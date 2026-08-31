"""Stage-specific evidence modelling without experimental feasibility claims."""

# ruff: noqa: F401 -- TYPE_CHECKING imports document the lazy public API.

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from synthaudit.models.evaluation import (
        evaluate_evidence_scores,
        evaluate_predictions,
        run_feature_group_ablations,
    )
    from synthaudit.models.evidence import (
        AblationResultV1,
        AbstentionPolicyV1,
        CalibrationMethod,
        CalibrationSliceV1,
        EstimatorFamily,
        EvidenceEvaluationV1,
        EvidenceExampleSplit,
        EvidenceExampleV1,
        EvidenceFeatureV1,
        EvidenceModelManifestV1,
        EvidenceModelPlanV1,
        EvidenceModelRole,
        EvidencePredictionV1,
        EvidenceStage,
        EvidenceStagePlanV1,
        FeatureGroup,
        FeatureSchemaV1,
        ProviderDisagreementV1,
        ReliabilityBinV1,
        TransparentBaselineResultV1,
    )
    from synthaudit.models.extraction import extract_reaction_evidence_features
    from synthaudit.models.features import (
        PLAUSIBILITY_GROUPS,
        EncodedEvidenceMatrix,
        EvidenceFeatureEncoder,
        feature_groups_for_role,
    )
    from synthaudit.models.training import (
        ScoredEvidenceBatch,
        TrainedEvidenceModel,
        fit_evidence_model,
        transparent_baseline,
    )
    from synthaudit.models.uncertainty import (
        BootstrapEvidenceEnsemble,
        fit_abstention_policy_from_calibration,
        fit_bootstrap_ensemble,
        predict_with_uncertainty,
        provider_disagreement,
    )

_EXPORTS = {
    "PLAUSIBILITY_GROUPS": ("synthaudit.models.features", "PLAUSIBILITY_GROUPS"),
    "AblationResultV1": ("synthaudit.models.evidence", "AblationResultV1"),
    "AbstentionPolicyV1": ("synthaudit.models.evidence", "AbstentionPolicyV1"),
    "BootstrapEvidenceEnsemble": (
        "synthaudit.models.uncertainty",
        "BootstrapEvidenceEnsemble",
    ),
    "CalibrationMethod": ("synthaudit.models.evidence", "CalibrationMethod"),
    "CalibrationSliceV1": ("synthaudit.models.evidence", "CalibrationSliceV1"),
    "EncodedEvidenceMatrix": ("synthaudit.models.features", "EncodedEvidenceMatrix"),
    "EstimatorFamily": ("synthaudit.models.evidence", "EstimatorFamily"),
    "EvidenceEvaluationV1": ("synthaudit.models.evidence", "EvidenceEvaluationV1"),
    "EvidenceExampleSplit": ("synthaudit.models.evidence", "EvidenceExampleSplit"),
    "EvidenceExampleV1": ("synthaudit.models.evidence", "EvidenceExampleV1"),
    "EvidenceFeatureEncoder": ("synthaudit.models.features", "EvidenceFeatureEncoder"),
    "EvidenceFeatureV1": ("synthaudit.models.evidence", "EvidenceFeatureV1"),
    "EvidenceModelManifestV1": (
        "synthaudit.models.evidence",
        "EvidenceModelManifestV1",
    ),
    "EvidenceModelPlanV1": ("synthaudit.models.evidence", "EvidenceModelPlanV1"),
    "EvidenceModelRole": ("synthaudit.models.evidence", "EvidenceModelRole"),
    "EvidencePredictionV1": ("synthaudit.models.evidence", "EvidencePredictionV1"),
    "EvidenceStage": ("synthaudit.models.evidence", "EvidenceStage"),
    "EvidenceStagePlanV1": ("synthaudit.models.evidence", "EvidenceStagePlanV1"),
    "FeatureGroup": ("synthaudit.models.evidence", "FeatureGroup"),
    "FeatureSchemaV1": ("synthaudit.models.evidence", "FeatureSchemaV1"),
    "ProviderDisagreementV1": (
        "synthaudit.models.evidence",
        "ProviderDisagreementV1",
    ),
    "ReliabilityBinV1": ("synthaudit.models.evidence", "ReliabilityBinV1"),
    "ScoredEvidenceBatch": ("synthaudit.models.training", "ScoredEvidenceBatch"),
    "TrainedEvidenceModel": ("synthaudit.models.training", "TrainedEvidenceModel"),
    "TransparentBaselineResultV1": (
        "synthaudit.models.evidence",
        "TransparentBaselineResultV1",
    ),
    "evaluate_evidence_scores": (
        "synthaudit.models.evaluation",
        "evaluate_evidence_scores",
    ),
    "evaluate_predictions": ("synthaudit.models.evaluation", "evaluate_predictions"),
    "extract_reaction_evidence_features": (
        "synthaudit.models.extraction",
        "extract_reaction_evidence_features",
    ),
    "feature_groups_for_role": ("synthaudit.models.features", "feature_groups_for_role"),
    "fit_abstention_policy_from_calibration": (
        "synthaudit.models.uncertainty",
        "fit_abstention_policy_from_calibration",
    ),
    "fit_bootstrap_ensemble": (
        "synthaudit.models.uncertainty",
        "fit_bootstrap_ensemble",
    ),
    "fit_evidence_model": ("synthaudit.models.training", "fit_evidence_model"),
    "predict_with_uncertainty": (
        "synthaudit.models.uncertainty",
        "predict_with_uncertainty",
    ),
    "provider_disagreement": (
        "synthaudit.models.uncertainty",
        "provider_disagreement",
    ),
    "run_feature_group_ablations": (
        "synthaudit.models.evaluation",
        "run_feature_group_ablations",
    ),
    "transparent_baseline": ("synthaudit.models.training", "transparent_baseline"),
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str) -> Any:
    try:
        module_name, attribute = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(name) from exc
    value = getattr(import_module(module_name), attribute)
    globals()[name] = value
    return value
