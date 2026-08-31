from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from synthaudit.models import (
    CalibrationMethod,
    EstimatorFamily,
    EvidenceExampleSplit,
    EvidenceExampleV1,
    EvidenceFeatureV1,
    EvidenceModelPlanV1,
    EvidenceModelRole,
    EvidenceStage,
    FeatureGroup,
    fit_abstention_policy_from_calibration,
    fit_bootstrap_ensemble,
    fit_evidence_model,
    predict_with_uncertainty,
    run_feature_group_ablations,
    transparent_baseline,
)
from synthaudit.models.evaluation import evaluate_predictions
from synthaudit.models.features import feature_groups_for_role
from synthaudit.schema import EvidenceAvailability, ProvenanceRecord

PROVENANCE = (
    ProvenanceRecord(
        source="authored-model-test-fixture",
        source_version="1",
        license="Apache-2.0 fixture",
    ),
)


def _feature(feature_id: str, group: FeatureGroup, value: float | None) -> EvidenceFeatureV1:
    if value is None:
        return EvidenceFeatureV1(
            feature_id=feature_id,
            group=group,
            availability=EvidenceAvailability.UNAVAILABLE,
            missing_reason="authored missing-value test case",
            interpretation="Software-fixture missingness only.",
        )
    return EvidenceFeatureV1(
        feature_id=feature_id,
        group=group,
        availability=EvidenceAvailability.AVAILABLE,
        value=value,
        interpretation="Authored numeric software fixture.",
        provenance=PROVENANCE,
    )


def test_committed_model_plan_declares_all_stages_baselines_and_leakage_guards() -> None:
    payload = json.loads(Path("configs/evidence-models-v1.json").read_text())
    plan = EvidenceModelPlanV1.model_validate(payload)
    assert len(plan.baseline_roles) == 6
    assert {item.stage for item in plan.stage_models} == set(EvidenceStage)
    assert plan.test_split_use == "evaluation_only_no_calibration_or_threshold_selection"
    assert plan.model_selection_status == "not_run"


def _examples(
    split: EvidenceExampleSplit,
    *,
    count: int,
    prefix: str,
    stage: EvidenceStage = EvidenceStage.REACTION_CENTRE,
) -> tuple[EvidenceExampleV1, ...]:
    values = []
    for index in range(count):
        label = index % 2
        support = 0.82 if label else 0.18
        noise = (index % 3 - 1) * 0.03
        features = (
            _feature("corpus.familiarity", FeatureGroup.CORPUS_FAMILIARITY, 1.0 - support),
            _feature("structural.valid", FeatureGroup.STRUCTURAL, support),
            _feature("centre.consistent", FeatureGroup.REACTION_CENTRE, support + noise),
            _feature(
                "completion.consistent",
                FeatureGroup.COMPLETION,
                min(1.0, max(0.0, support - noise)),
            ),
            _feature("stereo.support", FeatureGroup.STEREO, support),
            _feature(
                "precedent.support",
                FeatureGroup.PRECEDENT,
                None if split != EvidenceExampleSplit.TRAIN and index == 0 else support,
            ),
            _feature("providers.agreement", FeatureGroup.PROVIDER_AGREEMENT, 0.5 - noise),
        )
        values.append(
            EvidenceExampleV1(
                example_id=f"{prefix}-{index}",
                parent_group_id=f"{prefix}-parent-{index}",
                split=split,
                stage=stage,
                target_label=label,
                target_source="authored support-annotation fixture",
                completion_condition_centre_supported=(
                    True if stage == EvidenceStage.COMPLETION_GIVEN_CENTRE else None
                ),
                product_novelty=(index + 1) / (count + 1),
                features=features,
                provenance=PROVENANCE,
            )
        )
    return tuple(values)


@pytest.mark.parametrize(
    ("family", "calibration"),
    [
        (EstimatorFamily.LOGISTIC_REGRESSION, CalibrationMethod.PLATT),
        (EstimatorFamily.LOGISTIC_REGRESSION, CalibrationMethod.ISOTONIC),
        (EstimatorFamily.HIST_GRADIENT_BOOSTING, CalibrationMethod.PLATT),
    ],
)
def test_stage_model_fits_only_train_and_held_out_calibration(
    family: EstimatorFamily,
    calibration: CalibrationMethod,
) -> None:
    train = _examples(EvidenceExampleSplit.TRAIN, count=16, prefix="train")
    held_out = _examples(EvidenceExampleSplit.CALIBRATION, count=8, prefix="cal")
    test = _examples(EvidenceExampleSplit.TEST, count=8, prefix="test")
    model = fit_evidence_model(
        train,
        held_out,
        stage=EvidenceStage.REACTION_CENTRE,
        role=EvidenceModelRole.REACTION_CENTRE_MODEL,
        estimator_family=family,
        calibration_method=calibration,
        random_seed=7,
    )
    scored = model.score(test)
    assert scored.raw_scores.shape == (8,)
    assert scored.calibrated_scores is not None
    assert np.all((scored.calibrated_scores >= 0) & (scored.calibrated_scores <= 1))
    assert model.manifest.calibration_uses_held_out_groups
    assert model.manifest.raw_score_semantics == "uncalibrated_model_score"
    assert "not_experimental_probability" in model.manifest.calibrated_score_semantics
    assert "corpus.familiarity" not in model.manifest.feature_schema.ordered_feature_ids


