"""Internal helpers shared by staged executors."""

from __future__ import annotations

from collections.abc import Iterable

from rdkit import Chem

from synthaudit import __version__
from synthaudit.graph.sanitize import mapped_fragments
from synthaudit.schema.common import ProvenanceRecord

BOND_TYPES: dict[float, Chem.BondType] = {
    1.0: Chem.BondType.SINGLE,
    1.5: Chem.BondType.AROMATIC,
    2.0: Chem.BondType.DOUBLE,
    3.0: Chem.BondType.TRIPLE,
}


class OperationError(ValueError):
    """An edit cannot be applied to the current graph."""


def bond_type(order: float) -> Chem.BondType:
    try:
        return BOND_TYPES[float(order)]
    except KeyError as exc:
        raise OperationError(f"unsupported bond order: {order}") from exc


def operation_labels(edits: Iterable[object]) -> tuple[str, ...]:
    labels: list[str] = []
    for index, edit in enumerate(edits):
        edit_type = str(getattr(edit, "edit_type", type(edit).__name__))
        edit_id = getattr(edit, "edit_id", None)
        labels.append(f"{index}:{edit_type}" + (f":{edit_id}" if edit_id else ""))
    return tuple(labels)


def executor_provenance(component: str) -> tuple[ProvenanceRecord, ...]:
    return (
        ProvenanceRecord(
            source="synthaudit",
            source_version=__version__,
            adapter=component,
            adapter_version="1",
            license="Apache-2.0",
        ),
    )


def safe_fragments(molecule: Chem.Mol, fallback: tuple[str, ...]) -> tuple[str, ...]:
    try:
        return mapped_fragments(molecule)
    except Exception:
        return fallback
