"""Authored numeric fixture that exercises model contracts without scientific metrics."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from synthaudit.models import (
    CalibrationMethod,
    EstimatorFamily,
    EvidenceExampleSplit,
    EvidenceExampleV1,
    EvidenceFeatureV1,
    EvidenceModelRole,
    EvidenceStage,
    FeatureGroup,
    fit_abstention_policy_from_calibration,
    fit_bootstrap_ensemble,
    fit_evidence_model,
    predict_with_uncertainty,
    run_feature_group_ablations,
)
from synthaudit.models.evaluation import evaluate_predictions
from synthaudit.schema.common import ProvenanceRecord, StrictModel
from synthaudit.schema.evidence import EvidenceAvailability

_PROVENANCE = (
    ProvenanceRecord(
        source="synthaudit-authored-evidence-model-smoke",
        source_version="1",
        license="Apache-2.0 fixture; no experimental evidence",
    ),
)


class EvidenceModelContractSmokeV1(StrictModel):
    schema_version: Literal["synthaudit.evidence-model-contract-smoke/1"] = (
        "synthaudit.evidence-model-contract-smoke/1"
    )
    stage_model_count: Literal[4] = 4
    stages: tuple[EvidenceStage, ...]
    estimator_families_exercised: tuple[EstimatorFamily, ...]
    calibration_methods_exercised: tuple[CalibrationMethod, ...]
    bootstrap_member_count: int = Field(ge=2)
    missing_flags_exercised: bool
    provider_disagreement_exercised: bool
    abstention_exercised: bool
    ood_evaluation_contract_exercised: bool
    ablation_contract_count: int = Field(ge=1)
    raw_score_semantics: Literal["uncalibrated_model_score"] = "uncalibrated_model_score"
    calibrated_score_semantics: Literal[
        "calibrated_evidence_support_score_not_experimental_probability"
    ] = "calibrated_evidence_support_score_not_experimental_probability"
    metrics_status: Literal["not_reportable_software_fixture"] = "not_reportable_software_fixture"
    notice: Literal[
        "SynthAudit estimates representation validity, corpus novelty and evidence-based plausibility. It does not establish experimental feasibility, yield, selectivity, safety or scalability."
    ] = (
        "SynthAudit estimates representation validity, corpus novelty and evidence-based "
        "plausibility. It does not establish experimental feasibility, yield, selectivity, "
        "safety or scalability."
    )


def _feature(identifier: str, group: FeatureGroup, value: float | None) -> EvidenceFeatureV1:
    if value is None:
        return EvidenceFeatureV1(
            feature_id=identifier,
            group=group,
            availability=EvidenceAvailability.UNAVAILABLE,
            missing_reason="authored smoke missingness",
            interpretation="Software contract fixture only.",
        )
    return EvidenceFeatureV1(
        feature_id=identifier,
        group=group,
        availability=EvidenceAvailability.AVAILABLE,
        value=value,
        interpretation="Authored numeric contract fixture only.",
        provenance=_PROVENANCE,
    )


def _examples(
    split: EvidenceExampleSplit,
    stage: EvidenceStage,
    prefix: str,
    count: int,
) -> tuple[EvidenceExampleV1, ...]:
    examples = []
    for index in range(count):
        label = index % 2
        support = 0.8 if label else 0.2
        examples.append(
            EvidenceExampleV1(
                example_id=f"{prefix}-{index}",
                parent_group_id=f"{prefix}-parent-{index}",
                split=split,
                stage=stage,
                target_label=label,
                target_source="authored software support annotation",
                completion_condition_centre_supported=(
                    True if stage == EvidenceStage.COMPLETION_GIVEN_CENTRE else None
                ),
                product_novelty=(index + 1) / (count + 1),
                features=(
                    _feature(
                        "corpus.familiarity",
                        FeatureGroup.CORPUS_FAMILIARITY,
                        1.0 - support,
                    ),
                    _feature("structural.valid", FeatureGroup.STRUCTURAL, support),
                    _feature("centre.support", FeatureGroup.REACTION_CENTRE, support),
                    _feature("completion.support", FeatureGroup.COMPLETION, support),
                    _feature("stereo.support", FeatureGroup.STEREO, support),
                    _feature("route.support", FeatureGroup.ROUTE, support),
                    _feature(
                        "precedent.support",
                        FeatureGroup.PRECEDENT,
                        None if split != EvidenceExampleSplit.TRAIN and index == 0 else support,
                    ),
                    _feature("providers.agreement", FeatureGroup.PROVIDER_AGREEMENT, 0.9),
                ),
                provenance=_PROVENANCE,
            )
        )
    return tuple(examples)


def run_evidence_model_contract_smoke() -> EvidenceModelContractSmokeV1:
    configurations = (
        (EvidenceStage.REACTION_CENTRE, EvidenceModelRole.REACTION_CENTRE_MODEL),
        (EvidenceStage.COMPLETION_GIVEN_CENTRE, EvidenceModelRole.COMPLETION_MODEL),
        (EvidenceStage.STEREO, EvidenceModelRole.STEREO_MODEL),
        (EvidenceStage.ROUTE_CONTEXT, EvidenceModelRole.FULL_EVIDENCE_ENSEMBLE),
    )
    fitted = []
    for index, (stage, role) in enumerate(configurations):
        fitted.append(
            fit_evidence_model(
                _examples(EvidenceExampleSplit.TRAIN, stage, f"stage-{index}-train", 12),
                _examples(
                    EvidenceExampleSplit.CALIBRATION,
                    stage,
                    f"stage-{index}-calibration",
                    6,
                ),
                stage=stage,
                role=role,
                estimator_family=EstimatorFamily.LOGISTIC_REGRESSION,
                calibration_method=CalibrationMethod.PLATT,
                random_seed=100 + index,
            )
        )
    stage = EvidenceStage.REACTION_CENTRE
    train = _examples(EvidenceExampleSplit.TRAIN, stage, "uncertainty-train", 12)
    calibration = _examples(EvidenceExampleSplit.CALIBRATION, stage, "uncertainty-calibration", 6)
    ood = _examples(EvidenceExampleSplit.OOD_SCAFFOLD, stage, "uncertainty-ood", 6)
    hgb = fit_evidence_model(
        train,
        calibration,
        stage=stage,
        role=EvidenceModelRole.REACTION_CENTRE_MODEL,
        estimator_family=EstimatorFamily.HIST_GRADIENT_BOOSTING,
        calibration_method=CalibrationMethod.ISOTONIC,
        random_seed=200,
    )
    bootstrap = fit_bootstrap_ensemble(
        train,
        calibration,
        stage=stage,
        role=EvidenceModelRole.REACTION_CENTRE_MODEL,
        estimator_family=EstimatorFamily.LOGISTIC_REGRESSION,
        calibration_method=CalibrationMethod.PLATT,
        random_seed=201,
        member_count=3,
    )
    calibration_count = len(calibration)
    policy = fit_abstention_policy_from_calibration(
        policy_id="authored-smoke-policy",
        calibration_parent_groups=[item.parent_group_id for item in calibration],
        bootstrap_standard_deviations=[0.5] * calibration_count,
        missing_feature_fractions=[1.0] * calibration_count,
        ood_max_absolute_zscores=[0.0] * calibration_count,
        provider_score_ranges=[1.0] * calibration_count,
    )
    predictions = predict_with_uncertainty(
        fitted[0],
        ood,
        policy=policy,
        bootstrap=bootstrap,
        provider_scores_by_example={
            item.example_id: {"fixture-a": 0.7, "fixture-b": 0.6} for item in ood
        },
    )
    evaluation = evaluate_predictions(
        ood,
        predictions,
        evaluation_id="authored-ood-contract-smoke",
        split=EvidenceExampleSplit.OOD_SCAFFOLD,
        scope="software_verification_fixture",
    )
    ablations = run_feature_group_ablations(
        train,
        calibration,
        ood,
        stage=stage,
        estimator_family=EstimatorFamily.LOGISTIC_REGRESSION,
        calibration_method=CalibrationMethod.PLATT,
        retained_group_sets=(
            {FeatureGroup.STRUCTURAL},
            {FeatureGroup.STRUCTURAL, FeatureGroup.REACTION_CENTRE},
        ),
        random_seed=300,
        scope="software_verification_fixture",
    )
    assert evaluation.scope == "software_verification_fixture"
    assert hgb.manifest.calibration_method == CalibrationMethod.ISOTONIC
    return EvidenceModelContractSmokeV1(
        stages=tuple(stage for stage, _ in configurations),
        estimator_families_exercised=(
            EstimatorFamily.LOGISTIC_REGRESSION,
            EstimatorFamily.HIST_GRADIENT_BOOSTING,
        ),
        calibration_methods_exercised=(CalibrationMethod.PLATT, CalibrationMethod.ISOTONIC),
        bootstrap_member_count=len(bootstrap.members),
        missing_flags_exercised=bool(predictions[0].missing_feature_flags),
        provider_disagreement_exercised=(
            predictions[0].provider_disagreement is not None
            and predictions[0].provider_disagreement.availability == EvidenceAvailability.AVAILABLE
        ),
        abstention_exercised=any(item.abstained for item in predictions),
        ood_evaluation_contract_exercised=True,
        ablation_contract_count=len(ablations),
    )
