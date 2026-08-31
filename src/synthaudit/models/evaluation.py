"""Held-out OOD evaluation and feature-group ablations without threshold tuning."""

from __future__ import annotations

from collections.abc import Sequence, Set

import numpy as np
from sklearn.metrics import average_precision_score, roc_auc_score

from synthaudit.calibration.metrics import (
    novelty_stratified_calibration,
    reliability_summary,
)
from synthaudit.models.evidence import (
    AblationResultV1,
    CalibrationMethod,
    EstimatorFamily,
    EvidenceEvaluationV1,
    EvidenceExampleSplit,
    EvidenceExampleV1,
    EvidenceModelRole,
    EvidencePredictionV1,
    EvidenceStage,
    FeatureGroup,
)
from synthaudit.models.training import fit_evidence_model


def evaluate_evidence_scores(
    examples: Sequence[EvidenceExampleV1],
    scores: Sequence[float],
    abstained: Sequence[bool],
    *,
    evaluation_id: str,
    model_id: str,
    split: EvidenceExampleSplit,
    scope: str,
    bin_count: int = 10,
) -> EvidenceEvaluationV1:
    if not (len(examples) == len(scores) == len(abstained)):
        raise ValueError("evaluation examples, scores, and abstention flags must be aligned")
    if not examples:
        raise ValueError("evidence evaluation requires examples")
    if any(example.split != split for example in examples):
        raise ValueError("evaluation examples do not match the declared held-out split")
    stage = examples[0].stage
    if any(example.stage != stage for example in examples):
        raise ValueError("evidence evaluation requires one stage")
    labels = np.asarray([example.target_label for example in examples], dtype=int)
    score_array = np.asarray(scores, dtype=float)
    if np.any((score_array < 0) | (score_array > 1)):
        raise ValueError("calibrated evidence scores must be within [0, 1]")
    retained = np.asarray([not value for value in abstained], dtype=bool)
    coverage = float(np.mean(retained))
    selective_risk = None
    if np.any(retained):
        decisions = score_array[retained] >= 0.5
        selective_risk = float(np.mean(decisions != labels[retained]))
    both_classes = len(set(int(value) for value in labels)) == 2
    overall = reliability_summary(
        labels.tolist(), score_array.tolist(), slice_id="all", bin_count=bin_count
    )
    slices = novelty_stratified_calibration(
        labels.tolist(),
        score_array.tolist(),
        [example.product_novelty for example in examples],
        bin_count=bin_count,
    )
    limitations = [
        "Targets are evidence-support annotations, not experimental outcomes.",
        "Calibration and decision thresholds were not selected on this evaluation split.",
    ]
    if scope == "software_verification_fixture":
        limitations.append(
            "Authored software-fixture metrics are plumbing checks and not scientific performance."
        )
    return EvidenceEvaluationV1(
        evaluation_id=evaluation_id,
        stage=stage,
        model_id=model_id,
        split=split,
        scope=scope,
        sample_count=len(examples),
        auroc=float(roc_auc_score(labels, score_array)) if both_classes else None,
        average_precision=(
            float(average_precision_score(labels, score_array)) if both_classes else None
        ),
        brier_score=overall.brier_score,
        expected_calibration_error=overall.expected_calibration_error,
        selective_risk=selective_risk,
        coverage=coverage,
        calibration_slices=(overall, *slices),
        limitations=tuple(limitations),
    )


def evaluate_predictions(
    examples: Sequence[EvidenceExampleV1],
    predictions: Sequence[EvidencePredictionV1],
    *,
    evaluation_id: str,
    split: EvidenceExampleSplit,
    scope: str,
    bin_count: int = 10,
) -> EvidenceEvaluationV1:
    if len(examples) != len(predictions):
        raise ValueError("prediction evaluation requires aligned examples")
    if [item.example_id for item in examples] != [item.example_id for item in predictions]:
        raise ValueError("prediction IDs do not align with evaluation examples")
    scores = [item.calibrated_evidence_support_score for item in predictions]
    if any(value is None for value in scores):
        raise ValueError("evaluation requires held-out calibrated evidence scores")
    model_ids = {item.model_id for item in predictions}
    if len(model_ids) != 1:
        raise ValueError("prediction evaluation requires one model")
    return evaluate_evidence_scores(
        examples,
        [float(value) for value in scores if value is not None],
        [item.abstained for item in predictions],
        evaluation_id=evaluation_id,
        model_id=next(iter(model_ids)),
        split=split,
        scope=scope,
        bin_count=bin_count,
    )


def run_feature_group_ablations(
    train: Sequence[EvidenceExampleV1],
    calibration: Sequence[EvidenceExampleV1],
    test: Sequence[EvidenceExampleV1],
    *,
    stage: EvidenceStage,
    estimator_family: EstimatorFamily,
    calibration_method: CalibrationMethod,
    retained_group_sets: Sequence[Set[FeatureGroup]],
    random_seed: int,
    scope: str,
) -> tuple[AblationResultV1, ...]:
    if not retained_group_sets:
        raise ValueError("ablation requires at least one retained feature-group set")
    if any(FeatureGroup.CORPUS_FAMILIARITY in groups for groups in retained_group_sets):
        raise ValueError("primary plausibility ablations cannot reintroduce corpus novelty")
    results: list[AblationResultV1] = []
    for index, groups in enumerate(retained_group_sets):
        model = fit_evidence_model(
            train,
            calibration,
            stage=stage,
            role=EvidenceModelRole.FULL_EVIDENCE_ENSEMBLE,
            estimator_family=estimator_family,
            calibration_method=calibration_method,
            random_seed=random_seed + index,
            feature_groups=groups,
        )
        scored = model.score(test)
        values = (
            scored.calibrated_scores if scored.calibrated_scores is not None else scored.raw_scores
        )
        evaluation = evaluate_evidence_scores(
            test,
            values.tolist(),
            [False] * len(test),
            evaluation_id=f"ablation-{index}",
            model_id=model.manifest.model_id,
            split=test[0].split,
            scope=scope,
        )
        results.append(
            AblationResultV1(
                ablation_id=f"ablation-{index}",
                retained_feature_groups=tuple(sorted(groups, key=lambda item: item.value)),
                evaluation=evaluation,
            )
        )
    return tuple(results)
