"""Deterministic generation of exact, partial, ambiguous, incorrect, and contradictory prompts."""

from __future__ import annotations

import json
import random
from collections.abc import Iterable
from typing import Any, cast

from pydantic import JsonValue
from rdkit import Chem

from synthaudit import __version__
from synthaudit.graph.semantic_hash import reaction_ir_semantic_hash
from synthaudit.prompting.models import (
    PromptBenchmarkCaseV1,
    PromptInstructionRelation,
    PromptInstructionV1,
    PromptMutationKind,
    PromptMutationV1,
    PromptVariantKind,
    PromptVariantV1,
)
from synthaudit.schema.common import ProvenanceRecord
from synthaudit.schema.reaction_ir import ReactionIRV1


class PromptCaseIneligible(ValueError):
    """Raised when five meaningful prompt variants cannot be generated without guessing."""


def _provenance() -> tuple[ProvenanceRecord, ...]:
    return (
        ProvenanceRecord(
            source="synthaudit",
            source_version=__version__,
            adapter="PromptRobustnessCaseGenerator",
            adapter_version="1",
            license="Apache-2.0",
        ),
    )


def _operation_payload(operation: Any) -> dict[str, JsonValue]:
    return cast(
        dict[str, JsonValue],
        operation.model_dump(
            mode="json",
            exclude={"edit_id", "source_range", "metadata"},
        ),
    )


def _atom_maps(value: JsonValue, *, key: str = "") -> set[int]:
    result: set[int] = set()
    if isinstance(value, dict):
        for child_key, child in value.items():
            result.update(_atom_maps(child, key=child_key))
    elif isinstance(value, list):
        for child in value:
            result.update(_atom_maps(child, key=key))
    elif isinstance(value, int) and "map" in key and value > 0:
        result.add(value)
    return result


def _render(instruction: PromptInstructionV1) -> str:
    maps = ",".join(str(value) for value in instruction.atom_maps) or "site-unspecified"
    payload = json.dumps(instruction.operation_payload, sort_keys=True, separators=(",", ":"))
    return f"{instruction.edit_type} at atom maps [{maps}]; operation={payload}"


def _reference_instructions(reaction: ReactionIRV1) -> tuple[PromptInstructionV1, ...]:
    staged: Iterable[tuple[str, tuple[Any, ...]]] = (
        ("centre", cast(tuple[Any, ...], reaction.core_edits)),
        ("completion", cast(tuple[Any, ...], reaction.attachment_edits)),
        ("atom_state", cast(tuple[Any, ...], reaction.atom_state_edits)),
        ("stereo", cast(tuple[Any, ...], reaction.stereo_edits)),
    )
    instructions: list[PromptInstructionV1] = []
    for stage, operations in staged:
        for index, operation in enumerate(operations):
            payload = _operation_payload(operation)
            identifier = operation.edit_id or f"{stage}-{index}"
            provisional = PromptInstructionV1(
                instruction_id=identifier,
                edit_type=str(payload["edit_type"]),
                atom_maps=tuple(sorted(_atom_maps(payload))),
                operation_payload=payload,
                relation_to_reference=PromptInstructionRelation.CORRECT,
                rendered_text="pending",
            )
            instructions.append(
                provisional.model_copy(update={"rendered_text": _render(provisional)})
            )
    return tuple(instructions)


def _variant(
    *,
    reaction: ReactionIRV1,
    kind: PromptVariantKind,
    instructions: tuple[PromptInstructionV1, ...],
    seed: int,
    mutations: tuple[PromptMutationV1, ...] = (),
    omitted: tuple[str, ...] = (),
) -> PromptVariantV1:
    text = "\n".join(
        (
            f"Prompt quality={kind.value}. Treat atom maps as stable graph identities.",
            *(f"- {instruction.rendered_text}" for instruction in instructions),
        )
    )
    return PromptVariantV1(
        variant_id=f"{reaction.reaction_id}:{kind.value}:v1:{seed}",
        reaction_id=reaction.reaction_id,
        kind=kind,
        prompt_version="synthaudit.provider-neutral-edit-prompt/1",
        prompt_text=text,
        instructions=instructions,
        mutations=mutations,
        omitted_reference_instruction_ids=omitted,
        source_reaction_semantic_hash=reaction_ir_semantic_hash(reaction),
        generation_seed=seed,
        provenance=_provenance(),
    )


