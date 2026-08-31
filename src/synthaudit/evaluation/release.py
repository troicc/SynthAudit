"""Deterministic release-evaluation manifest with fail-closed research claims."""

from __future__ import annotations

import hashlib
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Literal, TypeAlias

from pydantic import Field, model_validator

from synthaudit import __version__
from synthaudit.adapters.reactseq import ReactSeqAdapter, ReactSeqAdapterInput
from synthaudit.counterfactuals import (
    CounterfactualBenchmarkValidationV1,
    validate_benchmark_artifacts,
)
from synthaudit.evaluation.evidence_model_smoke import (
    EvidenceModelContractSmokeV1,
    run_evidence_model_contract_smoke,
)
from synthaudit.evaluation.reactseq_conformance import (
    ReactSeqConformanceSummary,
    run_reactseq_conformance,
)
from synthaudit.evaluation.route_prompt_smoke import (
    RoutePromptContractSmokeV1,
    run_route_prompt_contract_smoke,
)
from synthaudit.graph.semantic_hash import reaction_ir_semantic_hash
from synthaudit.prompting import (
    PromptBenchmarkValidationV1,
    validate_prompt_benchmark_artifacts,
)
from synthaudit.schema.common import ProvenanceRecord, StrictModel

ResearchQuestionId: TypeAlias = Literal["RQ1", "RQ2", "RQ3", "RQ4", "RQ5", "RQ6", "RQ7"]
RequiredMetricId: TypeAlias = Literal[
    "parse_success",
    "exact_precursor_reconstruction",
    "reaction_centre_precision",
    "reaction_centre_recall",
    "reaction_centre_f1",
    "completion_accuracy",
    "leaving_group_accuracy",
    "stereo_retention",
    "auroc",
    "auprc",
    "brier_score",
    "expected_calibration_error",
    "false_rejection_rate",
    "false_acceptance_rate",
    "selective_risk",
    "coverage",
    "high_novelty_false_rejection_rate",
]

REQUIRED_RESEARCH_QUESTIONS: tuple[ResearchQuestionId, ...] = (
    "RQ1",
    "RQ2",
    "RQ3",
    "RQ4",
    "RQ5",
    "RQ6",
    "RQ7",
)
REQUIRED_METRICS: tuple[RequiredMetricId, ...] = (
    "parse_success",
    "exact_precursor_reconstruction",
    "reaction_centre_precision",
    "reaction_centre_recall",
    "reaction_centre_f1",
    "completion_accuracy",
    "leaving_group_accuracy",
    "stereo_retention",
    "auroc",
    "auprc",
    "brier_score",
    "expected_calibration_error",
    "false_rejection_rate",
    "false_acceptance_rate",
    "selective_risk",
    "coverage",
    "high_novelty_false_rejection_rate",
)


class EvaluationAvailability(StrEnum):
    FIXTURE_OBSERVATION = "fixture_observation"
    NOT_RUN = "not_run"


class ResearchQuestionStatusV1(StrictModel):
    question_id: ResearchQuestionId
    status: EvaluationAvailability
    evidence_summary: str = Field(min_length=1)
    blocking_requirements: tuple[str, ...] = ()
    reproduction_command: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_status(self) -> ResearchQuestionStatusV1:
        if self.status == EvaluationAvailability.NOT_RUN and not self.blocking_requirements:
            raise ValueError("not-run research questions require explicit blocking requirements")
        return self


class RequiredMetricStatusV1(StrictModel):
    metric_id: RequiredMetricId
    status: EvaluationAvailability
    value: float | None = Field(default=None, ge=0, le=1)
    numerator: int | None = Field(default=None, ge=0)
    denominator: int | None = Field(default=None, ge=1)
    sample_count: int | None = Field(default=None, ge=1)
    unit: str | None = None
    scope: Literal["software_verification_fixture", "research_evaluation"]
    confidence_interval_95: tuple[float, float] | None = None
    bootstrap_unit: Literal["parent_reaction_or_route_id"] = "parent_reaction_or_route_id"
    bootstrap_status: Literal["not_run_fixture_scope", "not_run_missing_research_data"]
    reason: str = Field(min_length=1)
    reproduction_command: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_availability(self) -> RequiredMetricStatusV1:
        has_counts = self.numerator is not None or self.denominator is not None
        if has_counts and (self.numerator is None or self.denominator is None):
            raise ValueError("metric numerator and denominator must be supplied together")
        if (
            self.numerator is not None
            and self.denominator is not None
            and self.numerator > self.denominator
        ):
            raise ValueError("metric numerator cannot exceed its denominator")
        if (
            self.value is not None
            and self.numerator is not None
            and self.denominator is not None
            and abs(self.value - self.numerator / self.denominator) > 1e-12
        ):
            raise ValueError("metric value must equal its declared numerator/denominator")
        if self.status == EvaluationAvailability.FIXTURE_OBSERVATION:
            if self.value is None or self.sample_count is None or self.unit is None:
                raise ValueError("fixture observations require value, sample count, and unit")
            if self.scope != "software_verification_fixture":
                raise ValueError("fixture observations cannot be labelled as research evaluation")
            if self.bootstrap_status != "not_run_fixture_scope":
                raise ValueError("fixture observations cannot claim a research bootstrap")
        else:
            if self.value is not None or has_counts or self.sample_count is not None:
                raise ValueError("not-run metrics cannot contain numerical results")
            if self.scope != "research_evaluation":
                raise ValueError("not-run research metrics require research-evaluation scope")
            if self.bootstrap_status != "not_run_missing_research_data":
                raise ValueError(
                    "not-run metrics require an explicit missing-data bootstrap status"
                )
        if self.confidence_interval_95 is not None:
            raise ValueError(
                "Phase 12 does not publish confidence intervals for fixture observations"
            )
        return self


