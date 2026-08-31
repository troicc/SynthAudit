"""Versioned models for independent novelty views and optional providers."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, JsonValue, model_validator

from synthaudit.schema.common import ProvenanceRecord, StrictModel
from synthaudit.schema.evidence import EvidenceAvailability


class FingerprintSpecificationV1(StrictModel):
    schema_version: Literal["synthaudit.fingerprint-specification/1"] = (
        "synthaudit.fingerprint-specification/1"
    )
    algorithm: str = Field(min_length=1)
    radius: int | None = Field(default=None, ge=0)
    bit_length: int = Field(gt=0)
    use_chirality: bool
    implementation: str = Field(min_length=1)
    implementation_version: str = Field(min_length=1)
    parameters: dict[str, JsonValue] = Field(default_factory=dict)


class NoveltyMetricV1(StrictModel):
    schema_version: Literal["synthaudit.novelty-metric/1"] = "synthaudit.novelty-metric/1"
    metric_id: str = Field(min_length=1)
    availability: EvidenceAvailability
    novelty: float | None = Field(default=None, ge=0, le=1)
    maximum_similarity: float | None = Field(default=None, ge=0, le=1)
    nearest_reference_ids: tuple[str, ...] = ()
    method: str = Field(min_length=1)
    interpretation: str = Field(min_length=1)
    missing_reasons: tuple[str, ...] = ()
    provenance: tuple[ProvenanceRecord, ...] = ()
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_availability_contract(self) -> NoveltyMetricV1:
        if self.availability == EvidenceAvailability.AVAILABLE:
            if self.novelty is None or self.maximum_similarity is None:
                raise ValueError("available novelty requires novelty and maximum similarity")
            if not self.nearest_reference_ids:
                raise ValueError("available novelty requires a nearest reference")
            if abs(self.novelty - (1.0 - self.maximum_similarity)) > 1e-9:
                raise ValueError("novelty must equal one minus maximum similarity")
        elif self.novelty is not None or self.maximum_similarity is not None:
            raise ValueError("unavailable novelty cannot contain numeric values")
        return self


class StructureNoveltyViewV1(StrictModel):
    product_morgan: NoveltyMetricV1
    precursor_morgan: NoveltyMetricV1
    product_scaffold: NoveltyMetricV1
    precursor_scaffold: NoveltyMetricV1


class ReactionDifferenceNoveltyViewV1(StrictModel):
    reaction_difference: NoveltyMetricV1
    changed_bond_and_atom: NoveltyMetricV1
    drfp: NoveltyMetricV1


class EditSemanticNoveltyViewV1(StrictModel):
    normalized_edit_signature: NoveltyMetricV1
    reaction_centre_neighbourhood: NoveltyMetricV1
    ring_change_profile: NoveltyMetricV1
    fragmentation_profile: NoveltyMetricV1
    attachment_profile: NoveltyMetricV1


class EmbeddingEvidenceV1(StrictModel):
    schema_version: Literal["synthaudit.embedding-evidence/1"] = "synthaudit.embedding-evidence/1"
    provider_id: str = Field(min_length=1)
    availability: EvidenceAvailability
    vector: tuple[float, ...] | None = None
    missing_reasons: tuple[str, ...] = ()
    provenance: tuple[ProvenanceRecord, ...] = ()

    @model_validator(mode="after")
    def validate_vector_contract(self) -> EmbeddingEvidenceV1:
        if self.availability == EvidenceAvailability.AVAILABLE:
            if self.vector is None or not self.vector:
                raise ValueError("available embedding requires a non-empty vector")
            if not self.provenance:
                raise ValueError("available embedding requires model/artifact provenance")
        elif self.vector is not None:
            raise ValueError("unavailable embedding cannot contain a vector")
        return self


class LearnedTransformationNoveltyViewV1(StrictModel):
    reactseq_meo: NoveltyMetricV1


class TaxonomyRecognitionV1(StrictModel):
    schema_version: Literal["synthaudit.taxonomy-recognition/1"] = (
        "synthaudit.taxonomy-recognition/1"
    )
    provider_id: str = Field(min_length=1)
    availability: EvidenceAvailability
    recognized: bool | None = None
    class_label: str | None = None
    provider_raw_score: float | None = None
    class_frequency: int | None = Field(default=None, ge=0)
    interpretation: str = Field(min_length=1)
    missing_reasons: tuple[str, ...] = ()
    provenance: tuple[ProvenanceRecord, ...] = ()
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_recognition_contract(self) -> TaxonomyRecognitionV1:
        if self.availability == EvidenceAvailability.AVAILABLE and self.recognized is None:
            raise ValueError("available taxonomy evidence requires recognized=true or false")
        if self.availability == EvidenceAvailability.AVAILABLE and not self.provenance:
            raise ValueError("available taxonomy evidence requires provider provenance")
        if self.availability != EvidenceAvailability.AVAILABLE and any(
            value is not None
            for value in (
                self.recognized,
                self.class_label,
                self.provider_raw_score,
                self.class_frequency,
            )
        ):
            raise ValueError("unavailable taxonomy evidence cannot contain provider outputs")
        return self


class MultiViewNoveltyResultV1(StrictModel):
    schema_version: Literal["synthaudit.multi-view-novelty/1"] = "synthaudit.multi-view-novelty/1"
    reaction_id: str = Field(min_length=1)
    corpus_id: str = Field(min_length=1)
    corpus_version: str = Field(min_length=1)
    primary_baseline: Literal["one_minus_maximum_reference_tanimoto"] = (
        "one_minus_maximum_reference_tanimoto"
    )
    structure_novelty: StructureNoveltyViewV1
    reaction_difference_novelty: ReactionDifferenceNoveltyViewV1
    edit_semantic_novelty: EditSemanticNoveltyViewV1
    learned_transformation_novelty: LearnedTransformationNoveltyViewV1
    taxonomy_recognition: TaxonomyRecognitionV1
    top_precedents: tuple[PrecedentHitV1, ...] = ()
    interpretations: tuple[str, ...] = ()
    notice: Literal[
        "SynthAudit estimates representation validity, corpus novelty and evidence-based plausibility. It does not establish experimental feasibility, yield, selectivity, safety or scalability."
    ] = (
        "SynthAudit estimates representation validity, corpus novelty and evidence-based "
        "plausibility. It does not establish experimental feasibility, yield, selectivity, "
        "safety or scalability."
    )
    provenance: tuple[ProvenanceRecord, ...] = ()


from synthaudit.precedent.models import PrecedentHitV1  # noqa: E402

MultiViewNoveltyResultV1.model_rebuild()
