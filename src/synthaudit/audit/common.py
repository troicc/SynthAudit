"""Shared audit result and molecular inspection helpers."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any, Literal, cast

from pydantic import JsonValue
from rdkit import Chem

from synthaudit import __version__
from synthaudit.graph.atom_maps import atom_map_index, parse_mapped_molecule
from synthaudit.graph.sanitize import sanitize_copy
from synthaudit.schema.common import ProvenanceRecord
from synthaudit.schema.results import (
    CheckResultV1,
    CheckStatus,
    Severity,
    StageAuditResultV1,
)

AuditStage = Literal["structural", "reaction_centre", "completion", "stereo"]


def audit_provenance(component: str) -> tuple[ProvenanceRecord, ...]:
    return (
        ProvenanceRecord(
            source="synthaudit",
            source_version=__version__,
            adapter=component,
            adapter_version="1",
            license="Apache-2.0",
        ),
    )


def check(
    check_id: str,
    category: AuditStage,
    status: CheckStatus,
    message: str,
    *,
    severity: Severity | None = None,
    affected_atom_maps: Iterable[int] = (),
    evidence: dict[str, Any] | None = None,
    references: Sequence[str] = (),
    deterministic: bool = True,
) -> CheckResultV1:
    if severity is None:
        severity = {
            CheckStatus.PASS: Severity.INFO,
            CheckStatus.FAIL: Severity.ERROR,
            CheckStatus.WARNING: Severity.WARNING,
            CheckStatus.INDETERMINATE: Severity.WARNING,
            CheckStatus.UNAVAILABLE: Severity.INFO,
            CheckStatus.UNSUPPORTED: Severity.WARNING,
        }[status]
    return CheckResultV1(
        check_id=check_id,
        category=category,
        severity=severity,
        status=status,
        message=message,
        affected_atom_maps=tuple(sorted(set(affected_atom_maps))),
        evidence=cast(dict[str, JsonValue], evidence or {}),
        references=tuple(references),
        deterministic=deterministic,
    )


def stage_result(stage: AuditStage, checks: Sequence[CheckResultV1]) -> StageAuditResultV1:
    if any(item.status == CheckStatus.FAIL for item in checks):
        status = CheckStatus.FAIL
    elif any(item.status == CheckStatus.INDETERMINATE for item in checks):
        status = CheckStatus.INDETERMINATE
    elif any(item.status in {CheckStatus.WARNING, CheckStatus.UNSUPPORTED} for item in checks):
        status = CheckStatus.WARNING
    elif checks and all(item.status == CheckStatus.UNAVAILABLE for item in checks):
        status = CheckStatus.UNAVAILABLE
    else:
        status = CheckStatus.PASS
    return StageAuditResultV1(stage=stage, status=status, checks=tuple(checks))


def mapped_molecule(structures: str | Sequence[str]) -> Chem.Mol:
    values = (structures,) if isinstance(structures, str) else tuple(structures)
    if not values:
        raise ValueError("at least one mapped structure is required")
    return parse_mapped_molecule(".".join(values))


def sanitized_molecule(structures: str | Sequence[str]) -> Chem.Mol:
    molecule = mapped_molecule(structures)
    outcome = sanitize_copy(molecule)
    if not outcome.success:
        raise ValueError(outcome.error_message or "RDKit sanitation failed")
    return outcome.molecule


def map_numbers(structures: str | Sequence[str]) -> set[int]:
    return set(atom_map_index(mapped_molecule(structures)))


def canonical_structure_set(
    structures: Sequence[str],
    *,
    clear_maps: bool = False,
    clear_stereo: bool = False,
) -> tuple[str, ...]:
    result: list[str] = []
    for structure in structures:
        molecule = cast(Chem.Mol | None, Chem.MolFromSmiles(structure))
        if molecule is None:
            raise ValueError(f"cannot parse structure: {structure!r}")
        if clear_maps:
            for atom in molecule.GetAtoms():
                atom.SetAtomMapNum(0)
        if clear_stereo:
            Chem.RemoveStereochemistry(molecule)
        result.extend(
            Chem.MolToSmiles(molecule, canonical=True, isomericSmiles=not clear_stereo).split(".")
        )
    return tuple(sorted(result))


def cip_assignments(structures: Sequence[str]) -> dict[int, str]:
    molecule = sanitized_molecule(structures)
    Chem.AssignStereochemistry(molecule, cleanIt=True, force=True)
    return {
        atom.GetAtomMapNum(): atom.GetProp("_CIPCode")
        for atom in molecule.GetAtoms()
        if atom.HasProp("_CIPCode")
    }