class ReleaseEvaluationManifestV1(StrictModel):
    schema_version: Literal["synthaudit.release-evaluation/1"] = "synthaudit.release-evaluation/1"
    evaluation_id: Literal["synthaudit-v1-offline-release-evaluation"] = (
        "synthaudit-v1-offline-release-evaluation"
    )
    release_version: Literal["1.0.0"] = "1.0.0"
    evaluation_date: date
    evaluation_scope: Literal["offline_software_verification_fixtures"] = (
        "offline_software_verification_fixtures"
    )
    research_metrics_status: Literal["not_run"] = "not_run"
    fixture_results_are_population_metrics: Literal[False] = False
    experimental_feasibility_established: Literal[False] = False
    source_artifact_sha256: dict[str, str] = Field(min_length=1)
    traversal_pair_semantically_equivalent: bool
    counterfactual_validation: CounterfactualBenchmarkValidationV1
    prompt_validation: PromptBenchmarkValidationV1
    reactseq_conformance: ReactSeqConformanceSummary
    route_prompt_contract: RoutePromptContractSmokeV1
    evidence_model_contract: EvidenceModelContractSmokeV1
    research_questions: tuple[ResearchQuestionStatusV1, ...]
    required_metrics: tuple[RequiredMetricStatusV1, ...]
    notice: Literal[
        "SynthAudit estimates representation validity, corpus novelty and evidence-based plausibility. It does not establish experimental feasibility, yield, selectivity, safety or scalability."
    ] = (
        "SynthAudit estimates representation validity, corpus novelty and evidence-based "
        "plausibility. It does not establish experimental feasibility, yield, selectivity, "
        "safety or scalability."
    )
    provenance: tuple[ProvenanceRecord, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_complete_contract(self) -> ReleaseEvaluationManifestV1:
        if tuple(item.question_id for item in self.research_questions) != (
            REQUIRED_RESEARCH_QUESTIONS
        ):
            raise ValueError("release evaluation must contain ordered RQ1-RQ7 status entries")
        if tuple(item.metric_id for item in self.required_metrics) != REQUIRED_METRICS:
            raise ValueError("release evaluation must contain every required metric exactly once")
        if any(
            len(value) != 64 or set(value) - set("0123456789abcdef")
            for value in self.source_artifact_sha256.values()
        ):
            raise ValueError("source artifact hashes must be SHA-256 hex digests")
        return self


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _traversal_pair_equivalent() -> bool:
    mapped_product = "[CH3:1][CH2:2][OH:3]"
    first = ReactSeqAdapter().to_reaction_ir(
        ReactSeqAdapterInput(
            reactseq="CCO>>>C!CO<><[Br:1]>",
            mapped_product_smiles=mapped_product,
        )
    )
    second = ReactSeqAdapter().to_reaction_ir(
        ReactSeqAdapterInput(
            reactseq="OCC>>>OC!C<[Br:1]><>",
            mapped_product_smiles=mapped_product,
        )
    )
    return reaction_ir_semantic_hash(first) == reaction_ir_semantic_hash(second)


def _mean(values: list[float]) -> float:
    if not values:
        raise ValueError("cannot summarize an empty fixture metric")
    return sum(values) / len(values)


def _fixture_metric(
    metric_id: RequiredMetricId,
    *,
    value: float,
    sample_count: int,
    unit: str,
    reason: str,
    numerator: int | None = None,
    denominator: int | None = None,
) -> RequiredMetricStatusV1:
    return RequiredMetricStatusV1(
        metric_id=metric_id,
        status=EvaluationAvailability.FIXTURE_OBSERVATION,
        value=value,
        numerator=numerator,
        denominator=denominator,
        sample_count=sample_count,
        unit=unit,
        scope="software_verification_fixture",
        bootstrap_status="not_run_fixture_scope",
        reason=reason,
        reproduction_command="make release-evaluation",
    )


def _not_run_metric(metric_id: RequiredMetricId, reason: str) -> RequiredMetricStatusV1:
    return RequiredMetricStatusV1(
        metric_id=metric_id,
        status=EvaluationAvailability.NOT_RUN,
        scope="research_evaluation",
        bootstrap_status="not_run_missing_research_data",
        reason=reason,
        reproduction_command="make release-evaluation",
    )


def _required_metric_statuses(
    conformance: ReactSeqConformanceSummary,
) -> tuple[RequiredMetricStatusV1, ...]:
    centre_precision = [
        item.reaction_centre_precision
        for item in conformance.cases
        if item.reaction_centre_precision is not None
    ]
    centre_recall = [
        item.reaction_centre_recall
        for item in conformance.cases
        if item.reaction_centre_recall is not None
    ]
    centre_f1 = [
        0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)
        for precision, recall in zip(centre_precision, centre_recall, strict=True)
    ]
    leaving_group = [
        item.leaving_group_exact_match
        for item in conformance.cases
        if item.leaving_group_exact_match is not None
    ]
    fixture_reason = (
        "Observed only on three committed, pinned ReactSeq demo fixtures; not a population "
        "estimate or experimental result."
    )
    missing_evidence_labels = (
        "No licensed, adjudicated evidence-support evaluation set or selected calibrated research "
        "model is configured."
    )
    return (
        _fixture_metric(
            "parse_success",
            value=conformance.parse_success_rate or 0.0,
            numerator=conformance.parse_success_count,
            denominator=conformance.fixture_count,
            sample_count=conformance.fixture_count,
            unit="fixture_rate",
            reason=fixture_reason,
        ),
        _fixture_metric(
            "exact_precursor_reconstruction",
            value=conformance.exact_reconstruction_rate or 0.0,
            numerator=conformance.exact_reconstruction_count,
            denominator=conformance.fixture_count,
            sample_count=conformance.fixture_count,
            unit="fixture_rate",
            reason=fixture_reason,
        ),
        _fixture_metric(
            "reaction_centre_precision",
            value=_mean(centre_precision),
            sample_count=len(centre_precision),
            unit="mean_fixture_case_score",
            reason=fixture_reason,
        ),
        _fixture_metric(
            "reaction_centre_recall",
            value=_mean(centre_recall),
            sample_count=len(centre_recall),
            unit="mean_fixture_case_score",
            reason=fixture_reason,
        ),
        _fixture_metric(
            "reaction_centre_f1",
            value=_mean(centre_f1),
            sample_count=len(centre_f1),
            unit="mean_fixture_case_score",
            reason=fixture_reason,
        ),
        _not_run_metric(
            "completion_accuracy",
            "No licensed completion-support evaluation set with a frozen target definition is configured.",
        ),
        _fixture_metric(
            "leaving_group_accuracy",
            value=sum(leaving_group) / len(leaving_group),
            numerator=sum(leaving_group),
            denominator=len(leaving_group),
            sample_count=len(leaving_group),
            unit="fixture_exact_match_rate",
            reason=fixture_reason,
        ),
        _not_run_metric(
            "stereo_retention",
            "The three pinned ReactSeq fixtures contain no evaluable stereo-retention target.",
        ),
        _not_run_metric("auroc", missing_evidence_labels),
        _not_run_metric("auprc", missing_evidence_labels),
        _not_run_metric("brier_score", missing_evidence_labels),
        _not_run_metric("expected_calibration_error", missing_evidence_labels),
        _not_run_metric("false_rejection_rate", missing_evidence_labels),
        _not_run_metric("false_acceptance_rate", missing_evidence_labels),
        _not_run_metric("selective_risk", missing_evidence_labels),
        _not_run_metric("coverage", missing_evidence_labels),
        _not_run_metric(
            "high_novelty_false_rejection_rate",
            "No licensed recorded-reaction test set with frozen novelty strata and adjudicated support labels is configured.",
        ),
    )


