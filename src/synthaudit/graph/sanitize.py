"""Strict and diagnostic RDKit sanitation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from rdkit import Chem


class SanitationMode(StrEnum):
    STRICT = "strict"
    DIAGNOSTIC = "diagnostic"


@dataclass(frozen=True)
class SanitationOutcome:
    success: bool
    molecule: Chem.Mol
    error_type: str | None = None
    error_message: str | None = None


def sanitize_copy(molecule: Chem.Mol) -> SanitationOutcome:
    """Sanitize a copy so a failing operation never mutates caller state."""
    candidate = Chem.Mol(molecule)
    try:
        candidate.UpdatePropertyCache(strict=False)
        Chem.SanitizeMol(candidate)
        Chem.AssignStereochemistry(candidate, cleanIt=False, force=True)
    except Exception as exc:  # RDKit exposes several exception classes by build
        return SanitationOutcome(
            success=False,
            molecule=candidate,
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
    return SanitationOutcome(success=True, molecule=candidate)


def mapped_fragments(molecule: Chem.Mol) -> tuple[str, ...]:
    """Serialize components canonically without changing map numbers."""
    fragments = Chem.GetMolFrags(molecule, asMols=True, sanitizeFrags=False)
    smiles = [Chem.MolToSmiles(item, canonical=True, isomericSmiles=True) for item in fragments]
    return tuple(sorted(smiles))
