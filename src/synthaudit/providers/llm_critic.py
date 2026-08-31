"""Disabled-by-default, provider-neutral independent critic boundary."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal, Protocol

from pydantic import Field, model_validator

from synthaudit.schema.common import ProvenanceRecord, StrictModel
from synthaudit.schema.evidence import EvidenceAvailability
from synthaudit.schema.reaction_ir import ReactionIRV1


class CriticJudgement(StrEnum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    INDETERMINATE = "indeterminate"


class IndependentCriticRequestV1(StrictModel):
    schema_version: Literal["synthaudit.independent-critic-request/1"] = (
        "synthaudit.independent-critic-request/1"
    )
    request_id: str = Field(min_length=1)
    reaction: ReactionIRV1
    prompt_id: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    requested_samples: int = Field(default=3, ge=2, le=20)
    generation_provider_id: str | None = None


class CriticSampleV1(StrictModel):
    sample_index: int = Field(ge=0)
    judgement: CriticJudgement
    rationale: str = Field(min_length=1)
    raw_response: str = Field(min_length=1)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    reported_cost_usd: float = Field(ge=0)


class IndependentCriticEvidenceV1(StrictModel):
    schema_version: Literal["synthaudit.independent-critic-evidence/1"] = (
        "synthaudit.independent-critic-evidence/1"
    )
    request_id: str = Field(min_length=1)
    provider_id: str = Field(min_length=1)
    availability: EvidenceAvailability
    samples: tuple[CriticSampleV1, ...] = ()
    total_input_tokens: int = Field(default=0, ge=0)
    total_output_tokens: int = Field(default=0, ge=0)
    total_reported_cost_usd: float = Field(default=0, ge=0)
    missing_reasons: tuple[str, ...] = ()
    provenance: tuple[ProvenanceRecord, ...] = ()
    independent_from_generation_provider: bool | None = None
    sole_plausibility_source_permitted: Literal[False] = False

    @model_validator(mode="after")
    def validate_evidence(self) -> IndependentCriticEvidenceV1:
        if self.availability == EvidenceAvailability.AVAILABLE:
            if len(self.samples) < 2 or not self.provenance:
                raise ValueError(
                    "available critic evidence requires multiple samples and provenance"
                )
            if self.independent_from_generation_provider is not True:
                raise ValueError(
                    "available critic evidence must be independent from the generation provider"
                )
            if self.total_input_tokens != sum(item.input_tokens for item in self.samples):
                raise ValueError("critic input-token total does not match samples")
            if self.total_output_tokens != sum(item.output_tokens for item in self.samples):
                raise ValueError("critic output-token total does not match samples")
            expected_cost = sum(item.reported_cost_usd for item in self.samples)
            if abs(self.total_reported_cost_usd - expected_cost) > 1e-9:
                raise ValueError("critic cost total does not match samples")
        elif (
            self.samples
            or any(
                (
                    self.total_input_tokens,
                    self.total_output_tokens,
                    self.total_reported_cost_usd,
                )
            )
            or self.independent_from_generation_provider is not None
        ):
            raise ValueError("unavailable critic evidence cannot contain provider outputs")
        return self


class IndependentCriticProvider(Protocol):
    provider_id: str

    def review(self, request: IndependentCriticRequestV1) -> IndependentCriticEvidenceV1: ...


class DisabledIndependentCriticProvider:
    provider_id = "disabled-independent-critic"

    def review(self, request: IndependentCriticRequestV1) -> IndependentCriticEvidenceV1:
        return IndependentCriticEvidenceV1(
            request_id=request.request_id,
            provider_id=self.provider_id,
            availability=EvidenceAvailability.UNAVAILABLE,
            missing_reasons=("independent critic providers are disabled by default",),
        )
