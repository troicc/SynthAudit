"""Independent multi-view novelty against a declared reference index."""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

from synthaudit import __version__
from synthaudit.novelty.fingerprints import (
    attachment_fingerprint,
    changed_bond_atom_fingerprint,
    edit_signature_fingerprint,
    fragmentation_fingerprint,
    morgan_fingerprint,
    precursor_structures,
    reaction_centre_fingerprint,
    reaction_difference_fingerprint,
    ring_change_fingerprint,
    scaffold_fingerprint,
    tanimoto,
)
from synthaudit.novelty.models import (
    EditSemanticNoveltyViewV1,
    EmbeddingEvidenceV1,
    LearnedTransformationNoveltyViewV1,
    MultiViewNoveltyResultV1,
    NoveltyMetricV1,
    ReactionDifferenceNoveltyViewV1,
    StructureNoveltyViewV1,
)
from synthaudit.novelty.providers import (
    ReactionClassProvider,
    ReactSeqMEOEmbeddingProvider,
    UnavailableReactionClassProvider,
    UnavailableReactSeqMEOProvider,
)
from synthaudit.precedent.index import ReferenceIndex
from synthaudit.precedent.models import ReferenceReactionV1
from synthaudit.precedent.retrieval import PrecedentRetriever
from synthaudit.schema.common import ProvenanceRecord
from synthaudit.schema.evidence import EvidenceAvailability
from synthaudit.schema.reaction_ir import ReactionIRV1

FingerprintFactory = Callable[[ReactionIRV1], Any | None]