def _incorrect_instruction(
    reaction: ReactionIRV1,
    reference: PromptInstructionV1,
    rng: random.Random,
) -> tuple[PromptInstructionV1, str]:
    molecule = cast(Chem.Mol | None, Chem.MolFromSmiles(reaction.product.mapped_smiles))
    if molecule is None:
        raise PromptCaseIneligible("mapped product cannot be parsed for an incorrect-site decoy")
    reference_sites = {
        tuple(sorted(instruction.atom_maps[:2]))
        for instruction in _reference_instructions(reaction)
        if len(instruction.atom_maps) >= 2
    }
    candidates = sorted(
        (
            tuple(sorted((bond.GetBeginAtom().GetAtomMapNum(), bond.GetEndAtom().GetAtomMapNum()))),
            float(bond.GetBondTypeAsDouble()),
        )
        for bond in molecule.GetBonds()
        if bond.GetBeginAtom().GetAtomMapNum() > 0
        and bond.GetEndAtom().GetAtomMapNum() > 0
        and tuple(sorted((bond.GetBeginAtom().GetAtomMapNum(), bond.GetEndAtom().GetAtomMapNum())))
        not in reference_sites
    )
    if candidates:
        (map_a, map_b), order = rng.choice(candidates)
        payload: dict[str, JsonValue] = {
            "edit_type": "break_bond",
            "map_a": map_a,
            "map_b": map_b,
            "expected_order": order,
        }
        reason = "nearby_existing_product_bond_decoy"
    elif len(reference.atom_maps) >= 2:
        map_a, map_b = reference.atom_maps[:2]
        atom_by_map = {
            atom.GetAtomMapNum(): atom.GetIdx()
            for atom in molecule.GetAtoms()
            if atom.GetAtomMapNum() > 0
        }
        if map_a not in atom_by_map or map_b not in atom_by_map:
            raise PromptCaseIneligible(
                "reference site is not a product bond for a wrong-order prompt decoy"
            )
        bond = molecule.GetBondBetweenAtoms(atom_by_map[map_a], atom_by_map[map_b])
        if bond is None:
            raise PromptCaseIneligible(
                "reference site is not a product bond for a wrong-order prompt decoy"
            )
        expected_order = float(bond.GetBondTypeAsDouble())
        payload = {
            "edit_type": "change_bond_order",
            "map_a": map_a,
            "map_b": map_b,
            "expected_order": expected_order,
            "new_order": 1.0 if expected_order != 1.0 else 2.0,
        }
        reason = "wrong_bond_order_instruction_on_reference_site"
    else:
        raise PromptCaseIneligible(
            "reference has no mapped bond site for a structurally plausible incorrect prompt"
        )
    provisional = PromptInstructionV1(
        instruction_id=f"incorrect-{reference.instruction_id}",
        edit_type=str(payload["edit_type"]),
        atom_maps=tuple(sorted(_atom_maps(payload))),
        operation_payload=payload,
        relation_to_reference=PromptInstructionRelation.INCORRECT,
        rendered_text="pending",
    )
    return provisional.model_copy(update={"rendered_text": _render(provisional)}), reason


def _contradictory_instruction(reference: PromptInstructionV1) -> PromptInstructionV1:
    inverse = {
        "break_bond": "add_bond",
        "add_bond": "break_bond",
        "change_bond_order": "break_bond",
        "attach_fragment": "detach_fragment",
        "detach_fragment": "attach_fragment",
        "set_tetrahedral_stereo": "clear_tetrahedral_stereo",
        "invert_tetrahedral_stereo": "clear_tetrahedral_stereo",
        "clear_tetrahedral_stereo": "set_tetrahedral_stereo",
        "set_bond_stereo": "clear_bond_stereo",
        "clear_bond_stereo": "set_bond_stereo",
    }.get(reference.edit_type, f"negate_{reference.edit_type}")
    payload: dict[str, JsonValue] = {
        "edit_type": inverse,
        "contradicts_instruction_id": reference.instruction_id,
        "atom_maps": list(reference.atom_maps),
    }
    provisional = PromptInstructionV1(
        instruction_id=f"contradiction-{reference.instruction_id}",
        edit_type=inverse,
        atom_maps=reference.atom_maps,
        operation_payload=payload,
        relation_to_reference=PromptInstructionRelation.CONTRADICTORY,
        rendered_text="pending",
    )
    return provisional.model_copy(update={"rendered_text": _render(provisional)})


