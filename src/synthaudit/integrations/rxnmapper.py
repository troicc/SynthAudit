"""Opt-in RXNMapper integration.

The mapper is deliberately not a core dependency. Mapping changes the source
representation and is therefore always explicit and provenance-bearing.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from importlib import metadata
from typing import Any


class MapperUnavailableError(RuntimeError):
    """Raised when RXNMapper is not installed."""


@dataclass(frozen=True)
class AtomMappingSummary:
    original_reaction_smiles: str
    mapped_reaction_smiles: str
    confidence: float | None
    provider: str
    provider_version: str | None
    notice: str = (
        "Atom mapping is a model-derived preprocessing step, not experimental "
        "validation or proof that the reaction is correct."
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _split_reaction(reaction_smiles: str) -> tuple[str, str, str]:
    text = reaction_smiles.strip()
    if not text:
        raise ValueError("reaction SMILES is empty")
    parts = text.split(">")
    if len(parts) != 3:
        raise ValueError(
            "reaction SMILES must use reactants>>product or reactants>reagents>product"
        )
    reactants, reagents, product = parts
    if not reactants or not product:
        raise ValueError("reaction SMILES requires non-empty reactants and product")
    return reactants, reagents, product


def map_reaction_smiles(reaction_smiles: str) -> AtomMappingSummary:
    """Map one reaction through RXNMapper after an explicit user request."""

    try:
        from rxnmapper import RXNMapper  # type: ignore[import-not-found]
    except ImportError as exc:
        raise MapperUnavailableError(
            "RXNMapper is not installed. In the active environment run "
            "`uv pip install rxnmapper` (or `pip install rxnmapper`) and retry."
        ) from exc

    reactants, reagents, product = _split_reaction(reaction_smiles)
    mapping_input = f"{reactants}>>{product}"
    mapper = RXNMapper()
    outputs = mapper.get_attention_guided_atom_maps([mapping_input])
    if not outputs:
        raise RuntimeError("RXNMapper returned no mapping result")
    first = outputs[0]
    mapped = str(first.get("mapped_rxn", ""))
    if ">>" not in mapped:
        raise RuntimeError("RXNMapper returned an invalid mapped reaction")
    mapped_reactants, mapped_product = mapped.split(">>", 1)
    confidence_raw = first.get("confidence")
    confidence = float(confidence_raw) if confidence_raw is not None else None
    try:
        version = metadata.version("rxnmapper")
    except metadata.PackageNotFoundError:
        version = None
    return AtomMappingSummary(
        original_reaction_smiles=reaction_smiles,
        mapped_reaction_smiles=f"{mapped_reactants}>{reagents}>{mapped_product}",
        confidence=confidence,
        provider="rxnmapper",
        provider_version=version,
    )
