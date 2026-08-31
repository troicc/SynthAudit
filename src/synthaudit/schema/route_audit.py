"""Versioned route-context evidence and audit outputs."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from synthaudit.schema.common import ProvenanceRecord, StrictModel
from synthaudit.schema.results import CheckResultV1, CheckStatus, ReactionAuditResultV1, Severity


class RouteStepEvidenceV1(StrictModel):
    """Optional, separately sourced evidence for one route step."""

    schema_version: Literal["synthaudit.route-step-evidence/1"] = "synthaudit.route-step-evidence/1"
    step_id: str = Field(min_length=1)
    calibrated_evidence_support_score: float | None = Field(default=None, ge=0, le=1)
    uncertainty: float | None = Field(default=None, ge=0)
    product_novelty: float | None = Field(default=None, ge=0, le=1)
    missing_reasons: tuple[str, ...] = ()
    support_interpretation: Literal[
        "Calibrated evidence support; not an experimental feasibility probability."
    ] = "Calibrated evidence support; not an experimental feasibility probability."
    novelty_interpretation: Literal["Corpus-relative novelty is independent of plausibility."] = (
        "Corpus-relative novelty is independent of plausibility."
    )
    provenance: tuple[ProvenanceRecord, ...] = ()

    @model_validator(mode="after")
    def validate_evidence(self) -> RouteStepEvidenceV1:
        values = (
            self.calibrated_evidence_support_score,
            self.uncertainty,
            self.product_novelty,
        )
        if any(value is not None for value in values) and not self.provenance:
            raise ValueError("numeric route-step evidence requires provenance")
        if all(value is None for value in values) and not self.missing_reasons:
            raise ValueError("empty route-step evidence requires explicit missing reasons")
        return self


class RouteReviewItemV1(StrictModel):
    review_id: str = Field(min_length=1)
    priority: int = Field(ge=1, le=4)
    category: Literal[
        "structural",
        "completion",
        "stereo",
        "condition",
        "novelty",
        "uncertainty",
        "continuity",
    ]
    step_ids: tuple[str, ...] = Field(min_length=1)
    reason: str = Field(min_length=1)
    deterministic: bool


class RouteStepAuditV1(StrictModel):
    step_id: str = Field(min_length=1)
    reaction_audit: ReactionAuditResultV1


class RouteAuditResultV1(StrictModel):
    schema_version: Literal["synthaudit.route-audit-result/1"] = "synthaudit.route-audit-result/1"
    route_id: str = Field(min_length=1)
    status: CheckStatus
    checks: tuple[CheckResultV1, ...] = Field(min_length=1)
    step_audits: tuple[RouteStepAuditV1, ...]
    minimum_step_support: float | None = Field(default=None, ge=0, le=1)
    maximum_uncertainty: float | None = Field(default=None, ge=0)
    maximum_uncertainty_steps: tuple[str, ...] = ()
    structural_blocking_steps: tuple[str, ...] = ()
    unresolved_completion_failures: tuple[str, ...] = ()
    stereo_sensitive_steps: tuple[str, ...] = ()
    high_novelty_key_steps: tuple[str, ...] = ()
    critical_condition_conflicts: tuple[str, ...] = ()
    expert_review_queue: tuple[RouteReviewItemV1, ...] = ()
    exploratory_naive_independence_score: float | None = Field(default=None, ge=0, le=1)
    exploratory_score_interpretation: (
        Literal["Exploratory naive independence product; not a route success probability."] | None
    ) = None
    score_aggregation_policy: Literal["independent_step_summaries_no_route_success_probability"] = (
        "independent_step_summaries_no_route_success_probability"
    )
    blocking: bool
    notice: Literal[
        "SynthAudit estimates representation validity, corpus novelty and evidence-based plausibility. It does not establish experimental feasibility, yield, selectivity, safety or scalability."
    ] = (
        "SynthAudit estimates representation validity, corpus novelty and evidence-based "
        "plausibility. It does not establish experimental feasibility, yield, selectivity, "
        "safety or scalability."
    )
    provenance: tuple[ProvenanceRecord, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_route_result(self) -> RouteAuditResultV1:
        if any(item.category != "route" for item in self.checks):
            raise ValueError("route audit checks must use the route category")
        step_ids = {item.step_id for item in self.step_audits}
        if len(step_ids) != len(self.step_audits):
            raise ValueError("route step-audit IDs must be unique")
        failed = any(item.status == CheckStatus.FAIL for item in self.checks)
        indeterminate = any(item.status == CheckStatus.INDETERMINATE for item in self.checks)
        warning = any(
            item.status in {CheckStatus.WARNING, CheckStatus.UNSUPPORTED} for item in self.checks
        )
        unavailable = all(item.status == CheckStatus.UNAVAILABLE for item in self.checks)
        expected_status = (
            CheckStatus.FAIL
            if failed
            else CheckStatus.INDETERMINATE
            if indeterminate
            else CheckStatus.WARNING
            if warning
            else CheckStatus.UNAVAILABLE
            if unavailable
            else CheckStatus.PASS
        )
        if self.status != expected_status:
            raise ValueError("route status must summarize check statuses")
        expected_blocking = bool(self.structural_blocking_steps) or any(
            item.status == CheckStatus.FAIL and item.severity == Severity.BLOCKING
            for item in self.checks
        )
        if self.blocking != expected_blocking:
            raise ValueError("route blocking flag must reflect blocking evidence")
        if self.maximum_uncertainty is None and self.maximum_uncertainty_steps:
            raise ValueError("maximum-uncertainty steps require a numeric maximum")
        if self.maximum_uncertainty is not None and not self.maximum_uncertainty_steps:
            raise ValueError("numeric maximum uncertainty requires its contributing steps")
        if self.exploratory_naive_independence_score is None:
            if self.exploratory_score_interpretation is not None:
                raise ValueError("exploratory interpretation requires an exploratory score")
        elif self.exploratory_score_interpretation is None:
            raise ValueError("exploratory independence score requires its non-probability label")
        for values in (
            self.maximum_uncertainty_steps,
            self.structural_blocking_steps,
            self.unresolved_completion_failures,
            self.stereo_sensitive_steps,
            self.high_novelty_key_steps,
        ):
            if len(values) != len(set(values)):
                raise ValueError("route summary step lists must not contain duplicates")
            if not set(values).issubset(step_ids):
                raise ValueError("route summary references a step without a step audit")
        if any(not set(item.step_ids).issubset(step_ids) for item in self.expert_review_queue):
            raise ValueError("expert-review item references an unknown route step")
        priorities = [item.priority for item in self.expert_review_queue]
        if priorities != sorted(priorities):
            raise ValueError("expert-review queue must be sorted by ascending priority")
        return self