class PromptRobustnessCaseGenerator:
    """Build five deterministic variants for reactions with sufficient declared edits."""

    def build_case(
        self,
        reaction: ReactionIRV1,
        *,
        parent_group_id: str,
        seed: int,
    ) -> PromptBenchmarkCaseV1:
        reference = _reference_instructions(reaction)
        if not reaction.core_edits or len(reference) < 2:
            raise PromptCaseIneligible(
                "prompt benchmark eligibility requires at least one reaction-centre edit and "
                "at least two declared edit operations"
            )
        rng = random.Random(seed)
        exact = _variant(
            reaction=reaction,
            kind=PromptVariantKind.EXACT,
            instructions=reference,
            seed=seed,
        )
        retained = (reference[0],)
        omitted = tuple(item.instruction_id for item in reference[1:])
        partial = _variant(
            reaction=reaction,
            kind=PromptVariantKind.PARTIAL,
            instructions=retained,
            seed=seed,
            mutations=(
                PromptMutationV1(
                    mutation_kind=PromptMutationKind.OMIT,
                    reference_instruction_ids=omitted,
                    description="Retain one correct edit and omit the remaining necessary edits.",
                ),
            ),
            omitted=omitted,
        )
        ambiguous_instruction = PromptInstructionV1(
            instruction_id=f"ambiguous-{reference[0].instruction_id}",
            edit_type=reference[0].edit_type,
            atom_maps=(),
            operation_payload={"edit_type": reference[0].edit_type},
            relation_to_reference=PromptInstructionRelation.AMBIGUOUS,
            rendered_text=f"{reference[0].edit_type} at an unspecified eligible site",
        )
        ambiguous = _variant(
            reaction=reaction,
            kind=PromptVariantKind.AMBIGUOUS,
            instructions=(ambiguous_instruction,),
            seed=seed,
            mutations=(
                PromptMutationV1(
                    mutation_kind=PromptMutationKind.GENERALIZE,
                    reference_instruction_ids=(reference[0].instruction_id,),
                    description="Remove atom-site identity while retaining the edit family.",
                ),
            ),
        )
        incorrect_instruction, incorrect_reason = _incorrect_instruction(
            reaction, reference[0], rng
        )
        incorrect = _variant(
            reaction=reaction,
            kind=PromptVariantKind.INCORRECT_STRUCTURALLY_PLAUSIBLE,
            instructions=(incorrect_instruction,),
            seed=seed,
            mutations=(
                PromptMutationV1(
                    mutation_kind=PromptMutationKind.REPLACE,
                    reference_instruction_ids=(reference[0].instruction_id,),
                    description=incorrect_reason,
                ),
            ),
        )
        contradiction = _contradictory_instruction(reference[0])
        contradictory = _variant(
            reaction=reaction,
            kind=PromptVariantKind.CONTRADICTORY,
            instructions=(*reference, contradiction),
            seed=seed,
            mutations=(
                PromptMutationV1(
                    mutation_kind=PromptMutationKind.APPEND_CONTRADICTION,
                    reference_instruction_ids=(reference[0].instruction_id,),
                    description="Append an instruction that conflicts with a correct edit.",
                ),
            ),
        )
        return PromptBenchmarkCaseV1(
            case_id=f"prompt-case:{reaction.reaction_id}:{seed}",
            parent_group_id=parent_group_id,
            reference_reaction=reaction,
            variants=(exact, partial, ambiguous, incorrect, contradictory),
            provenance=_provenance(),
        )