class MultiViewNoveltyEngine:
    """Score multiple declared views; never emit an unbenchmarked composite."""

    def __init__(
        self,
        reference_index: ReferenceIndex,
        *,
        meo_provider: ReactSeqMEOEmbeddingProvider | None = None,
        class_provider: ReactionClassProvider | None = None,
        familiarity_similarity_threshold: float = 0.5,
        close_centre_similarity_threshold: float = 0.7,
    ) -> None:
        if not 0 <= familiarity_similarity_threshold <= 1:
            raise ValueError("familiarity similarity threshold must be in [0, 1]")
        if not 0 <= close_centre_similarity_threshold <= 1:
            raise ValueError("close-centre similarity threshold must be in [0, 1]")
        self.reference_index = reference_index
        self.meo_provider = meo_provider or UnavailableReactSeqMEOProvider()
        self.class_provider = class_provider or UnavailableReactionClassProvider()
        self.familiarity_similarity_threshold = familiarity_similarity_threshold
        self.close_centre_similarity_threshold = close_centre_similarity_threshold

    def _provenance(self, component: str) -> tuple[ProvenanceRecord, ...]:
        return (
            ProvenanceRecord(
                source=self.reference_index.manifest.corpus_id,
                source_version=self.reference_index.manifest.corpus_version,
                adapter=component,
                adapter_version=__version__,
                artifact_sha256=self.reference_index.manifest.records_sha256,
                license="; ".join(self.reference_index.manifest.source_licenses) or None,
            ),
        )

    def _unavailable_metric(
        self,
        metric_id: str,
        reason: str,
        *,
        availability: EvidenceAvailability = EvidenceAvailability.UNAVAILABLE,
        method: str = "one_minus_maximum_reference_tanimoto",
    ) -> NoveltyMetricV1:
        return NoveltyMetricV1(
            metric_id=metric_id,
            availability=availability,
            method=method,
            interpretation="Novelty evidence is unavailable for this view.",
            missing_reasons=(reason,),
            provenance=self._provenance(metric_id),
        )

    def _tanimoto_metric(
        self,
        metric_id: str,
        query: ReactionIRV1,
        factory: FingerprintFactory,
    ) -> NoveltyMetricV1:
        if not self.reference_index.records:
            return self._unavailable_metric(metric_id, "reference index is empty")
        try:
            query_fingerprint = factory(query)
        except Exception as exc:
            return self._unavailable_metric(
                metric_id,
                str(exc),
                availability=EvidenceAvailability.INDETERMINATE,
            )
        if query_fingerprint is None:
            return self._unavailable_metric(metric_id, "query has no applicable fingerprint")
        similarities: list[tuple[float, str]] = []
        errors: list[str] = []
        for reference in self.reference_index.records:
            try:
                fingerprint = factory(reference.reaction)
                if fingerprint is not None:
                    similarities.append(
                        (tanimoto(query_fingerprint, fingerprint), reference.source_reaction_id)
                    )
            except Exception as exc:
                errors.append(f"{reference.source_reaction_id}: {exc}")
        if not similarities:
            return self._unavailable_metric(metric_id, "no comparable reference fingerprint")
        maximum = max(value for value, _ in similarities)
        nearest = tuple(
            sorted(identifier for value, identifier in similarities if abs(value - maximum) < 1e-12)
        )
        return NoveltyMetricV1(
            metric_id=metric_id,
            availability=EvidenceAvailability.AVAILABLE,
            novelty=1.0 - maximum,
            maximum_similarity=maximum,
            nearest_reference_ids=nearest,
            method="one_minus_maximum_reference_tanimoto",
            interpretation=(
                "Lower values indicate a closer neighbour in this declared fingerprint view; "
                "this is corpus novelty, not plausibility."
            ),
            provenance=self._provenance(metric_id),
            metadata={
                "comparable_reference_count": len(similarities),
                "skipped_reference_errors": errors,
            },
        )

    @staticmethod
    def _normalized_cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float | None:
        if len(left) != len(right) or not left:
            return None
        norm_left = math.sqrt(sum(value * value for value in left))
        norm_right = math.sqrt(sum(value * value for value in right))
        if norm_left == 0 or norm_right == 0:
            return None
        cosine = sum(a * b for a, b in zip(left, right, strict=True)) / (norm_left * norm_right)
        return min(1.0, max(0.0, (cosine + 1.0) / 2.0))

    def _reference_embedding(self, reference: ReferenceReactionV1) -> EmbeddingEvidenceV1:
        if reference.reactseq_meo_embedding is not None:
            return EmbeddingEvidenceV1(
                provider_id="reference-index/stored-reactseq-meo",
                availability=EvidenceAvailability.AVAILABLE,
                vector=reference.reactseq_meo_embedding,
                provenance=(
                    reference.reactseq_meo_provenance
                    or self._provenance("stored-reactseq-meo-unverified-source")
                ),
            )
        return self.meo_provider.embed(reference.reaction)

    def _meo_metric(self, query: ReactionIRV1) -> NoveltyMetricV1:
        query_evidence = self.meo_provider.embed(query)
        method = "one_minus_maximum_normalized_cosine_similarity"
        if query_evidence.availability != EvidenceAvailability.AVAILABLE:
            return self._unavailable_metric(
                "learned.reactseq_meo",
                "; ".join(query_evidence.missing_reasons) or "query MEO embedding unavailable",
                availability=query_evidence.availability,
                method=method,
            )
        assert query_evidence.vector is not None
        similarities: list[tuple[float, str]] = []
        for reference in self.reference_index.records:
            evidence = self._reference_embedding(reference)
            if evidence.availability != EvidenceAvailability.AVAILABLE:
                continue
            assert evidence.vector is not None
            similarity = self._normalized_cosine(query_evidence.vector, evidence.vector)
            if similarity is not None:
                similarities.append((similarity, reference.source_reaction_id))
        if not similarities:
            return self._unavailable_metric(
                "learned.reactseq_meo",
                "no dimension-compatible reference MEO embeddings are available",
                method=method,
            )
        maximum = max(value for value, _ in similarities)
        nearest = tuple(
            sorted(identifier for value, identifier in similarities if abs(value - maximum) < 1e-12)
        )
        return NoveltyMetricV1(
            metric_id="learned.reactseq_meo",
            availability=EvidenceAvailability.AVAILABLE,
            novelty=1.0 - maximum,
            maximum_similarity=maximum,
            nearest_reference_ids=nearest,
            method=method,
            interpretation=(
                "ReactSeq MEO embedding distance is optional learned novelty evidence, not an "
                "experimental or calibrated plausibility estimate."
            ),
            provenance=(*query_evidence.provenance, *self._provenance("reactseq-meo-novelty")),
            metadata={"comparable_reference_count": len(similarities)},
        )

    def _interpretations(
        self,
        structure: StructureNoveltyViewV1,
        reaction_difference: ReactionDifferenceNoveltyViewV1,
        edit_semantic: EditSemanticNoveltyViewV1,
    ) -> tuple[str, ...]:
        structure_values = (
            structure.product_morgan.maximum_similarity,
            structure.precursor_morgan.maximum_similarity,
        )
        transformation = reaction_difference.reaction_difference.maximum_similarity
        centre = edit_semantic.reaction_centre_neighbourhood.maximum_similarity
        if any(value is None for value in (*structure_values, transformation)):
            return ("unavailable evidence",)
        structurally_familiar = all(
            value is not None and value >= self.familiarity_similarity_threshold
            for value in structure_values
        )
        transformation_familiar = bool(
            transformation is not None and transformation >= self.familiarity_similarity_threshold
        )
        interpretations: list[str] = []
        if structurally_familiar and transformation_familiar:
            interpretations.append("structurally familiar and transformation-familiar")
        elif not structurally_familiar and transformation_familiar:
            interpretations.append("structurally novel but transformation-familiar")
        elif structurally_familiar and not transformation_familiar:
            interpretations.append("structurally familiar but transformation-novel")
        elif centre is not None and centre >= self.close_centre_similarity_threshold:
            interpretations.append("novel with close reaction-centre precedent")
        else:
            interpretations.append("novel with no close precedent")
        return tuple(interpretations)

    def score(
        self, reaction: ReactionIRV1, *, top_k_precedents: int = 5
    ) -> MultiViewNoveltyResultV1:
        structure = StructureNoveltyViewV1(
            product_morgan=self._tanimoto_metric(
                "structure.product_morgan",
                reaction,
                lambda item: morgan_fingerprint(item.product.mapped_smiles),
            ),
            precursor_morgan=self._tanimoto_metric(
                "structure.precursor_morgan",
                reaction,
                lambda item: morgan_fingerprint(precursor_structures(item)),
            ),
            product_scaffold=self._tanimoto_metric(
                "structure.product_scaffold",
                reaction,
                lambda item: scaffold_fingerprint(item.product.mapped_smiles),
            ),
            precursor_scaffold=self._tanimoto_metric(
                "structure.precursor_scaffold",
                reaction,
                lambda item: scaffold_fingerprint(precursor_structures(item)),
            ),
        )
        reaction_difference = ReactionDifferenceNoveltyViewV1(
            reaction_difference=self._tanimoto_metric(
                "reaction_difference.synth_audit",
                reaction,
                reaction_difference_fingerprint,
            ),
            changed_bond_and_atom=self._tanimoto_metric(
                "reaction_difference.changed_bond_and_atom",
                reaction,
                changed_bond_atom_fingerprint,
            ),
            drfp=self._unavailable_metric(
                "reaction_difference.drfp",
                "optional DRFP provider is not configured",
            ),
        )
        edit_semantic = EditSemanticNoveltyViewV1(
            normalized_edit_signature=self._tanimoto_metric(
                "edit.normalized_signature",
                reaction,
                edit_signature_fingerprint,
            ),
            reaction_centre_neighbourhood=self._tanimoto_metric(
                "edit.reaction_centre_neighbourhood",
                reaction,
                reaction_centre_fingerprint,
            ),
            ring_change_profile=self._tanimoto_metric(
                "edit.ring_change_profile",
                reaction,
                ring_change_fingerprint,
            ),
            fragmentation_profile=self._tanimoto_metric(
                "edit.fragmentation_profile",
                reaction,
                fragmentation_fingerprint,
            ),
            attachment_profile=self._tanimoto_metric(
                "edit.attachment_profile",
                reaction,
                attachment_fingerprint,
            ),
        )
        learned = LearnedTransformationNoveltyViewV1(reactseq_meo=self._meo_metric(reaction))
        taxonomy = self.class_provider.classify(reaction, self.reference_index)
        precedents = PrecedentRetriever(self.reference_index).search(
            reaction, top_k=top_k_precedents
        )
        return MultiViewNoveltyResultV1(
            reaction_id=reaction.reaction_id,
            corpus_id=self.reference_index.manifest.corpus_id,
            corpus_version=self.reference_index.manifest.corpus_version,
            structure_novelty=structure,
            reaction_difference_novelty=reaction_difference,
            edit_semantic_novelty=edit_semantic,
            learned_transformation_novelty=learned,
            taxonomy_recognition=taxonomy,
            top_precedents=precedents.hits,
            interpretations=self._interpretations(structure, reaction_difference, edit_semantic),
            provenance=self._provenance("MultiViewNoveltyEngine"),
        )
