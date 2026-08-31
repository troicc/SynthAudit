"""Representation-independent semantic comparison functions."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any, cast

from rdkit import Chem

from synthaudit import __version__
from synthaudit.graph.executor import ReactionExecutor
from synthaudit.schema.common import ProvenanceRecord
from synthaudit.schema.edits import AttachFragmentEdit, DetachFragmentEdit
from synthaudit.schema.reaction_ir import ReactionIRV1
from synthaudit.schema.results import (
    ComparisonState,
    ExecutionResultBase,
    GraphDiffV1,
    SemanticComparisonV1,
)


def _provenance() -> tuple[ProvenanceRecord, ...]:
    return (
        ProvenanceRecord(
            source="synthaudit",
            source_version=__version__,
            adapter="semantic-comparison",
            adapter_version="1",
            license="Apache-2.0",
        ),
    )


def _canonical_components(structures: Iterable[str], *, clear_maps: bool) -> tuple[str, ...]:
    result: list[str] = []
    for structure in structures:
        molecule = cast(Chem.Mol | None, Chem.MolFromSmiles(structure))
        if molecule is None:
            raise ValueError(f"cannot parse structure for semantic comparison: {structure!r}")
        if clear_maps:
            for atom in molecule.GetAtoms():
                atom.SetAtomMapNum(0)
        canonical = Chem.MolToSmiles(molecule, canonical=True, isomericSmiles=True)
        result.extend(canonical.split("."))
    return tuple(sorted(result))


def compare_precursor_sets(
    left: Iterable[str],
    right: Iterable[str],
) -> SemanticComparisonV1:
    """Compare chemical graphs and report map-only differences separately."""
    try:
        left_values = tuple(left)
        right_values = tuple(right)
        exact = _canonical_components(left_values, clear_maps=False) == _canonical_components(
            right_values, clear_maps=False
        )
        chemical = _canonical_components(left_values, clear_maps=True) == _canonical_components(
            right_values, clear_maps=True
        )
    except ValueError as exc:
        return SemanticComparisonV1(
            state=ComparisonState.INDETERMINATE,
            exact_semantic_equivalence=None,
            equivalent_precursor_set=None,
            equivalent_reaction_centre=None,
            equivalent_attachment_completion=None,
            equivalent_stereo_result=None,
            reasons=(str(exc),),
            provenance=_provenance(),
        )
    mismatches: list[str] = []
    if chemical and not exact:
        mismatches.append("atom_map_renumbering")
    elif not chemical:
        mismatches.append("precursor_set")
    return SemanticComparisonV1(
        state=ComparisonState.EQUIVALENT if chemical else ComparisonState.DIFFERENT,
        exact_semantic_equivalence=exact,
        equivalent_precursor_set=chemical,
        equivalent_reaction_centre=None,
        equivalent_attachment_completion=None,
        equivalent_stereo_result=None,
        mismatch_categories=tuple(mismatches),
        provenance=_provenance(),
    )


def _mapped_atom(atom_map: int, correspondence: Mapping[int, int]) -> int:
    return correspondence.get(atom_map, atom_map)


def _core_signature(
    reaction: ReactionIRV1,
    correspondence: Mapping[int, int] = {},
) -> tuple[tuple[Any, ...], ...]:
    signatures: list[tuple[Any, ...]] = []
    for edit in reaction.core_edits:
        endpoints = tuple(
            sorted(
                (
                    _mapped_atom(edit.map_a, correspondence),
                    _mapped_atom(edit.map_b, correspondence),
                )
            )
        )
        payload = edit.model_dump(
            mode="json", exclude={"edit_id", "source_range", "metadata", "map_a", "map_b"}
        )
        signatures.append((edit.edit_type, *endpoints, json.dumps(payload, sort_keys=True)))
    return tuple(sorted(signatures))


def _fragment_connection_signature(
    fragment_smiles: str,
    fragment_atom_map: int,
) -> tuple[int, int, int, int]:
    molecule = cast(Chem.Mol | None, Chem.MolFromSmiles(fragment_smiles))
    if molecule is None:
        raise ValueError("attachment fragment is not parseable")
    target_index = None
    for atom in molecule.GetAtoms():
        if atom.GetAtomMapNum() == fragment_atom_map:
            target_index = atom.GetIdx()
        atom.SetAtomMapNum(0)
    if target_index is None:
        raise ValueError("attachment fragment map is dangling")
    ranks = tuple(Chem.CanonicalRankAtoms(molecule, breakTies=False))
    atom = molecule.GetAtomWithIdx(target_index)
    return (atom.GetAtomicNum(), atom.GetFormalCharge(), atom.GetDegree(), ranks[target_index])


def _attachment_signature(
    reaction: ReactionIRV1,
    correspondence: Mapping[int, int] = {},
) -> tuple[tuple[Any, ...], ...]:
    signatures: list[tuple[Any, ...]] = []
    for edit in reaction.attachment_edits:
        if isinstance(edit, AttachFragmentEdit):
            if edit.attachment_kind == "fragment":
                assert edit.fragment_smiles is not None
                fragment = _canonical_components((edit.fragment_smiles,), clear_maps=True)[0]
                connections = tuple(
                    sorted(
                        (
                            _mapped_atom(connection.product_atom_map, correspondence),
                            connection.order,
                            _fragment_connection_signature(
                                edit.fragment_smiles, connection.fragment_atom_map
                            ),
                        )
                        for connection in edit.connections
                    )
                )
                signatures.append(("fragment", fragment, connections))
            else:
                signatures.append(
                    (
                        edit.attachment_kind,
                        (
                            _mapped_atom(edit.target_atom_map, correspondence)
                            if edit.target_atom_map is not None
                            else None
                        ),
                        edit.charge_delta,
                    )
                )
        elif isinstance(edit, DetachFragmentEdit):
            signatures.append(
                (
                    "detach",
                    tuple(
                        sorted(
                            _mapped_atom(atom_map, correspondence)
                            for atom_map in edit.fragment_atom_maps
                        )
                    ),
                    tuple(
                        sorted(
                            tuple(
                                sorted(_mapped_atom(atom_map, correspondence) for atom_map in pair)
                            )
                            for pair in edit.attachment_bonds
                        )
                    ),
                )
            )
    return tuple(sorted(signatures, key=repr))


def _remap_stage_payload(value: Any, correspondence: Mapping[int, int]) -> Any:
    if isinstance(value, list):
        return [_remap_stage_payload(item, correspondence) for item in value]
    if not isinstance(value, dict):
        return value
    mapped: dict[str, Any] = {}
    scalar_fields = {
        "atom_map",
        "map_a",
        "map_b",
        "stereo_atom_a",
        "stereo_atom_b",
        "target_atom_map",
        "product_atom_map",
    }
    sequence_fields = {"neighbour_maps", "fragment_atom_maps"}
    for key, item in value.items():
        if key in scalar_fields and isinstance(item, int):
            mapped[key] = _mapped_atom(item, correspondence)
        elif key in sequence_fields and isinstance(item, list):
            mapped[key] = [_mapped_atom(atom_map, correspondence) for atom_map in item]
        elif key == "attachment_bonds" and isinstance(item, list):
            mapped[key] = [
                [_mapped_atom(atom_map, correspondence) for atom_map in pair] for pair in item
            ]
        else:
            mapped[key] = _remap_stage_payload(item, correspondence)
    return mapped


def _stage_signature(
    edits: Iterable[object],
    correspondence: Mapping[int, int] = {},
) -> tuple[str, ...]:
    values = []
    for edit in edits:
        payload = edit.model_dump(  # type: ignore[attr-defined]
            mode="json", exclude={"edit_id", "source_range", "metadata"}
        )
        values.append(
            json.dumps(
                _remap_stage_payload(payload, correspondence),
                sort_keys=True,
                separators=(",", ":"),
            )
        )
    return tuple(sorted(values))


def _product_correspondences(
    left_smiles: str,
    right_smiles: str,
) -> tuple[dict[int, int], ...]:
    """Return every bounded right-map to left-map product isomorphism."""
    left = cast(Chem.Mol | None, Chem.MolFromSmiles(left_smiles))
    right = cast(Chem.Mol | None, Chem.MolFromSmiles(right_smiles))
    if left is None or right is None:
        raise ValueError("cannot parse product for atom-map correspondence")
    if left.GetNumAtoms() != right.GetNumAtoms():
        return ()
    left_maps = tuple(atom.GetAtomMapNum() for atom in left.GetAtoms())
    right_maps = tuple(atom.GetAtomMapNum() for atom in right.GetAtoms())
    if any(atom_map < 1 for atom_map in (*left_maps, *right_maps)):
        raise ValueError("product comparison requires complete positive atom maps")
    for molecule in (left, right):
        for atom in molecule.GetAtoms():
            atom.SetAtomMapNum(0)
    matches = right.GetSubstructMatches(
        left,
        uniquify=False,
        useChirality=True,
        maxMatches=256,
    )
    correspondences: set[tuple[tuple[int, int], ...]] = set()
    for match in matches:
        if len(match) != left.GetNumAtoms():
            continue
        correspondence = tuple(
            sorted(
                (right_maps[right_index], left_maps[left_index])
                for left_index, right_index in enumerate(match)
            )
        )
        correspondences.add(correspondence)
    return tuple(dict(items) for items in sorted(correspondences))


def _stage_equivalence(
    left: ReactionIRV1,
    right: ReactionIRV1,
    correspondence: Mapping[int, int],
) -> tuple[bool, bool, bool, bool]:
    return (
        _core_signature(left) == _core_signature(right, correspondence),
        _attachment_signature(left) == _attachment_signature(right, correspondence),
        _stage_signature(left.atom_state_edits)
        == _stage_signature(right.atom_state_edits, correspondence),
        _stage_signature(left.stereo_edits) == _stage_signature(right.stereo_edits, correspondence),
    )


def compare_reaction_ir(left: ReactionIRV1, right: ReactionIRV1) -> SemanticComparisonV1:
    """Compare stages and reconstructed graphs, never source strings."""
    mismatches: list[str] = []
    reasons: list[str] = []
    try:
        product_equivalent = _canonical_components(
            (left.product.mapped_smiles,), clear_maps=True
        ) == _canonical_components((right.product.mapped_smiles,), clear_maps=True)
        product_exact = _canonical_components(
            (left.product.mapped_smiles,), clear_maps=False
        ) == _canonical_components((right.product.mapped_smiles,), clear_maps=False)
        if product_exact:
            outcomes = {_stage_equivalence(left, right, {})}
        elif product_equivalent:
            correspondences = _product_correspondences(
                left.product.mapped_smiles,
                right.product.mapped_smiles,
            )
            outcomes = {
                _stage_equivalence(left, right, correspondence)
                for correspondence in correspondences
            }
        else:
            outcomes = {_stage_equivalence(left, right, {})}
    except ValueError as exc:
        return SemanticComparisonV1(
            state=ComparisonState.INDETERMINATE,
            exact_semantic_equivalence=None,
            equivalent_precursor_set=None,
            equivalent_reaction_centre=None,
            equivalent_attachment_completion=None,
            equivalent_stereo_result=None,
            reasons=(str(exc),),
            provenance=_provenance(),
        )

    if not outcomes:
        return SemanticComparisonV1(
            state=ComparisonState.INDETERMINATE,
            exact_semantic_equivalence=None,
            equivalent_precursor_set=None,
            equivalent_reaction_centre=None,
            equivalent_attachment_completion=None,
            equivalent_stereo_result=None,
            reasons=("no product atom-map correspondence could be established",),
            provenance=_provenance(),
        )
    if len(outcomes) > 1:
        return SemanticComparisonV1(
            state=ComparisonState.INDETERMINATE,
            exact_semantic_equivalence=None,
            equivalent_precursor_set=None,
            equivalent_reaction_centre=None,
            equivalent_attachment_completion=None,
            equivalent_stereo_result=None,
            reasons=(
                "symmetric product graph admits atom-map correspondences with different edit semantics",
            ),
            provenance=_provenance(),
        )
    (
        centre_equivalent,
        attachment_equivalent,
        atom_state_equivalent,
        stereo_equivalent,
    ) = outcomes.pop()

    for equivalent, category in (
        (product_equivalent, "product"),
        (centre_equivalent, "reaction_centre"),
        (attachment_equivalent, "attachment_completion"),
        (atom_state_equivalent, "atom_state"),
        (stereo_equivalent, "stereo"),
    ):
        if not equivalent:
            mismatches.append(category)

    left_execution = ReactionExecutor().execute(left)
    right_execution = ReactionExecutor().execute(right)
    if not left_execution.success or not right_execution.success:
        if not left_execution.success:
            reasons.append(
                f"left execution failed: {left_execution.error.message if left_execution.error else 'unknown'}"
            )
        if not right_execution.success:
            reasons.append(
                f"right execution failed: {right_execution.error.message if right_execution.error else 'unknown'}"
            )
        return SemanticComparisonV1(
            state=ComparisonState.INDETERMINATE,
            exact_semantic_equivalence=None,
            equivalent_precursor_set=None,
            equivalent_reaction_centre=centre_equivalent,
            equivalent_attachment_completion=attachment_equivalent,
            equivalent_stereo_result=stereo_equivalent,
            mismatch_categories=tuple(mismatches),
            reasons=tuple(reasons),
            provenance=_provenance(),
        )

    precursor_comparison = compare_precursor_sets(
        left_execution.mapped_structures, right_execution.mapped_structures
    )
    precursor_equivalent = precursor_comparison.equivalent_precursor_set
    if precursor_equivalent is False:
        mismatches.append("precursor_set")
    exact = bool(
        product_exact
        and centre_equivalent
        and attachment_equivalent
        and atom_state_equivalent
        and stereo_equivalent
        and precursor_comparison.exact_semantic_equivalence
    )
    all_equivalent = bool(
        product_equivalent
        and centre_equivalent
        and attachment_equivalent
        and atom_state_equivalent
        and stereo_equivalent
        and precursor_equivalent
    )
    if all_equivalent and not exact:
        mismatches.extend(
            value for value in precursor_comparison.mismatch_categories if value not in mismatches
        )
        if not product_exact and "atom_map_renumbering" not in mismatches:
            mismatches.append("atom_map_renumbering")
    return SemanticComparisonV1(
        state=ComparisonState.EQUIVALENT if all_equivalent else ComparisonState.DIFFERENT,
        exact_semantic_equivalence=exact,
        equivalent_precursor_set=precursor_equivalent,
        equivalent_reaction_centre=centre_equivalent,
        equivalent_attachment_completion=attachment_equivalent,
        equivalent_stereo_result=stereo_equivalent,
        mismatch_categories=tuple(mismatches),
        reasons=tuple(reasons),
        provenance=_provenance(),
    )


def _diff_signature(value: GraphDiffV1 | None) -> str | None:
    if value is None:
        return None
    return json.dumps(value.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))


def compare_execution_results(
    left: ExecutionResultBase,
    right: ExecutionResultBase,
) -> SemanticComparisonV1:
    """Compare successful execution stages and reconstructed precursor graphs."""
    if not left.success or not right.success:
        reasons = tuple(
            f"{side} execution failed: {result.error.message if result.error else 'unknown'}"
            for side, result in (("left", left), ("right", right))
            if not result.success
        )
        return SemanticComparisonV1(
            state=ComparisonState.INDETERMINATE,
            exact_semantic_equivalence=None,
            equivalent_precursor_set=None,
            equivalent_reaction_centre=None,
            equivalent_attachment_completion=None,
            equivalent_stereo_result=None,
            reasons=reasons,
            provenance=_provenance(),
        )
    precursor = compare_precursor_sets(left.mapped_structures, right.mapped_structures)
    diff_equal = _diff_signature(left.graph_diff) == _diff_signature(right.graph_diff)
    exact = precursor.exact_semantic_equivalence and diff_equal
    mismatches = list(precursor.mismatch_categories)
    if not diff_equal:
        mismatches.append("graph_diff")
    return SemanticComparisonV1(
        state=(
            ComparisonState.EQUIVALENT
            if precursor.equivalent_precursor_set and diff_equal
            else ComparisonState.DIFFERENT
        ),
        exact_semantic_equivalence=bool(exact),
        equivalent_precursor_set=precursor.equivalent_precursor_set,
        equivalent_reaction_centre=diff_equal,
        equivalent_attachment_completion=diff_equal,
        equivalent_stereo_result=diff_equal,
        mismatch_categories=tuple(mismatches),
        provenance=_provenance(),
    )