def _research_question_statuses() -> tuple[ResearchQuestionStatusV1, ...]:
    return (
        ResearchQuestionStatusV1(
            question_id="RQ1",
            status=EvaluationAvailability.FIXTURE_OBSERVATION,
            evidence_summary=(
                "One authored pair of alternate product traversals normalizes to an equal "
                "ReactionIR semantic hash; three pinned upstream demo fixtures also parse, "
                "execute, and reconstruct exactly. This is fixture-only evidence."
            ),
            reproduction_command="make release-evaluation reactseq-conformance-small",
        ),
        ResearchQuestionStatusV1(
            question_id="RQ2",
            status=EvaluationAvailability.NOT_RUN,
            evidence_summary="Error prevalence is not estimated from designed counterfactual counts.",
            blocking_requirements=(
                "licensed representative reaction sample",
                "frozen stage-error annotation protocol",
                "parent-group bootstrap",
            ),
            reproduction_command="make release-evaluation",
        ),
        ResearchQuestionStatusV1(
            question_id="RQ3",
            status=EvaluationAvailability.NOT_RUN,
            evidence_summary="ReactSeq_MEO complementarity has not been measured.",
            blocking_requirements=(
                "licensed downloadable ReactSeq checkpoint",
                "reproduced embedding extraction environment",
                "frozen novelty corpus and comparison protocol",
            ),
            reproduction_command="make release-evaluation",
        ),
        ResearchQuestionStatusV1(
            question_id="RQ4",
            status=EvaluationAvailability.NOT_RUN,
            evidence_summary="High-novelty false rejection has not been measured.",
            blocking_requirements=(
                "licensed recorded-reaction test set",
                "adjudicated support labels",
                "selected and calibrated evidence models",
            ),
            reproduction_command="make release-evaluation",
        ),
        ResearchQuestionStatusV1(
            question_id="RQ5",
            status=EvaluationAvailability.NOT_RUN,
            evidence_summary=(
                "Forty deterministic prompt variants exist, but no prompt-capable provider was run."
            ),
            blocking_requirements=(
                "versioned prompt-capable model providers",
                "provider/checkpoint licenses and digests",
                "frozen grouped evaluation cases",
            ),
            reproduction_command="make release-evaluation prompt-benchmark-small",
        ),
        ResearchQuestionStatusV1(
            question_id="RQ6",
            status=EvaluationAvailability.FIXTURE_OBSERVATION,
            evidence_summary=(
                "The route contract detects all five authored dependency, protection, condition, "
                "and precursor-continuity perturbation classes; this is not a population estimate."
            ),
            reproduction_command="make release-evaluation route-prompt-small",
        ),
        ResearchQuestionStatusV1(
            question_id="RQ7",
            status=EvaluationAvailability.NOT_RUN,
            evidence_summary="No cross-system output comparison has been run.",
            blocking_requirements=(
                "official versioned SynthEx ReactionJSON/RouteJSON or export specification",
                "licensed comparable SynthEx, Synthelite, and ReactSeq outputs",
                "frozen cross-system sampling and mapping protocol",
            ),
            reproduction_command="make release-evaluation",
        ),
    )


