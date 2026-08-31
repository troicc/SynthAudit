from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from synthaudit.evaluation import (
    EvaluationAvailability,
    RequiredMetricStatusV1,
    run_release_evaluation,
)


def test_release_evaluation_separates_fixture_observations_from_unrun_research() -> None:
    result = run_release_evaluation(Path.cwd())

    assert result.release_version == "1.0.0"
    assert result.research_metrics_status == "not_run"
    assert not result.fixture_results_are_population_metrics
    assert not result.experimental_feasibility_established
    assert result.traversal_pair_semantically_equivalent
    assert result.counterfactual_validation.record_count == 200
    assert result.prompt_validation.variant_count == 40
    assert result.reactseq_conformance.fixture_count == 3
    assert result.route_prompt_contract.all_route_perturbations_detected

    question_status = {item.question_id: item.status for item in result.research_questions}
    assert question_status == {
        "RQ1": EvaluationAvailability.FIXTURE_OBSERVATION,
        "RQ2": EvaluationAvailability.NOT_RUN,
        "RQ3": EvaluationAvailability.NOT_RUN,
        "RQ4": EvaluationAvailability.NOT_RUN,
        "RQ5": EvaluationAvailability.NOT_RUN,
        "RQ6": EvaluationAvailability.FIXTURE_OBSERVATION,
        "RQ7": EvaluationAvailability.NOT_RUN,
    }
    assert len(result.required_metrics) == 17
    observed = [
        item
        for item in result.required_metrics
        if item.status == EvaluationAvailability.FIXTURE_OBSERVATION
    ]
    assert {item.metric_id for item in observed} == {
        "parse_success",
        "exact_precursor_reconstruction",
        "reaction_centre_precision",
        "reaction_centre_recall",
        "reaction_centre_f1",
        "leaving_group_accuracy",
    }
    assert all(item.scope == "software_verification_fixture" for item in observed)
    assert all(item.confidence_interval_95 is None for item in result.required_metrics)
    assert all(len(digest) == 64 for digest in result.source_artifact_sha256.values())


def test_not_run_metric_contract_rejects_prefilled_numbers() -> None:
    with pytest.raises(ValidationError, match="not-run metrics cannot contain numerical results"):
        RequiredMetricStatusV1(
            metric_id="auroc",
            status=EvaluationAvailability.NOT_RUN,
            value=0.9,
            sample_count=100,
            unit="score",
            scope="research_evaluation",
            bootstrap_status="not_run_missing_research_data",
            reason="invalid prefilled test value",
            reproduction_command="make release-evaluation",
        )
