"""Seeded counterfactual mutations with exact field-level change records."""

from __future__ import annotations

import copy
import hashlib
import json
import random
import re
from collections.abc import Sequence
from typing import Any, cast

from rdkit import Chem
from rdkit.Chem.Scaffolds import MurckoScaffold

from synthaudit import __version__
from synthaudit.counterfactuals.models import (
    METHOD_CATEGORY,
    BenchmarkLabel,
    CounterfactualRecordV1,
    DifficultyLevel,
    FieldChangeV1,
    GenerationMethod,
)
from synthaudit.counterfactuals.validity import (
    evaluate_reaction,
    evaluate_reaction_payload,
    evaluate_route,
    evaluate_route_payload,
)
from synthaudit.schema.common import ProvenanceRecord
from synthaudit.schema.reaction_ir import ReactionIRV1
from synthaudit.schema.route_ir import RouteIRV1


class CounterfactualNotApplicable(ValueError):
    """Raised when a declared mutation cannot be applied to a parent."""


_DIFFICULTY: dict[GenerationMethod, DifficultyLevel] = {
    GenerationMethod.DUPLICATE_ATOM_MAPS: DifficultyLevel.EASY,
    GenerationMethod.DANGLING_ATOM_MAPS: DifficultyLevel.EASY,
    GenerationMethod.MALFORMED_EDIT: DifficultyLevel.EASY,
    GenerationMethod.MISSING_ATTACHMENT_REFERENCE: DifficultyLevel.EASY,
    GenerationMethod.IMPOSSIBLE_OPERATION_ORDERING: DifficultyLevel.MEDIUM,
    GenerationMethod.INVALID_LEAVING_GROUP_SYNTAX: DifficultyLevel.EASY,
    GenerationMethod.WRONG_BOND_BREAK: DifficultyLevel.MEDIUM,
    GenerationMethod.WRONG_BOND_ORDER_CHANGE: DifficultyLevel.MEDIUM,
    GenerationMethod.ALTERNATIVE_SITE_SWAP: DifficultyLevel.HARD,
    GenerationMethod.WRONG_RING_CLOSURE_ATOM: DifficultyLevel.HARD,
    GenerationMethod.CLASS_PRESERVING_CENTRE_DECOY: DifficultyLevel.HARD,
    GenerationMethod.UNEXPLAINED_GRAPH_CHANGE: DifficultyLevel.MEDIUM,
    GenerationMethod.WRONG_LEAVING_GROUP: DifficultyLevel.HARD,
    GenerationMethod.WRONG_ATTACHMENT_ATOM: DifficultyLevel.MEDIUM,
    GenerationMethod.MISSING_LEAVING_GROUP: DifficultyLevel.EASY,
    GenerationMethod.DUPLICATE_LEAVING_GROUP: DifficultyLevel.EASY,
    GenerationMethod.PRECURSOR_ANALOG_MISSING_HANDLE: DifficultyLevel.HARD,
    GenerationMethod.CHARGE_ONLY_COMPLETION_ERROR: DifficultyLevel.MEDIUM,
    GenerationMethod.MULTI_ATTACHMENT_TOPOLOGY_ERROR: DifficultyLevel.HARD,
    GenerationMethod.UNINTENDED_INVERSION: DifficultyLevel.MEDIUM,
    GenerationMethod.OMITTED_STEREOCHEMISTRY: DifficultyLevel.EASY,
    GenerationMethod.INCORRECT_E_Z: DifficultyLevel.MEDIUM,
    GenerationMethod.INVALID_CHIRAL_CENTRE_OPERATION: DifficultyLevel.EASY,
    GenerationMethod.CYCLIC_STEREOCHEMISTRY_CORRUPTION: DifficultyLevel.HARD,
    GenerationMethod.DEPENDENCY_VIOLATING_STEP_SWAP: DifficultyLevel.MEDIUM,
    GenerationMethod.DEPROTECTION_TOO_EARLY: DifficultyLevel.HARD,
    GenerationMethod.PROTECTION_TOO_LATE: DifficultyLevel.HARD,
    GenerationMethod.FRAGILE_INTERMEDIATE_INCOMPATIBLE_CONDITIONS: DifficultyLevel.HARD,
    GenerationMethod.PRECURSOR_NOT_PRODUCED: DifficultyLevel.MEDIUM,
}


