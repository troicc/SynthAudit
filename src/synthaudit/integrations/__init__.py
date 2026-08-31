"""Explicit optional integrations used by the direct-use interface.

Nothing in this package is imported by the deterministic core at import time.
Heavy third-party models are loaded only after an explicit user action.
"""

from synthaudit.integrations.reactionclassifier import (
    ReactionClassificationSummary,
    classify_reaction_ir,
)
from synthaudit.integrations.rxnmapper import AtomMappingSummary, map_reaction_smiles

__all__ = [
    "AtomMappingSummary",
    "ReactionClassificationSummary",
    "classify_reaction_ir",
    "map_reaction_smiles",
]