def run_release_evaluation(root: str | Path) -> ReleaseEvaluationManifestV1:
    """Run every currently reproducible offline release evaluation without filling missing studies."""
    repository = Path(root)
    counterfactual_root = repository / "benchmarks" / "counterfactual-v1"
    prompt_root = repository / "benchmarks" / "prompt-robustness-v1"
    reactseq_fixture = repository / "tests" / "fixtures" / "reactseq" / "golden.json"
    source_paths = {
        "counterfactual_records": counterfactual_root / "records.jsonl",
        "counterfactual_manifest": counterfactual_root / "manifest.json",
        "counterfactual_splits": counterfactual_root / "splits.json",
        "counterfactual_human_review": counterfactual_root / "human-review.csv",
        "prompt_cases": prompt_root / "cases.jsonl",
        "prompt_manifest": prompt_root / "manifest.json",
        "reactseq_golden": reactseq_fixture,
        "evidence_model_plan": repository / "configs" / "evidence-models-v1.json",
    }
    counterfactual = validate_benchmark_artifacts(
        records_path=source_paths["counterfactual_records"],
        manifest_path=source_paths["counterfactual_manifest"],
        splits_path=source_paths["counterfactual_splits"],
        human_review_path=source_paths["counterfactual_human_review"],
    )
    prompt = validate_prompt_benchmark_artifacts(
        cases_path=source_paths["prompt_cases"],
        manifest_path=source_paths["prompt_manifest"],
    )
    conformance = run_reactseq_conformance(reactseq_fixture)
    return ReleaseEvaluationManifestV1(
        evaluation_date=date(2026, 8, 31),
        source_artifact_sha256={name: _sha256(path) for name, path in sorted(source_paths.items())},
        traversal_pair_semantically_equivalent=_traversal_pair_equivalent(),
        counterfactual_validation=counterfactual,
        prompt_validation=prompt,
        reactseq_conformance=conformance,
        route_prompt_contract=run_route_prompt_contract_smoke(),
        evidence_model_contract=run_evidence_model_contract_smoke(),
        research_questions=_research_question_statuses(),
        required_metrics=_required_metric_statuses(conformance),
        provenance=(
            ProvenanceRecord(
                source="synthaudit",
                source_version=__version__,
                adapter="run_release_evaluation",
                adapter_version="1",
                license="Apache-2.0",
                metadata={
                    "scope": "offline_software_verification_fixtures",
                    "research_metrics_status": "not_run",
                },
            ),
        ),
    )