def test_training_rejects_parent_leakage_and_test_split_use() -> None:
    train = _examples(EvidenceExampleSplit.TRAIN, count=8, prefix="same")
    calibration = list(_examples(EvidenceExampleSplit.CALIBRATION, count=4, prefix="cal"))
    calibration[0] = calibration[0].model_copy(update={"parent_group_id": train[0].parent_group_id})
    with pytest.raises(ValueError, match="parent-group leakage"):
        fit_evidence_model(
            train,
            calibration,
            stage=EvidenceStage.REACTION_CENTRE,
            role=EvidenceModelRole.REACTION_CENTRE_MODEL,
            estimator_family=EstimatorFamily.LOGISTIC_REGRESSION,
            calibration_method=CalibrationMethod.PLATT,
            random_seed=1,
        )
    with pytest.raises(ValueError, match="training split"):
        fit_evidence_model(
            _examples(EvidenceExampleSplit.TEST, count=8, prefix="test-as-train"),
            (),
            stage=EvidenceStage.REACTION_CENTRE,
            role=EvidenceModelRole.REACTION_CENTRE_MODEL,
            estimator_family=EstimatorFamily.LOGISTIC_REGRESSION,
            calibration_method=CalibrationMethod.NONE,
            random_seed=1,
        )


@pytest.mark.parametrize(
    ("stage", "role"),
    [
        (EvidenceStage.REACTION_CENTRE, EvidenceModelRole.REACTION_CENTRE_MODEL),
        (EvidenceStage.COMPLETION_GIVEN_CENTRE, EvidenceModelRole.COMPLETION_MODEL),
        (EvidenceStage.STEREO, EvidenceModelRole.STEREO_MODEL),
        (EvidenceStage.ROUTE_CONTEXT, EvidenceModelRole.FULL_EVIDENCE_ENSEMBLE),
    ],
)
def test_all_four_stage_quantities_have_separate_model_contracts(
    stage: EvidenceStage,
    role: EvidenceModelRole,
) -> None:
    model = fit_evidence_model(
        _examples(EvidenceExampleSplit.TRAIN, count=12, prefix=f"{stage.value}-train", stage=stage),
        _examples(
            EvidenceExampleSplit.CALIBRATION,
            count=6,
            prefix=f"{stage.value}-calibration",
            stage=stage,
        ),
        stage=stage,
        role=role,
        estimator_family=EstimatorFamily.LOGISTIC_REGRESSION,
        calibration_method=CalibrationMethod.PLATT,
        random_seed=5,
    )
    assert model.manifest.stage == stage
    assert model.manifest.role == role


def _permissive_policy(calibration: tuple[EvidenceExampleV1, ...]):
    return fit_abstention_policy_from_calibration(
        policy_id="fixture-policy",
        calibration_parent_groups=[item.parent_group_id for item in calibration],
        bootstrap_standard_deviations=[0.5] * len(calibration),
        missing_feature_fractions=[1.0] * len(calibration),
        ood_max_absolute_zscores=[100.0] * len(calibration),
        provider_score_ranges=[1.0] * len(calibration),
        quantile=0.9,
    )


