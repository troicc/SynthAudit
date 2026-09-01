"""Opt-in ReactionClassifier integration with explicit score semantics."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from importlib import metadata
from typing import Any, cast

from rdkit import Chem

from synthaudit.graph.executor import ReactionExecutor
from synthaudit.schema.reaction_ir import ReactionIRV1


class ReactionClassifierUnavailableError(RuntimeError):
    """Raised when ReactionClassifier is not installed."""


@dataclass(frozen=True)
class ReactionClassificationSummary:
    reaction_smiles: str
    confirmed_code: str | None
    confirmed_name: str | None
    neural_code: str | None
    neural_name: str | None
    neural_raw_confidence: float | None
    confirmed_by_template: bool
    provider: str
    provider_version: str | None
    notice: str = (
        "A confirmed class means that a bundled template reproduced the declared "
        "product. Neural confidence is not a calibrated feasibility probability."
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _without_maps(smiles: str) -> str:
    molecule = cast(Chem.Mol | None, Chem.MolFromSmiles(smiles))
    if molecule is None:
        raise ValueError(f"invalid SMILES while preparing classifier input: {smiles!r}")
    for atom in molecule.GetAtoms():
        atom.SetAtomMapNum(0)
    return Chem.MolToSmiles(molecule, canonical=True, isomericSmiles=True)


def reaction_ir_to_forward_smiles(reaction: ReactionIRV1) -> str:
    """Create the classifier's forward reaction string from a canonical ReactionIR."""

    if reaction.expected_precursors:
        precursor_smiles = tuple(item.mapped_smiles for item in reaction.expected_precursors)
    else:
        execution = ReactionExecutor().execute(reaction)
        if not execution.success:
            raise ValueError(
                "cannot classify a ReactionIR without expected precursors when execution fails"
            )
        precursor_smiles = execution.mapped_structures
    left = ".".join(sorted(_without_maps(item) for item in precursor_smiles))
    product = _without_maps(reaction.product.mapped_smiles)
    return f"{left}>>{product}"


def classify_reaction_ir(reaction: ReactionIRV1) -> ReactionClassificationSummary:
    """Classify one reaction only after the optional dependency is requested."""

    try:
        from reactionclassifier import ReactionClassifier  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ReactionClassifierUnavailableError(
            "ReactionClassifier is not installed. In the active environment run "
            "`uv pip install reactionclassifier` (or `pip install reactionclassifier`) and retry."
        ) from exc

    reaction_smiles = reaction_ir_to_forward_smiles(reaction)
    result = ReactionClassifier().classify(reaction_smiles)
    confidence_raw = getattr(result, "confidence", None)
    try:
        version = metadata.version("reactionclassifier")
    except metadata.PackageNotFoundError:
        version = None
    confirmed_code = getattr(result, "reaction_code", None)
    return ReactionClassificationSummary(
        reaction_smiles=reaction_smiles,
        confirmed_code=confirmed_code,
        confirmed_name=getattr(result, "reaction_name", None),
        neural_code=getattr(result, "neural_code", None),
        neural_name=getattr(result, "neural_name", None),
        neural_raw_confidence=(float(confidence_raw) if confidence_raw is not None else None),
        confirmed_by_template=confirmed_code is not None,
        provider="reactionclassifier",
        provider_version=version,
    )
