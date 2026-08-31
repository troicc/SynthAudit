"""Multi-view reaction novelty without plausibility conflation."""

# ruff: noqa: F401 -- TYPE_CHECKING imports document the lazy public API.

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from synthaudit.novelty.engine import MultiViewNoveltyEngine
    from synthaudit.novelty.models import (
        EditSemanticNoveltyViewV1,
        EmbeddingEvidenceV1,
        FingerprintSpecificationV1,
        LearnedTransformationNoveltyViewV1,
        MultiViewNoveltyResultV1,
        NoveltyMetricV1,
        ReactionDifferenceNoveltyViewV1,
        StructureNoveltyViewV1,
        TaxonomyRecognitionV1,
    )
    from synthaudit.novelty.providers import (
        CallableReactionClassProvider,
        MappingReactSeqMEOProvider,
        ReactionClassProvider,
        ReactSeqMEOEmbeddingProvider,
        UnavailableReactionClassProvider,
        UnavailableReactSeqMEOProvider,
    )

_EXPORTS = {
    "MultiViewNoveltyEngine": ("synthaudit.novelty.engine", "MultiViewNoveltyEngine"),
    "EditSemanticNoveltyViewV1": (
        "synthaudit.novelty.models",
        "EditSemanticNoveltyViewV1",
    ),
    "EmbeddingEvidenceV1": ("synthaudit.novelty.models", "EmbeddingEvidenceV1"),
    "FingerprintSpecificationV1": (
        "synthaudit.novelty.models",
        "FingerprintSpecificationV1",
    ),
    "LearnedTransformationNoveltyViewV1": (
        "synthaudit.novelty.models",
        "LearnedTransformationNoveltyViewV1",
    ),
    "MultiViewNoveltyResultV1": (
        "synthaudit.novelty.models",
        "MultiViewNoveltyResultV1",
    ),
    "NoveltyMetricV1": ("synthaudit.novelty.models", "NoveltyMetricV1"),
    "ReactionDifferenceNoveltyViewV1": (
        "synthaudit.novelty.models",
        "ReactionDifferenceNoveltyViewV1",
    ),
    "StructureNoveltyViewV1": ("synthaudit.novelty.models", "StructureNoveltyViewV1"),
    "TaxonomyRecognitionV1": ("synthaudit.novelty.models", "TaxonomyRecognitionV1"),
    "CallableReactionClassProvider": (
        "synthaudit.novelty.providers",
        "CallableReactionClassProvider",
    ),
    "MappingReactSeqMEOProvider": (
        "synthaudit.novelty.providers",
        "MappingReactSeqMEOProvider",
    ),
    "ReactionClassProvider": ("synthaudit.novelty.providers", "ReactionClassProvider"),
    "ReactSeqMEOEmbeddingProvider": (
        "synthaudit.novelty.providers",
        "ReactSeqMEOEmbeddingProvider",
    ),
    "UnavailableReactSeqMEOProvider": (
        "synthaudit.novelty.providers",
        "UnavailableReactSeqMEOProvider",
    ),
    "UnavailableReactionClassProvider": (
        "synthaudit.novelty.providers",
        "UnavailableReactionClassProvider",
    ),
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