def test_feature_missingness_ood_bootstrap_disagreement_and_abstention_are_explicit() -> None:
    train = _examples(EvidenceExampleSplit.TRAIN, count=16, prefix="train")
    calibration = _examples(EvidenceExampleSplit.CALIBRATION, count=8, prefix="cal")
    test = _examples(EvidenceExampleSplit.TEST, count=8, prefix="test")
    model = fit_evidence_model(
        train,
        calibration,
        stage=EvidenceStage.REACTION_CENTRE,
        role=EvidenceModelRole.REACTION_CENTRE_MODEL,
        estimator_family=EstimatorFamily.LOGISTIC_REGRESSION,
        calibration_method=CalibrationMethod.PLATT,
        random_seed=11,
    )
    ensemble = fit_bootstrap_ensemble(
        train,
        calibration,
        stage=EvidenceStage.REACTION_CENTRE,
        role=EvidenceModelRole.REACTION_CENTRE_MODEL,
        estimator_family=EstimatorFamily.LOGISTIC_REGRESSION,
        calibration_method=CalibrationMethod.PLATT,
        random_seed=13,
        member_count=5,
    )
    policy = _permissive_policy(calibration)
    provider_scores = {item.example_id: {"provider-a": 0.6, "provider-b": 0.55} for item in test}
    predictions = predict_with_uncertainty(
        model,
        test,
        policy=policy,
        bootstrap=ensemble,
        provider_scores_by_example=provider_scores,
    )
    assert all(item.bootstrap_member_count == 5 for item in predictions)
    assert all(item.bootstrap_interval_90 is not None for item in predictions)
    assert predictions[0].missing_feature_flags == ("precedent.support__missing",)
    assert not any(item.abstained for item in predictions)
    assert predictions[0].provider_disagreement is not None
    assert predictions[0].provider_disagreement.score_range == pytest.approx(0.05)

    strict = policy.model_copy(update={"maximum_ood_zscore": 0.0})
    abstained = predict_with_uncertainty(
        model,
        test,
        policy=strict,
        bootstrap=ensemble,
        provider_scores_by_example=provider_scores,
    )
    assert any(item.abstained for item in abstained)
    assert any(
        "out-of-distribution" in reason for item in abstained for reason in item.abstention_reasons
    )


def test_ood_evaluation_and_ablations_are_held_out_reports_only() -> None:
    train = _examples(EvidenceExampleSplit.TRAIN, count=16, prefix="train")
    calibration = _examples(EvidenceExampleSplit.CALIBRATION, count=8, prefix="cal")
    test = _examples(EvidenceExampleSplit.OOD_SCAFFOLD, count=8, prefix="ood")
    model = fit_evidence_model(
        train,
        calibration,
        stage=EvidenceStage.REACTION_CENTRE,
        role=EvidenceModelRole.REACTION_CENTRE_MODEL,
        estimator_family=EstimatorFamily.LOGISTIC_REGRESSION,
        calibration_method=CalibrationMethod.PLATT,
        random_seed=21,
    )
    ensemble = fit_bootstrap_ensemble(
        train,
        calibration,
        stage=EvidenceStage.REACTION_CENTRE,
        role=EvidenceModelRole.REACTION_CENTRE_MODEL,
        estimator_family=EstimatorFamily.LOGISTIC_REGRESSION,
        calibration_method=CalibrationMethod.PLATT,
        random_seed=22,
        member_count=3,
    )
    predictions = predict_with_uncertainty(
        model,
        test,
        policy=_permissive_policy(calibration),
        bootstrap=ensemble,
        provider_scores_by_example={item.example_id: {"a": 0.5, "b": 0.5} for item in test},
    )
    evaluation = evaluate_predictions(
        test,
        predictions,
        evaluation_id="fixture-ood",
        split=EvidenceExampleSplit.OOD_SCAFFOLD,
        scope="software_verification_fixture",
    )
    assert evaluation.sample_count == len(test)
    assert evaluation.calibration_slices[0].slice_id == "all"
    assert any("plumbing" in item for item in evaluation.limitations)

    ablations = run_feature_group_ablations(
        train,
        calibration,
        test,
        stage=EvidenceStage.REACTION_CENTRE,
        estimator_family=EstimatorFamily.LOGISTIC_REGRESSION,
        calibration_method=CalibrationMethod.PLATT,
        retained_group_sets=(
            {FeatureGroup.STRUCTURAL},
            {FeatureGroup.STRUCTURAL, FeatureGroup.REACTION_CENTRE, FeatureGroup.PRECEDENT},
        ),
        random_seed=30,
        scope="software_verification_fixture",
    )
    assert len(ablations) == 2
    assert all(item.selection_prohibited for item in ablations)


def test_transparent_baselines_and_stage_roles_preserve_semantics() -> None:
    example = _examples(EvidenceExampleSplit.TRAIN, count=2, prefix="base")[1]
    familiarity = transparent_baseline(example, role=EvidenceModelRole.CORPUS_FAMILIARITY_BASELINE)
    structural = transparent_baseline(
        example, role=EvidenceModelRole.DETERMINISTIC_STRUCTURAL_BASELINE
    )
    assert familiarity.semantics == "corpus_familiarity_not_plausibility"
    assert structural.semantics.startswith("deterministic_representation_support")
    assert FeatureGroup.CORPUS_FAMILIARITY not in feature_groups_for_role(
        EvidenceModelRole.FULL_EVIDENCE_ENSEMBLE
    )


def test_completion_examples_require_explicit_centre_conditioning() -> None:
    payload = _examples(EvidenceExampleSplit.TRAIN, count=2, prefix="conditional")[0].model_dump(
        mode="json"
    )
    payload["stage"] = EvidenceStage.COMPLETION_GIVEN_CENTRE
    with pytest.raises(ValueError, match="conditioning"):
        EvidenceExampleV1.model_validate(payload)