def _json_pointer(path: Sequence[str | int]) -> str:
    def escape(value: str | int) -> str:
        return str(value).replace("~", "~0").replace("/", "~1")

    return "/" + "/".join(escape(item) for item in path)


def _change(
    path: Sequence[str | int],
    operation: str,
    before: Any,
    after: Any,
    reason: str,
) -> FieldChangeV1:
    return FieldChangeV1(
        json_pointer=_json_pointer(path),
        operation=cast(Any, operation),
        before=cast(Any, before),
        after=cast(Any, after),
        reason=reason,
    )


def _mapped_molecule(smiles: str) -> Chem.Mol:
    molecule = Chem.MolFromSmiles(smiles)
    if molecule is None:
        raise CounterfactualNotApplicable("parent product is not parseable by RDKit")
    return molecule


def product_atom_maps(reaction: ReactionIRV1) -> tuple[int, ...]:
    molecule = _mapped_molecule(reaction.product.mapped_smiles)
    return tuple(sorted(atom.GetAtomMapNum() for atom in molecule.GetAtoms()))


def product_scaffold_group(mapped_smiles: str) -> str:
    molecule = _mapped_molecule(mapped_smiles)
    for atom in molecule.GetAtoms():
        atom.SetAtomMapNum(0)
    scaffold = MurckoScaffold.GetScaffoldForMol(molecule)  # type: ignore[no-untyped-call]
    if not scaffold.GetNumAtoms():
        return "murcko:<acyclic>"
    smiles = Chem.MolToSmiles(scaffold, canonical=True, isomericSmiles=True)
    return f"murcko:{smiles}"


def _bonds(reaction: ReactionIRV1) -> list[tuple[int, int, float, bool]]:
    molecule = _mapped_molecule(reaction.product.mapped_smiles)
    values: list[tuple[int, int, float, bool]] = []
    for bond in molecule.GetBonds():
        map_a = bond.GetBeginAtom().GetAtomMapNum()
        map_b = bond.GetEndAtom().GetAtomMapNum()
        values.append(
            (min(map_a, map_b), max(map_a, map_b), bond.GetBondTypeAsDouble(), bond.IsInRing())
        )
    return sorted(values)


def _first_edit(payload: dict[str, Any]) -> tuple[str, int, dict[str, Any]]:
    for stage in ("core_edits", "attachment_edits", "atom_state_edits", "stereo_edits"):
        edits = cast(list[dict[str, Any]], payload[stage])
        if edits:
            return stage, 0, edits[0]
    raise CounterfactualNotApplicable("parent has no edit to mutate")


