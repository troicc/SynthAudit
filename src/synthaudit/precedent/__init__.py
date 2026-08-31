"""Versioned local precedent indexing and evidence-provider protocols."""

# ruff: noqa: F401 -- TYPE_CHECKING imports document the lazy public API.

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from synthaudit.precedent.index import ReferenceIndex
    from synthaudit.precedent.models import (
        ConditionEvidenceV1,
        PrecedentHitV1,
        PrecedentSearchResultV1,
        ProcedureEvidenceV1,
        ReferenceIndexArtifactV1,
        ReferenceIndexManifestV1,
        ReferenceReactionV1,
    )
    from synthaudit.precedent.providers import (
        ConditionEvidenceProvider,
        IndexConditionEvidenceProvider,
        LocalPrecedentEvidenceProvider,
        MappingProcedureEvidenceProvider,
        PrecedentEvidenceProvider,
        ProcedureEvidenceProvider,
        UnavailableConditionEvidenceProvider,
        UnavailableProcedureEvidenceProvider,
    )
    from synthaudit.precedent.retrieval import PrecedentRetriever

_EXPORTS = {
    "ReferenceIndex": ("synthaudit.precedent.index", "ReferenceIndex"),
    "ConditionEvidenceV1": ("synthaudit.precedent.models", "ConditionEvidenceV1"),
    "PrecedentHitV1": ("synthaudit.precedent.models", "PrecedentHitV1"),
    "PrecedentSearchResultV1": (
        "synthaudit.precedent.models",
        "PrecedentSearchResultV1",
    ),
    "ProcedureEvidenceV1": ("synthaudit.precedent.models", "ProcedureEvidenceV1"),
    "ReferenceIndexArtifactV1": (
        "synthaudit.precedent.models",
        "ReferenceIndexArtifactV1",
    ),
    "ReferenceIndexManifestV1": (
        "synthaudit.precedent.models",
        "ReferenceIndexManifestV1",
    ),
    "ReferenceReactionV1": ("synthaudit.precedent.models", "ReferenceReactionV1"),
    "ConditionEvidenceProvider": (
        "synthaudit.precedent.providers",
        "ConditionEvidenceProvider",
    ),
    "IndexConditionEvidenceProvider": (
        "synthaudit.precedent.providers",
        "IndexConditionEvidenceProvider",
    ),
    "LocalPrecedentEvidenceProvider": (
        "synthaudit.precedent.providers",
        "LocalPrecedentEvidenceProvider",
    ),
    "MappingProcedureEvidenceProvider": (
        "synthaudit.precedent.providers",
        "MappingProcedureEvidenceProvider",
    ),
    "PrecedentEvidenceProvider": (
        "synthaudit.precedent.providers",
        "PrecedentEvidenceProvider",
    ),
    "ProcedureEvidenceProvider": (
        "synthaudit.precedent.providers",
        "ProcedureEvidenceProvider",
    ),
    "UnavailableConditionEvidenceProvider": (
        "synthaudit.precedent.providers",
        "UnavailableConditionEvidenceProvider",
    ),
    "UnavailableProcedureEvidenceProvider": (
        "synthaudit.precedent.providers",
        "UnavailableProcedureEvidenceProvider",
    ),
    "PrecedentRetriever": ("synthaudit.precedent.retrieval", "PrecedentRetriever"),
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str) -> Any:
    try:
        module_name, attribute = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(name) from exc
    value = getattr(import_module(module_name), attribute)
    globals()[name] = value
    return value
