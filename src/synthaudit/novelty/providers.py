"""Optional learned-embedding and taxonomy provider boundaries."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Protocol

from synthaudit.novelty.models import EmbeddingEvidenceV1, TaxonomyRecognitionV1
from synthaudit.precedent.index import ReferenceIndex
from synthaudit.schema.common import ProvenanceRecord
from synthaudit.schema.evidence import EvidenceAvailability
from synthaudit.schema.reaction_ir import ReactionIRV1


class ReactSeqMEOEmbeddingProvider(Protocol):
    provider_id: str

    def embed(self, reaction: ReactionIRV1) -> EmbeddingEvidenceV1: ...


class ReactionClassProvider(Protocol):
    provider_id: str

    def classify(
        self,
        reaction: ReactionIRV1,
        reference_index: ReferenceIndex,
    ) -> TaxonomyRecognitionV1: ...


class UnavailableReactSeqMEOProvider:
    provider_id = "reactseq-meo/unavailable"

    def embed(self, reaction: ReactionIRV1) -> EmbeddingEvidenceV1:
        del reaction
        return EmbeddingEvidenceV1(
            provider_id=self.provider_id,
            availability=EvidenceAvailability.UNAVAILABLE,
            missing_reasons=(
                "no checksum-pinned ReactSeq checkpoint has been reproduced in the isolated runtime",
            ),
        )


class MappingReactSeqMEOProvider:
    """Use explicitly supplied embeddings without loading or inventing a model artifact."""

    def __init__(
        self,
        vectors: Mapping[str, tuple[float, ...]],
        *,
        provider_id: str,
        provenance: tuple[ProvenanceRecord, ...],
    ) -> None:
        if vectors and not provenance:
            raise ValueError("supplied MEO embeddings require artifact provenance")
        self._vectors = dict(vectors)
        self.provider_id = provider_id
        self._provenance = provenance

    def embed(self, reaction: ReactionIRV1) -> EmbeddingEvidenceV1:
        vector = self._vectors.get(reaction.reaction_id)
        if vector is None:
            return EmbeddingEvidenceV1(
                provider_id=self.provider_id,
                availability=EvidenceAvailability.UNAVAILABLE,
                missing_reasons=(f"no supplied embedding for {reaction.reaction_id}",),
                provenance=self._provenance,
            )
        return EmbeddingEvidenceV1(
            provider_id=self.provider_id,
            availability=EvidenceAvailability.AVAILABLE,
            vector=vector,
            provenance=self._provenance,
        )


class UnavailableReactionClassProvider:
    provider_id = "reaction-classifier/unavailable"

    def classify(
        self,
        reaction: ReactionIRV1,
        reference_index: ReferenceIndex,
    ) -> TaxonomyRecognitionV1:
        del reaction, reference_index
        return TaxonomyRecognitionV1(
            provider_id=self.provider_id,
            availability=EvidenceAvailability.UNAVAILABLE,
            interpretation="Reaction taxonomy evidence is unavailable.",
            missing_reasons=(
                "optional ReactionClassifier runtime and checkpoint were not explicitly configured",
            ),
        )


class CallableReactionClassProvider:
    """Adapt an explicitly injected classifier callable; never import a model implicitly."""

    def __init__(
        self,
        classify: Callable[[ReactionIRV1], tuple[str | None, float | None, bool]],
        *,
        provider_id: str,
        provenance: tuple[ProvenanceRecord, ...],
    ) -> None:
        if not provenance:
            raise ValueError("callable reaction classifier requires provider provenance")
        self._classify = classify
        self.provider_id = provider_id
        self._provenance = provenance

    def classify(
        self,
        reaction: ReactionIRV1,
        reference_index: ReferenceIndex,
    ) -> TaxonomyRecognitionV1:
        label, raw_score, recognized = self._classify(reaction)
        frequency = reference_index.class_frequency(label) if label is not None else None
        return TaxonomyRecognitionV1(
            provider_id=self.provider_id,
            availability=EvidenceAvailability.AVAILABLE,
            recognized=recognized,
            class_label=label,
            provider_raw_score=raw_score,
            class_frequency=frequency,
            interpretation=(
                "Provider recognized a reaction taxonomy label; raw score is not calibrated."
                if recognized
                else "Provider did not recognize a reaction taxonomy label."
            ),
            provenance=self._provenance,
            metadata={"provider_raw_score_is_calibrated_probability": False},
        )
