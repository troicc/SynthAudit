"""Measured offline conformance for pinned ReactSeq golden fixtures."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, cast

from pydantic import Field
from rdkit import Chem

from synthaudit.adapters.reactseq import (
    ReactSeqAdapter,
    ReactSeqAdapterInput,
    ReactSeqError,
)
from synthaudit.graph.atom_maps import atom_map_index, parse_mapped_molecule
from synthaudit.graph.executor import ReactionExecutor
from synthaudit.schema.common import StrictModel
from synthaudit.schema.edits import AttachFragmentEdit, BreakBondEdit, ChangeBondOrderEdit


class ReactSeqGoldenFixture(StrictModel):
    fixture_version: Literal["synthaudit.reactseq-golden/1"] = "synthaudit.reactseq-golden/1"
    fixture_id: str
    reactseq: str
    mapped_product_smiles: str
    expected_precursors: tuple[str, ...]
    expected_core_signatures: tuple[str, ...] = ()
    expected_attachment_maps: tuple[int, ...] = ()
    expected_leaving_groups: tuple[str, ...] = ()
    expected_charge_by_map: dict[int, int] = Field(default_factory=dict)
    expected_ring_count_change: int | None = None
    source_repository: str
    source_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    source_path: str
    source_line: int = Field(ge=1)


class ReactSeqConformanceCaseResult(StrictModel):
    fixture_id: str
    parse_success: bool
    execution_success: bool
    exact_precursor_reconstruction: bool | None
    reaction_centre_precision: float | None = Field(default=None, ge=0, le=1)
    reaction_centre_recall: float | None = Field(default=None, ge=0, le=1)
    attachment_point_accuracy: float | None = Field(default=None, ge=0, le=1)
    leaving_group_exact_match: bool | None
    charge_consistency: bool | None
    atom_map_preservation: bool | None
    stereo_preservation: bool | None
    ring_change_consistency: bool | None
    failure_category: str | None = None
    message: str | None = None


class ReactSeqConformanceSummary(StrictModel):
    schema_version: Literal["synthaudit.reactseq-conformance/1"] = (
        "synthaudit.reactseq-conformance/1"
    )
    fixture_count: int = Field(ge=0)
    parse_success_count: int = Field(ge=0)
    execution_success_count: int = Field(ge=0)
    exact_reconstruction_count: int = Field(ge=0)
    parse_success_rate: float | None = Field(default=None, ge=0, le=1)
    execution_success_rate: float | None = Field(default=None, ge=0, le=1)
    exact_reconstruction_rate: float | None = Field(default=None, ge=0, le=1)
    cases: tuple[ReactSeqConformanceCaseResult, ...]
    interpretation: str


def _canonical_unmapped_components(smiles_values: tuple[str, ...]) -> tuple[str, ...]:
    result: list[str] = []
    for value in smiles_values:
        molecule = cast(Chem.Mol | None, Chem.MolFromSmiles(value))
        if molecule is None:
            raise ValueError(f"cannot parse expected precursor SMILES: {value!r}")
        for atom in molecule.GetAtoms():
            atom.SetAtomMapNum(0)
        canonical = Chem.MolToSmiles(molecule, canonical=True, isomericSmiles=True)
        result.extend(canonical.split("."))
    return tuple(sorted(result))


def _core_signatures(reaction_input: ReactSeqAdapterInput) -> tuple[str, ...]:
    reaction = ReactSeqAdapter().to_reaction_ir(reaction_input)
    signatures: list[str] = []
    for edit in reaction.core_edits:
        left, right = sorted((edit.map_a, edit.map_b))
        if isinstance(edit, BreakBondEdit):
            signatures.append(f"break:{left}-{right}")
        elif isinstance(edit, ChangeBondOrderEdit):
            signatures.append(f"order:{left}-{right}:{edit.from_order:g}>{edit.to_order:g}")
        else:
            signatures.append(f"add:{left}-{right}:{edit.order:g}")
    return tuple(sorted(signatures))


def _set_overlap_metrics(
    actual: set[str] | set[int], expected: set[str] | set[int]
) -> tuple[float, float]:
    if not actual and not expected:
        return 1.0, 1.0
    intersection = len(actual & expected)
    precision = intersection / len(actual) if actual else 0.0
    recall = intersection / len(expected) if expected else 1.0
    return precision, recall


def _evaluate_fixture(fixture: ReactSeqGoldenFixture) -> ReactSeqConformanceCaseResult:
    adapter_input = ReactSeqAdapterInput(
        reactseq=fixture.reactseq,
        mapped_product_smiles=fixture.mapped_product_smiles,
        reaction_id=fixture.fixture_id,
    )
    try:
        normalized = ReactSeqAdapter().normalize(adapter_input)
    except ReactSeqError as exc:
        return ReactSeqConformanceCaseResult(
            fixture_id=fixture.fixture_id,
            parse_success=False,
            execution_success=False,
            exact_precursor_reconstruction=None,
            leaving_group_exact_match=None,
            charge_consistency=None,
            atom_map_preservation=None,
            stereo_preservation=None,
            ring_change_consistency=None,
            failure_category=exc.code,
            message=str(exc),
        )
    execution = ReactionExecutor().execute(normalized.reaction_ir)
    actual_core = set(_core_signatures(adapter_input))
    expected_core = set(fixture.expected_core_signatures)
    centre_precision, centre_recall = _set_overlap_metrics(actual_core, expected_core)
    actual_attachment_maps = {
        connection.product_atom_map
        for edit in normalized.reaction_ir.attachment_edits
        if isinstance(edit, AttachFragmentEdit)
        for connection in edit.connections
    } | {
        edit.target_atom_map
        for edit in normalized.reaction_ir.attachment_edits
        if isinstance(edit, AttachFragmentEdit)
        if edit.target_atom_map is not None
    }
    attachment_precision, attachment_recall = _set_overlap_metrics(
        actual_attachment_maps, set(fixture.expected_attachment_maps)
    )
    attachment_accuracy = (attachment_precision + attachment_recall) / 2
    actual_leaving_groups = tuple(
        str(edit.metadata["source_fragment"])
        for edit in normalized.reaction_ir.attachment_edits
        if "source_fragment" in edit.metadata
    )
    leaving_group_match = (
        _canonical_unmapped_components(actual_leaving_groups)
        == _canonical_unmapped_components(fixture.expected_leaving_groups)
        if fixture.expected_leaving_groups
        else None
    )
    if not execution.success:
        return ReactSeqConformanceCaseResult(
            fixture_id=fixture.fixture_id,
            parse_success=True,
            execution_success=False,
            exact_precursor_reconstruction=False,
            reaction_centre_precision=centre_precision,
            reaction_centre_recall=centre_recall,
            attachment_point_accuracy=attachment_accuracy,
            leaving_group_exact_match=leaving_group_match,
            charge_consistency=None,
            atom_map_preservation=False,
            stereo_preservation=None,
            ring_change_consistency=None,
            failure_category=execution.error.error_type if execution.error else "execution_error",
            message=execution.error.message if execution.error else None,
        )

    actual_precursors = _canonical_unmapped_components(execution.mapped_structures)
    expected_precursors = _canonical_unmapped_components(fixture.expected_precursors)
    output_maps = set(atom_map_index(parse_mapped_molecule(".".join(execution.mapped_structures))))
    product_maps = set(atom_map_index(parse_mapped_molecule(fixture.mapped_product_smiles)))
    exact = actual_precursors == expected_precursors
    output_molecule = parse_mapped_molecule(".".join(execution.mapped_structures))
    charge_consistency = (
        all(
            output_molecule.GetAtomWithIdx(
                atom_map_index(output_molecule)[atom_map]
            ).GetFormalCharge()
            == expected_charge
            for atom_map, expected_charge in fixture.expected_charge_by_map.items()
        )
        if fixture.expected_charge_by_map
        else None
    )
    has_stereo_expectation = any(
        any(marker in precursor for marker in ("@", "/", "\\"))
        for precursor in fixture.expected_precursors
    )
    ring_consistency = None
    if fixture.expected_ring_count_change is not None and execution.graph_diff is not None:
        ring_consistency = (
            execution.graph_diff.ring_count_after - execution.graph_diff.ring_count_before
            == fixture.expected_ring_count_change
        )
    return ReactSeqConformanceCaseResult(
        fixture_id=fixture.fixture_id,
        parse_success=True,
        execution_success=True,
        exact_precursor_reconstruction=exact,
        reaction_centre_precision=centre_precision,
        reaction_centre_recall=centre_recall,
        attachment_point_accuracy=attachment_accuracy,
        leaving_group_exact_match=leaving_group_match,
        charge_consistency=charge_consistency,
        atom_map_preservation=product_maps <= output_maps,
        stereo_preservation=exact if has_stereo_expectation else None,
        ring_change_consistency=ring_consistency,
        failure_category=None if exact else "precursor_mismatch",
    )


def run_reactseq_conformance(path: str | Path) -> ReactSeqConformanceSummary:
    """Run actual fixtures and report only directly measured small-set rates."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    fixtures = tuple(ReactSeqGoldenFixture.model_validate(item) for item in raw)
    cases = tuple(_evaluate_fixture(fixture) for fixture in fixtures)
    count = len(cases)
    parse_count = sum(case.parse_success for case in cases)
    execution_count = sum(case.execution_success for case in cases)
    exact_count = sum(case.exact_precursor_reconstruction is True for case in cases)
    return ReactSeqConformanceSummary(
        fixture_count=count,
        parse_success_count=parse_count,
        execution_success_count=execution_count,
        exact_reconstruction_count=exact_count,
        parse_success_rate=parse_count / count if count else None,
        execution_success_rate=execution_count / count if count else None,
        exact_reconstruction_rate=exact_count / count if count else None,
        cases=cases,
        interpretation=(
            "Descriptive results for committed pinned fixtures only; they are not a "
            "population benchmark or evidence of experimental feasibility."
        ),
    )