def _attachment(payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    edits = cast(list[dict[str, Any]], payload["attachment_edits"])
    for index, edit in enumerate(edits):
        if edit.get("edit_type") == "attach_fragment" and edit.get("attachment_kind") == "fragment":
            return index, edit
    raise CounterfactualNotApplicable("parent has no explicit leaving-group attachment")


def _core_edit(payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    edits = cast(list[dict[str, Any]], payload["core_edits"])
    if not edits:
        raise CounterfactualNotApplicable("parent has no reaction-centre edit")
    return 0, edits[0]


def _replace_product_map(smiles: str, old: int, new: int) -> str:
    changed, count = re.subn(rf":{old}(?=\])", f":{new}", smiles, count=1)
    if count != 1:
        raise CounterfactualNotApplicable(f"atom map {old} does not occur exactly as expected")
    return changed


def _reaction_mutation(
    parent: ReactionIRV1,
    method: GenerationMethod,
    rng: random.Random,
    seed: int,
) -> tuple[dict[str, Any], tuple[FieldChangeV1, ...]]:
    payload = copy.deepcopy(parent.model_dump(mode="json"))
    maps = product_atom_maps(parent)
    bonds = _bonds(parent)
    before: Any
    after: Any
    path: tuple[str | int, ...]
    index: int
    edit: dict[str, Any]
    edits: list[dict[str, Any]]
    added: dict[str, Any]
    if len(maps) < 2:
        raise CounterfactualNotApplicable("mutation requires at least two mapped product atoms")

    if method == GenerationMethod.DUPLICATE_ATOM_MAPS:
        old, duplicate_map = rng.sample(list(maps), 2)
        before = cast(str, payload["product"]["mapped_smiles"])
        after = _replace_product_map(before, old, duplicate_map)
        payload["product"]["mapped_smiles"] = after
        return payload, (
            _change(
                ("product", "mapped_smiles"),
                "replace",
                before,
                after,
                f"replace map {old} with existing map {duplicate_map}",
            ),
        )

    if method == GenerationMethod.DANGLING_ATOM_MAPS:
        stage, index, edit = _first_edit(payload)
        fields = [
            name for name in ("map_a", "map_b", "atom_map", "target_atom_map") if edit.get(name)
        ]
        if not fields and edit.get("connections"):
            path = (stage, index, "connections", 0, "product_atom_map")
            before = edit["connections"][0]["product_atom_map"]
            after = max(maps) + 1000
            edit["connections"][0]["product_atom_map"] = after
        elif fields:
            field = fields[0]
            path = (stage, index, field)
            before = edit[field]
            after = max(maps) + 1000
            edit[field] = after
        else:
            raise CounterfactualNotApplicable("selected edit has no map reference")
        return payload, (
            _change(path, "replace", before, after, "introduce a dangling atom-map reference"),
        )

    if method == GenerationMethod.MALFORMED_EDIT:
        stage, index, edit = _first_edit(payload)
        before = edit["edit_type"]
        after = "malformed_counterfactual_edit"
        edit["edit_type"] = after
        return payload, (
            _change(
                (stage, index, "edit_type"),
                "replace",
                before,
                after,
                "replace the discriminated edit type with invalid syntax",
            ),
        )

    if method == GenerationMethod.MISSING_ATTACHMENT_REFERENCE:
        index, edit = _attachment(payload)
        before = edit["connections"][0]["product_atom_map"]
        after = max(maps) + 1000
        edit["connections"][0]["product_atom_map"] = after
        return payload, (
            _change(
                ("attachment_edits", index, "connections", 0, "product_atom_map"),
                "replace",
                before,
                after,
                "make the attachment point absent from the product graph",
            ),
        )

    if method == GenerationMethod.IMPOSSIBLE_OPERATION_ORDERING:
        edits = cast(list[dict[str, Any]], payload["core_edits"])
        if not edits:
            raise CounterfactualNotApplicable("operation-order mutation requires a core edit")
        before = copy.deepcopy(edits)
        original = edits[0]
        if original["edit_type"] == "break_bond":
            added = {
                "edit_id": f"counterfactual-order-{seed}",
                "source_range": None,
                "metadata": {"counterfactual": True},
                "map_a": original["map_a"],
                "map_b": original["map_b"],
                "edit_type": "add_bond",
                "order": original.get("expected_order") or 1.0,
            }
            edits.insert(0, added)
        elif len(edits) > 1:
            edits.reverse()
        else:
            raise CounterfactualNotApplicable("cannot create an ordering conflict for this edit")
        return payload, (
            _change(
                ("core_edits",),
                "reorder",
                before,
                edits,
                "place an incompatible operation before its prerequisite",
            ),
        )

    if method == GenerationMethod.INVALID_LEAVING_GROUP_SYNTAX:
        index, edit = _attachment(payload)
        before = edit["fragment_smiles"]
        after = "[Cl:"
        edit["fragment_smiles"] = after
        return payload, (
            _change(
                ("attachment_edits", index, "fragment_smiles"),
                "replace",
                before,
                after,
                "introduce invalid leaving-group syntax",
            ),
        )

    if method in {
        GenerationMethod.WRONG_BOND_BREAK,
        GenerationMethod.ALTERNATIVE_SITE_SWAP,
        GenerationMethod.CLASS_PRESERVING_CENTRE_DECOY,
    }:
        index, edit = _core_edit(payload)
        current = {edit.get("map_a"), edit.get("map_b")}
        alternatives = [bond for bond in bonds if {bond[0], bond[1]} != current]
        if not alternatives:
            raise CounterfactualNotApplicable("parent has no alternative product bond")
        chosen = rng.choice(alternatives)
        before = copy.deepcopy(edit)
        if method == GenerationMethod.WRONG_BOND_BREAK:
            after = {
                "edit_id": edit.get("edit_id"),
                "source_range": edit.get("source_range"),
                "metadata": {**edit.get("metadata", {}), "counterfactual": True},
                "map_a": chosen[0],
                "map_b": chosen[1],
                "edit_type": "break_bond",
                "expected_order": chosen[2],
            }
        else:
            after = copy.deepcopy(edit)
            after["map_a"], after["map_b"] = chosen[0], chosen[1]
            after["metadata"] = {**after.get("metadata", {}), "counterfactual": True}
        payload["core_edits"][index] = after
        reason = {
            GenerationMethod.WRONG_BOND_BREAK: "break a different product bond",
            GenerationMethod.ALTERNATIVE_SITE_SWAP: "move the declared centre to an alternative site",
            GenerationMethod.CLASS_PRESERVING_CENTRE_DECOY: "preserve edit type while moving its centre",
        }[method]
        return payload, (_change(("core_edits", index), "replace", before, after, reason),)

    if method == GenerationMethod.WRONG_BOND_ORDER_CHANGE:
        if not bonds:
            raise CounterfactualNotApplicable("parent has no bond for an order-change decoy")
        index, edit = _core_edit(payload)
        chosen = rng.choice(bonds)
        before = copy.deepcopy(edit)
        to_order = 2.0 if chosen[2] == 1.0 else 1.0
        after = {
            "edit_id": edit.get("edit_id"),
            "source_range": edit.get("source_range"),
            "metadata": {**edit.get("metadata", {}), "counterfactual": True},
            "map_a": chosen[0],
            "map_b": chosen[1],
            "edit_type": "change_bond_order",
            "from_order": chosen[2],
            "to_order": to_order,
        }
        payload["core_edits"][index] = after
        return payload, (
            _change(
                ("core_edits", index),
                "replace",
                before,
                after,
                "replace the recorded centre with a different bond-order change",
            ),
        )

    if method == GenerationMethod.WRONG_RING_CLOSURE_ATOM:
        ring_bonds = [bond for bond in bonds if bond[3]]
        index, edit = _core_edit(payload)
        current = {edit.get("map_a"), edit.get("map_b")}
        alternatives = [bond for bond in ring_bonds if {bond[0], bond[1]} != current]
        if not alternatives:
            raise CounterfactualNotApplicable("parent has no alternative ring bond")
        chosen = rng.choice(alternatives)
        before = copy.deepcopy(edit)
        after = {
            "edit_id": edit.get("edit_id"),
            "source_range": edit.get("source_range"),
            "metadata": {**edit.get("metadata", {}), "counterfactual": True},
            "map_a": chosen[0],
            "map_b": chosen[1],
            "edit_type": "break_bond",
            "expected_order": chosen[2],
        }
        payload["core_edits"][index] = after
        return payload, (
            _change(
                ("core_edits", index),
                "replace",
                before,
                after,
                "move a retrosynthetic ring-opening edit to the wrong ring bond",
            ),
        )

    if method == GenerationMethod.UNEXPLAINED_GRAPH_CHANGE:
        edits = cast(list[dict[str, Any]], payload["core_edits"])
        if not edits:
            raise CounterfactualNotApplicable("parent has no core edit to omit")
        before = copy.deepcopy(edits[0])
        del edits[0]
        return payload, (
            _change(
                ("core_edits", 0),
                "remove",
                before,
                None,
                "omit a graph change while retaining the recorded precursor target",
            ),
        )

    if method == GenerationMethod.WRONG_LEAVING_GROUP:
        index, edit = _attachment(payload)
        before = cast(str, edit["fragment_smiles"])
        replacements = (("Br", "Cl"), ("Cl", "F"), ("I", "Br"))
        after = before
        for source, target in replacements:
            if source in before:
                after = before.replace(source, target, 1)
                break
        if after == before:
            after = re.sub(r"\[[A-Za-z]+", "[Cl", before, count=1)
        edit["fragment_smiles"] = after
        return payload, (
            _change(
                ("attachment_edits", index, "fragment_smiles"),
                "replace",
                before,
                after,
                "substitute a different explicit leaving group",
            ),
        )

    if method == GenerationMethod.WRONG_ATTACHMENT_ATOM:
        index, edit = _attachment(payload)
        before = edit["connections"][0]["product_atom_map"]
        choices = [item for item in maps if item != before]
        after = rng.choice(choices)
        edit["connections"][0]["product_atom_map"] = after
        return payload, (
            _change(
                ("attachment_edits", index, "connections", 0, "product_atom_map"),
                "replace",
                before,
                after,
                "attach the leaving group to a different product-derived atom",
            ),
        )

    if method == GenerationMethod.MISSING_LEAVING_GROUP:
        index, edit = _attachment(payload)
        del payload["attachment_edits"][index]
        return payload, (
            _change(
                ("attachment_edits", index),
                "remove",
                edit,
                None,
                "remove a required explicit leaving-group completion",
            ),
        )

    if method == GenerationMethod.DUPLICATE_LEAVING_GROUP:
        _, edit = _attachment(payload)
        duplicate = copy.deepcopy(edit)
        duplicate["edit_id"] = f"counterfactual-duplicate-{seed}"
        index = len(payload["attachment_edits"])
        payload["attachment_edits"].append(duplicate)
        return payload, (
            _change(
                ("attachment_edits", index),
                "add",
                None,
                duplicate,
                "duplicate a leaving-group completion",
            ),
        )

    if method == GenerationMethod.PRECURSOR_ANALOG_MISSING_HANDLE:
        precursors = cast(list[dict[str, Any]], payload["expected_precursors"])
        if len(precursors) < 2:
            raise CounterfactualNotApplicable("mutation requires multiple recorded precursors")
        before = copy.deepcopy(precursors)
        del precursors[0]
        return payload, (
            _change(
                ("expected_precursors",),
                "replace",
                before,
                precursors,
                "retain an analog set that lacks the precursor bearing the required handle",
            ),
        )

    if method == GenerationMethod.CHARGE_ONLY_COMPLETION_ERROR:
        atom_edits = cast(list[dict[str, Any]], payload["atom_state_edits"])
        for index, edit in enumerate(atom_edits):
            if edit.get("property") == "formal_charge":
                before = edit["to_value"]
                after = int(before) + (1 if int(before) <= 0 else -1)
                if after == edit.get("from_value"):
                    after += 1
                edit["to_value"] = after
                return payload, (
                    _change(
                        ("atom_state_edits", index, "to_value"),
                        "replace",
                        before,
                        after,
                        "apply an incorrect charge completion",
                    ),
                )
        added = {
            "edit_id": f"counterfactual-charge-{seed}",
            "source_range": None,
            "metadata": {"counterfactual": True},
            "edit_type": "attach_fragment",
            "attachment_kind": "charge_only",
            "fragment_smiles": None,
            "connections": [],
            "target_atom_map": maps[0],
            "charge_delta": 1,
        }
        index = len(payload["attachment_edits"])
        payload["attachment_edits"].append(added)
        return payload, (
            _change(
                ("attachment_edits", index),
                "add",
                None,
                added,
                "introduce an unsupported charge-only completion",
            ),
        )

    if method == GenerationMethod.MULTI_ATTACHMENT_TOPOLOGY_ERROR:
        index, edit = _attachment(payload)
        connections = cast(list[dict[str, Any]], edit["connections"])
        if len(connections) < 2:
            raise CounterfactualNotApplicable("parent has no multi-attachment topology")
        before = connections[1]["product_atom_map"]
        after = connections[0]["product_atom_map"]
        if before == after:
            after = rng.choice([item for item in maps if item != before])
        connections[1]["product_atom_map"] = after
        return payload, (
            _change(
                ("attachment_edits", index, "connections", 1, "product_atom_map"),
                "replace",
                before,
                after,
                "rewire one arm of a multi-attached fragment",
            ),
        )

    if method == GenerationMethod.UNINTENDED_INVERSION:
        molecule = _mapped_molecule(parent.product.mapped_smiles)
        centres = Chem.FindMolChiralCenters(  # type: ignore[no-untyped-call]
            molecule, includeUnassigned=False
        )
        if not centres:
            raise CounterfactualNotApplicable("parent product has no assigned tetrahedral centre")
        atom_map = molecule.GetAtomWithIdx(centres[0][0]).GetAtomMapNum()
        added = {
            "edit_id": f"counterfactual-invert-{seed}",
            "source_range": None,
            "metadata": {"counterfactual": True},
            "edit_type": "invert_tetrahedral_stereo",
            "atom_map": atom_map,
        }
        index = len(payload["stereo_edits"])
        payload["stereo_edits"].append(added)
        return payload, (
            _change(
                ("stereo_edits", index),
                "add",
                None,
                added,
                "introduce an inversion absent from the parent",
            ),
        )

    if method == GenerationMethod.OMITTED_STEREOCHEMISTRY:
        edits = cast(list[dict[str, Any]], payload["stereo_edits"])
        if not edits:
            raise CounterfactualNotApplicable("parent declares no stereo edit")
        before = copy.deepcopy(edits)
        edits.clear()
        return payload, (
            _change(
                ("stereo_edits",),
                "replace",
                before,
                [],
                "omit all declared stereochemical operations",
            ),
        )

    if method == GenerationMethod.INCORRECT_E_Z:
        edits = cast(list[dict[str, Any]], payload["stereo_edits"])
        for index, edit in enumerate(edits):
            if edit["edit_type"] in {"set_bond_stereo", "clear_bond_stereo"}:
                before = copy.deepcopy(edit)
                after = {
                    "edit_id": edit.get("edit_id"),
                    "source_range": edit.get("source_range"),
                    "metadata": {**edit.get("metadata", {}), "counterfactual": True},
                    "map_a": edit["map_a"],
                    "map_b": edit["map_b"],
                    "edit_type": "set_bond_stereo",
                    "stereo": "Z" if edit.get("stereo") == "E" else "E",
                    "stereo_atom_a": None,
                    "stereo_atom_b": None,
                }
                edits[index] = after
                return payload, (
                    _change(
                        ("stereo_edits", index),
                        "replace",
                        before,
                        after,
                        "replace the declared alkene stereo outcome",
                    ),
                )
        raise CounterfactualNotApplicable("parent has no bond-stereo operation")

    if method == GenerationMethod.INVALID_CHIRAL_CENTRE_OPERATION:
        molecule = _mapped_molecule(parent.product.mapped_smiles)
        candidates = [
            atom.GetAtomMapNum()
            for atom in molecule.GetAtoms()
            if atom.GetDegree() < 3 or atom.GetAtomicNum() != 6
        ]
        if not candidates:
            raise CounterfactualNotApplicable("no clearly non-chiral target atom is available")
        atom_map = rng.choice(candidates)
        added = {
            "edit_id": f"counterfactual-invalid-chiral-{seed}",
            "source_range": None,
            "metadata": {"counterfactual": True},
            "edit_type": "invert_tetrahedral_stereo",
            "atom_map": atom_map,
        }
        index = len(payload["stereo_edits"])
        payload["stereo_edits"].append(added)
        return payload, (
            _change(
                ("stereo_edits", index),
                "add",
                None,
                added,
                "target a non-stereogenic atom with a chiral operation",
            ),
        )

    if method == GenerationMethod.CYCLIC_STEREOCHEMISTRY_CORRUPTION:
        molecule = _mapped_molecule(parent.product.mapped_smiles)
        ring_maps = sorted(atom.GetAtomMapNum() for atom in molecule.GetAtoms() if atom.IsInRing())
        if not ring_maps:
            raise CounterfactualNotApplicable("parent product contains no ring atom")
        added = {
            "edit_id": f"counterfactual-cyclic-stereo-{seed}",
            "source_range": None,
            "metadata": {"counterfactual": True, "cyclic_path": True},
            "edit_type": "invert_tetrahedral_stereo",
            "atom_map": rng.choice(ring_maps),
        }
        index = len(payload["stereo_edits"])
        payload["stereo_edits"].append(added)
        return payload, (
            _change(
                ("stereo_edits", index),
                "add",
                None,
                added,
                "corrupt a ring atom through an unsupported inversion",
            ),
        )

    raise CounterfactualNotApplicable(f"{method.value} is a route-level mutation")


def _route_mutation(
    parent: RouteIRV1,
    method: GenerationMethod,
    seed: int,
) -> tuple[dict[str, Any], tuple[FieldChangeV1, ...]]:
    payload = copy.deepcopy(parent.model_dump(mode="json"))
    steps = cast(list[dict[str, Any]], payload["steps"])
    before: Any
    after: Any
    if len(steps) < 2:
        raise CounterfactualNotApplicable("route mutation requires at least two steps")

    if method == GenerationMethod.DEPENDENCY_VIOLATING_STEP_SWAP:
        before = copy.deepcopy(steps)
        steps.reverse()
        return payload, (
            _change(
                ("steps",),
                "reorder",
                before,
                steps,
                "place dependent steps before their declared prerequisites",
            ),
        )

    if method in {GenerationMethod.DEPROTECTION_TOO_EARLY, GenerationMethod.PROTECTION_TOO_LATE}:
        strategy = (
            "deprotection" if method == GenerationMethod.DEPROTECTION_TOO_EARLY else "protection"
        )
        index = next(
            (
                item
                for item, step in enumerate(steps)
                if strategy in str(step.get("strategy_text", "")).lower()
            ),
            None,
        )
        if index is None:
            raise CounterfactualNotApplicable(f"route has no {strategy} step")
        before = copy.deepcopy(steps)
        selected = steps.pop(index)
        if method == GenerationMethod.DEPROTECTION_TOO_EARLY:
            steps.insert(0, selected)
            reason = "move deprotection before its protected intermediate is ready"
        else:
            steps.append(selected)
            reason = "move protection after steps that require the protected intermediate"
        if before == steps:
            steps.reverse()
        return payload, (_change(("steps",), "reorder", before, steps, reason),)

    if method == GenerationMethod.FRAGILE_INTERMEDIATE_INCOMPATIBLE_CONDITIONS:
        index = 1
        metadata = cast(dict[str, Any], steps[index]["metadata"])
        before = copy.deepcopy(metadata)
        after = {
            **metadata,
            "counterfactual_fragile_intermediate": steps[index - 1].get("produces", []),
            "counterfactual_incompatible_condition": "strong_acid_fixture_rule",
            "counterfactual_seed": seed,
        }
        steps[index]["metadata"] = after
        return payload, (
            _change(
                ("steps", index, "metadata"),
                "replace",
                before,
                after,
                "place a declared fragile intermediate before an incompatible condition",
            ),
        )

    if method == GenerationMethod.PRECURSOR_NOT_PRODUCED:
        index = 1
        consumes = cast(list[str], steps[index]["consumes"])
        before = copy.deepcopy(consumes)
        after = [f"unproduced-node-{seed}"]
        steps[index]["consumes"] = after
        return payload, (
            _change(
                ("steps", index, "consumes"),
                "replace",
                before,
                after,
                "replace a precursor node with one produced by no prior step",
            ),
        )

    raise CounterfactualNotApplicable(f"{method.value} is not a supported route mutation")


def _record_id(parent_reaction_id: str, method: GenerationMethod, seed: int) -> str:
    digest = hashlib.sha256(f"{parent_reaction_id}|{method.value}|{seed}".encode()).hexdigest()
    return f"cf-{digest[:20]}"


def _provenance(method: str) -> tuple[ProvenanceRecord, ...]:
    return (
        ProvenanceRecord(
            source="synthaudit",
            source_version=__version__,
            adapter=method,
            adapter_version="1",
            license="Apache-2.0",
        ),
    )


class CounterfactualGenerator:
    """Generate one controlled mutation; never reinterpret its label as an outcome."""

    generator_version = "synthaudit.counterfactual-generator/1"

    def recorded_reaction(
        self,
        reaction: ReactionIRV1,
        *,
        record_id: str,
        source_dataset: str,
        source_version: str,
        data_license_status: str,
        reaction_class: str,
        tags: tuple[str, ...] = (),
    ) -> CounterfactualRecordV1:
        return CounterfactualRecordV1(
            record_id=record_id,
            label=BenchmarkLabel.RECORDED_REACTION,
            structural_validity=evaluate_reaction(reaction),
            reaction=reaction,
            source_dataset=source_dataset,
            source_version=source_version,
            data_license_status=data_license_status,
            reaction_class=reaction_class,
            product_scaffold_group=product_scaffold_group(reaction.product.mapped_smiles),
            tags=tags,
            provenance=_provenance("CounterfactualGenerator.recorded_reaction"),
        )

    def recorded_route(
        self,
        route: RouteIRV1,
        *,
        record_id: str,
        source_dataset: str,
        source_version: str,
        data_license_status: str,
        reaction_class: str,
        tags: tuple[str, ...] = (),
    ) -> CounterfactualRecordV1:
        if not route.steps:
            raise CounterfactualNotApplicable("a benchmark route requires at least one step")
        return CounterfactualRecordV1(
            record_id=record_id,
            label=BenchmarkLabel.RECORDED_REACTION,
            structural_validity=evaluate_route(route),
            route=route,
            source_dataset=source_dataset,
            source_version=source_version,
            data_license_status=data_license_status,
            reaction_class=reaction_class,
            product_scaffold_group=product_scaffold_group(route.target.mapped_smiles),
            tags=tags,
            provenance=_provenance("CounterfactualGenerator.recorded_route"),
        )

    def generate_reaction(
        self,
        parent: CounterfactualRecordV1,
        *,
        method: GenerationMethod,
        seed: int,
    ) -> CounterfactualRecordV1:
        if parent.label != BenchmarkLabel.RECORDED_REACTION or parent.reaction is None:
            raise CounterfactualNotApplicable("reaction counterfactual requires a recorded parent")
        if METHOD_CATEGORY[method].value == "route":
            raise CounterfactualNotApplicable("route method requires a route parent")
        payload, changes = _reaction_mutation(parent.reaction, method, random.Random(seed), seed)
        reaction, validity = evaluate_reaction_payload(payload)
        return CounterfactualRecordV1(
            record_id=_record_id(parent.reaction.reaction_id, method, seed),
            label=BenchmarkLabel.GENERATED_COUNTERFACTUAL,
            parent_reaction_id=parent.reaction.reaction_id,
            generation_method=method,
            category=METHOD_CATEGORY[method],
            seed=seed,
            changed_fields=changes,
            structural_validity=validity,
            difficulty=_DIFFICULTY[method],
            reaction=reaction,
            raw_candidate_payload=payload if reaction is None else None,
            source_dataset=parent.source_dataset,
            source_version=parent.source_version,
            data_license_status=parent.data_license_status,
            reaction_class=parent.reaction_class,
            product_scaffold_group=parent.product_scaffold_group,
            tags=parent.tags,
            provenance=_provenance(f"CounterfactualGenerator.{method.value}"),
        )

    def generate_route(
        self,
        parent: CounterfactualRecordV1,
        *,
        method: GenerationMethod,
        seed: int,
    ) -> CounterfactualRecordV1:
        if parent.label != BenchmarkLabel.RECORDED_REACTION or parent.route is None:
            raise CounterfactualNotApplicable("route counterfactual requires a recorded route")
        if METHOD_CATEGORY[method].value != "route":
            raise CounterfactualNotApplicable("reaction method cannot mutate a route parent")
        payload, changes = _route_mutation(parent.route, method, seed)
        route, validity = evaluate_route_payload(payload)
        parent_reaction_id = parent.route.steps[-1].reaction.reaction_id
        return CounterfactualRecordV1(
            record_id=_record_id(parent_reaction_id, method, seed),
            label=BenchmarkLabel.GENERATED_COUNTERFACTUAL,
            parent_reaction_id=parent_reaction_id,
            parent_route_id=parent.route.route_id,
            generation_method=method,
            category=METHOD_CATEGORY[method],
            seed=seed,
            changed_fields=changes,
            structural_validity=validity,
            difficulty=_DIFFICULTY[method],
            route=route,
            raw_candidate_payload=payload if route is None else None,
            source_dataset=parent.source_dataset,
            source_version=parent.source_version,
            data_license_status=parent.data_license_status,
            reaction_class=parent.reaction_class,
            product_scaffold_group=parent.product_scaffold_group,
            tags=parent.tags,
            provenance=_provenance(f"CounterfactualGenerator.{method.value}"),
        )


def canonical_payload_sha256(payload: Any) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode()).hexdigest()
