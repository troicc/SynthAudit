"""Schemas for reference corpora and multi-axis precedent evidence."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, JsonValue, model_validator

from synthaudit.novelty.models import FingerprintSpecificationV1
from synthaudit.schema.common import ProvenanceRecord, ReactionConditions, StrictModel
from synthaudit.schema.evidence import EvidenceAvailability
from synthaudit.schema.reaction_ir import ReactionIRV1


class ReferenceReactionV1(StrictModel):
    schema_version: Literal["synthaudit.reference-reaction/1"] = "synthaudit.reference-reaction/1"
    source_dataset: str = Field(min_length=1)
    source_reaction_id: str = Field(min_length=1)
    data_license_status: str = Field(min_length=1)
    reaction: ReactionIRV1
    reaction_class: str | None = None
    conditions: ReactionConditions | None = None
    reported_yield: float | None = Field(default=None, ge=0, le=100)
    reactseq_meo_embedding: tuple[float, ...] | None = None
    reactseq_meo_provenance: tuple[ProvenanceRecord, ...] = ()
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_embedding_provenance(self) -> ReferenceReactionV1:
        if self.reactseq_meo_embedding is not None and not self.reactseq_meo_provenance:
            raise ValueError("stored ReactSeq MEO embedding requires artifact provenance")
        if self.reactseq_meo_embedding is None and self.reactseq_meo_provenance:
            raise ValueError("embedding provenance cannot be stored without an embedding")
        return self


class ReferenceIndexManifestV1(StrictModel):
    schema_version: Literal["synthaudit.reference-index-manifest/1"] = (
        "synthaudit.reference-index-manifest/1"
    )
    corpus_id: str = Field(min_length=1)
    corpus_version: str = Field(min_length=1)
    record_count: int = Field(ge=0)
    records_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    fingerprint_specification: FingerprintSpecificationV1
    source_licenses: tuple[str, ...]
    provenance: tuple[ProvenanceRecord, ...] = ()


class ReferenceIndexArtifactV1(StrictModel):
    schema_version: Literal["synthaudit.reference-index/1"] = "synthaudit.reference-index/1"
    manifest: ReferenceIndexManifestV1
    records: tuple[ReferenceReactionV1, ...]

    @model_validator(mode="after")
    def validate_record_count(self) -> ReferenceIndexArtifactV1:
        if self.manifest.record_count != len(self.records):
            raise ValueError("reference-index record count does not match records")
        identities = [(item.source_dataset, item.source_reaction_id) for item in self.records]
        if len(identities) != len(set(identities)):
            raise ValueError("source reaction IDs must be unique within an index")
        return self


class PrecedentHitV1(StrictModel):
    schema_version: Literal["synthaudit.precedent-hit/1"] = "synthaudit.precedent-hit/1"
    source_dataset: str
    source_reaction_id: str
    data_license_status: str
    substrate_similarity: float | None = Field(default=None, ge=0, le=1)
    product_similarity: float | None = Field(default=None, ge=0, le=1)
    transformation_similarity: float | None = Field(default=None, ge=0, le=1)
    reaction_centre_similarity: float | None = Field(default=None, ge=0, le=1)
    leaving_group_similarity: float | None = Field(default=None, ge=0, le=1)
    stereo_similarity: float | None = Field(default=None, ge=0, le=1)
    similarity_methods: dict[str, str]
    fingerprint_specification: FingerprintSpecificationV1
    reaction_class: str | None = None
    conditions: ReactionConditions | None = None
    reported_yield: float | None = Field(default=None, ge=0, le=100)
    interpretation: tuple[str, ...] = ()
    missing_evidence: tuple[str, ...] = ()
    provenance: tuple[ProvenanceRecord, ...] = ()


class PrecedentSearchResultV1(StrictModel):
    schema_version: Literal["synthaudit.precedent-search/1"] = "synthaudit.precedent-search/1"
    query_reaction_id: str
    corpus_id: str
    corpus_version: str
    ranking_method: Literal[
        "lexicographic_transformation_centre_product_substrate_leaving_group_stereo"
    ] = "lexicographic_transformation_centre_product_substrate_leaving_group_stereo"
    hits: tuple[PrecedentHitV1, ...]
    notice: Literal[
        "Retrieved reactions are precedent support, not experimental validation of the query."
    ] = "Retrieved reactions are precedent support, not experimental validation of the query."
    provenance: tuple[ProvenanceRecord, ...] = ()


class ProcedureEvidenceV1(StrictModel):
    schema_version: Literal["synthaudit.procedure-evidence/1"] = "synthaudit.procedure-evidence/1"
    source_reaction_id: str
    availability: EvidenceAvailability
    procedure_text: str | None = None
    data_license_status: str | None = None
    missing_reasons: tuple[str, ...] = ()
    provenance: tuple[ProvenanceRecord, ...] = ()

    @model_validator(mode="after")
    def validate_availability_contract(self) -> ProcedureEvidenceV1:
        if self.availability == EvidenceAvailability.AVAILABLE:
            if not self.procedure_text or not self.data_license_status or not self.provenance:
                raise ValueError(
                    "available procedure evidence requires text, license status, and provenance"
                )
        elif self.procedure_text is not None or self.data_license_status is not None:
            raise ValueError("unavailable procedure evidence cannot contain procedure data")
        return self


class ConditionEvidenceV1(StrictModel):
    schema_version: Literal["synthaudit.condition-evidence/1"] = "synthaudit.condition-evidence/1"
    source_reaction_id: str
    availability: EvidenceAvailability
    conditions: ReactionConditions | None = None
    transfer_interpretation: str
    missing_reasons: tuple[str, ...] = ()
    provenance: tuple[ProvenanceRecord, ...] = ()

    @model_validator(mode="after")
    def validate_availability_contract(self) -> ConditionEvidenceV1:
        if self.availability == EvidenceAvailability.AVAILABLE:
            if self.conditions is None or not self.provenance:
                raise ValueError("available condition evidence requires conditions and provenance")
        elif self.conditions is not None:
            raise ValueError("unavailable condition evidence cannot contain conditions")
        return self
