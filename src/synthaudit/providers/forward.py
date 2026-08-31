"""Optional forward-reaction provider boundary with artifact provenance."""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import Field, model_validator

from synthaudit.schema.common import ProvenanceRecord, ReactionConditions, StrictModel
from synthaudit.schema.evidence import EvidenceAvailability


class ForwardReactionRequestV1(StrictModel):
    schema_version: Literal["synthaudit.forward-reaction-request/1"] = (
        "synthaudit.forward-reaction-request/1"
    )
    request_id: str = Field(min_length=1)
    mapped_precursors: tuple[str, ...] = Field(min_length=1)
    target_product_mapped_smiles: str | None = None
    conditions: ReactionConditions | None = None
    top_k: int = Field(default=10, ge=1, le=100)


class ForwardProductCandidateV1(StrictModel):
    rank: int = Field(ge=1)
    product_smiles: str = Field(min_length=1)
    provider_raw_score: float | None = None
    raw_score_is_calibrated_probability: Literal[False] = False


class ForwardReactionEvidenceV1(StrictModel):
    schema_version: Literal["synthaudit.forward-reaction-evidence/1"] = (
        "synthaudit.forward-reaction-evidence/1"
    )
    request_id: str = Field(min_length=1)
    provider_id: str = Field(min_length=1)
    availability: EvidenceAvailability
    candidates: tuple[ForwardProductCandidateV1, ...] = ()
    target_rank: int | None = Field(default=None, ge=1)
    target_similarity: float | None = Field(default=None, ge=0, le=1)
    model_uncertainty: float | None = Field(default=None, ge=0)
    missing_reasons: tuple[str, ...] = ()
    provenance: tuple[ProvenanceRecord, ...] = ()
    interpretation: Literal[
        "Forward-model support is independent provider evidence, not experimental validation."
    ] = "Forward-model support is independent provider evidence, not experimental validation."

    @model_validator(mode="after")
    def validate_availability_contract(self) -> ForwardReactionEvidenceV1:
        if self.availability == EvidenceAvailability.AVAILABLE:
            if not self.candidates or not self.provenance:
                raise ValueError("available forward evidence requires candidates and provenance")
        elif (
            any(
                value is not None
                for value in (self.target_rank, self.target_similarity, self.model_uncertainty)
            )
            or self.candidates
        ):
            raise ValueError("unavailable forward evidence cannot contain model outputs")
        return self


class ForwardReactionProvider(Protocol):
    provider_id: str

    def predict(self, request: ForwardReactionRequestV1) -> ForwardReactionEvidenceV1: ...


class UnavailableForwardReactionProvider:
    provider_id = "unavailable-forward-provider"

    def predict(self, request: ForwardReactionRequestV1) -> ForwardReactionEvidenceV1:
        return ForwardReactionEvidenceV1(
            request_id=request.request_id,
            provider_id=self.provider_id,
            availability=EvidenceAvailability.UNAVAILABLE,
            missing_reasons=(
                "no checkpoint with verified license, digest, input format, and local inference "
                "was configured",
            ),
        )
