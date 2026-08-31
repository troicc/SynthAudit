"""Versioned standalone-report sidecar contracts."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from synthaudit.novelty.models import MultiViewNoveltyResultV1
from synthaudit.precedent.models import PrecedentSearchResultV1
from synthaudit.schema.common import ProvenanceRecord, StrictModel
from synthaudit.schema.reaction_ir import ReactionIRV1
from synthaudit.schema.results import ReactionAuditResultV1
from synthaudit.schema.route_audit import RouteAuditResultV1, RouteStepEvidenceV1
from synthaudit.schema.route_ir import RouteIRV1


class EvidenceReportItemV1(StrictModel):
    """A report-safe evidence item whose semantics cannot imply experimental success."""

    stage: Literal["reaction_centre", "completion", "stereo", "route_context"]
    availability: Literal["available", "unavailable", "indeterminate"]
    calibrated_evidence_support_score: float | None = Field(default=None, ge=0, le=1)
    uncertainty: float | None = Field(default=None, ge=0)
    abstained: bool
    abstention_reasons: tuple[str, ...] = ()
    model_id: str | None = None
    interpretation: Literal[
        "Evidence support and uncertainty; not an experimental feasibility probability."
    ] = "Evidence support and uncertainty; not an experimental feasibility probability."
    provenance: tuple[ProvenanceRecord, ...] = ()

    @model_validator(mode="after")
    def validate_availability(self) -> EvidenceReportItemV1:
        numeric = self.calibrated_evidence_support_score is not None or self.uncertainty is not None
        if self.availability == "available":
            if self.calibrated_evidence_support_score is None or not self.provenance:
                raise ValueError(
                    "available report evidence requires a calibrated score and provenance"
                )
        elif numeric:
            raise ValueError("unavailable or indeterminate evidence cannot contain numeric values")
        if self.abstained and not self.abstention_reasons:
            raise ValueError("abstained report evidence requires reasons")
        return self


class ReactionReportV1(StrictModel):
    schema_version: Literal["synthaudit.reaction-report/1"] = "synthaudit.reaction-report/1"
    reaction: ReactionIRV1
    audit: ReactionAuditResultV1
    novelty: MultiViewNoveltyResultV1 | None = None
    precedents: PrecedentSearchResultV1 | None = None
    evidence: tuple[EvidenceReportItemV1, ...] = ()
    model_versions: tuple[str, ...] = ()
    corpus_versions: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    notice: Literal[
        "SynthAudit estimates representation validity, corpus novelty and evidence-based plausibility. It does not establish experimental feasibility, yield, selectivity, safety or scalability."
    ] = (
        "SynthAudit estimates representation validity, corpus novelty and evidence-based "
        "plausibility. It does not establish experimental feasibility, yield, selectivity, "
        "safety or scalability."
    )
    provenance: tuple[ProvenanceRecord, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_identity(self) -> ReactionReportV1:
        if self.reaction.reaction_id != self.audit.reaction_id:
            raise ValueError("reaction report input and audit IDs must match")
        if self.novelty is not None and self.novelty.reaction_id != self.reaction.reaction_id:
            raise ValueError("reaction report novelty query ID must match")
        if (
            self.precedents is not None
            and self.precedents.query_reaction_id != self.reaction.reaction_id
        ):
            raise ValueError("reaction report precedent query ID must match")
        return self


class RouteReportV1(StrictModel):
    schema_version: Literal["synthaudit.route-report/1"] = "synthaudit.route-report/1"
    route: RouteIRV1
    audit: RouteAuditResultV1
    step_evidence: tuple[RouteStepEvidenceV1, ...] = ()
    model_versions: tuple[str, ...] = ()
    corpus_versions: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    notice: Literal[
        "SynthAudit estimates representation validity, corpus novelty and evidence-based plausibility. It does not establish experimental feasibility, yield, selectivity, safety or scalability."
    ] = (
        "SynthAudit estimates representation validity, corpus novelty and evidence-based "
        "plausibility. It does not establish experimental feasibility, yield, selectivity, "
        "safety or scalability."
    )
    provenance: tuple[ProvenanceRecord, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_identity(self) -> RouteReportV1:
        if self.route.route_id != self.audit.route_id:
            raise ValueError("route report input and audit IDs must match")
        route_steps = {step.step_id for step in self.route.steps}
        if any(item.step_id not in route_steps for item in self.step_evidence):
            raise ValueError("route report evidence references an unknown step")
        return self
