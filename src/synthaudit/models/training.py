"""Leakage-checked stage-specific LogisticRegression and HGB evidence models."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence, Set
from dataclasses import dataclass
from typing import Any

import numpy as np
import sklearn
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression

from synthaudit import __version__
from synthaudit.calibration.calibrators import FittedScoreCalibrator, fit_score_calibrator
from synthaudit.models.evidence import (
    CalibrationMethod,
    EstimatorFamily,
    EvidenceExampleSplit,
    EvidenceExampleV1,
    EvidenceModelManifestV1,
    EvidenceModelRole,
    EvidenceStage,
    FeatureGroup,
    TransparentBaselineResultV1,
)
from synthaudit.models.features import (
    EncodedEvidenceMatrix,
    EvidenceFeatureEncoder,
    feature_groups_for_role,
)
from synthaudit.schema.common import ProvenanceRecord
from synthaudit.schema.evidence import EvidenceAvailability


def _group_digest(examples: Sequence[EvidenceExampleV1]) -> str:
    groups = "\n".join(sorted({example.parent_group_id for example in examples}))
    return hashlib.sha256(groups.encode()).hexdigest()


def _configuration_digest(payload: dict[str, Any]) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode()).hexdigest()


def _validate_role(stage: EvidenceStage, role: EvidenceModelRole) -> None:
    expected = {
        EvidenceModelRole.REACTION_CENTRE_MODEL: EvidenceStage.REACTION_CENTRE,
        EvidenceModelRole.COMPLETION_MODEL: EvidenceStage.COMPLETION_GIVEN_CENTRE,
        EvidenceModelRole.STEREO_MODEL: EvidenceStage.STEREO,
    }
    if role in expected and expected[role] != stage:
        raise ValueError(f"model role {role.value} requires stage {expected[role].value}")
    if role == EvidenceModelRole.DETERMINISTIC_STRUCTURAL_BASELINE:
        raise ValueError("deterministic structural baseline is not a learned estimator")
    if role == EvidenceModelRole.CORPUS_FAMILIARITY_BASELINE:
        raise ValueError("corpus familiarity baseline is reported transparently, not fitted here")


def _validate_training_partitions(
    train: Sequence[EvidenceExampleV1],
    calibration: Sequence[EvidenceExampleV1],
    *,
    stage: EvidenceStage,
    calibration_method: CalibrationMethod,
) -> None:
    if not train:
        raise ValueError("evidence model requires training examples")
    if any(example.split != EvidenceExampleSplit.TRAIN for example in train):
        raise ValueError("base estimator may use only the training split")
    if any(example.split != EvidenceExampleSplit.CALIBRATION for example in calibration):
        raise ValueError("calibrator may use only the calibration split")
    if any(example.stage != stage for example in (*train, *calibration)):
        raise ValueError("all model examples must match the declared stage")
    train_groups = {example.parent_group_id for example in train}
    calibration_groups = {example.parent_group_id for example in calibration}
    overlap = sorted(train_groups & calibration_groups)
    if overlap:
        raise ValueError(f"parent-group leakage between train and calibration: {overlap}")
    if len({example.example_id for example in (*train, *calibration)}) != len(
        (*train, *calibration)
    ):
        raise ValueError("training and calibration example IDs must be unique")
    if len({example.target_label for example in train}) != 2:
        raise ValueError("training split requires both support annotation classes")
    if calibration_method == CalibrationMethod.NONE and calibration:
        raise ValueError("uncalibrated training cannot consume calibration examples")
    if calibration_method != CalibrationMethod.NONE and (
        not calibration or len({example.target_label for example in calibration}) != 2
    ):
        raise ValueError("held-out calibration requires both support annotation classes")


def _estimator(family: EstimatorFamily, *, random_seed: int) -> tuple[Any, dict[str, Any]]:
    if family == EstimatorFamily.LOGISTIC_REGRESSION:
        parameters: dict[str, Any] = {
            "class_weight": "balanced",
            "max_iter": 1000,
            "random_state": random_seed,
            "solver": "lbfgs",
        }
        return LogisticRegression(**parameters), parameters
    parameters = {
        "learning_rate": 0.1,
        "max_iter": 100,
        "random_state": random_seed,
    }
    return HistGradientBoostingClassifier(**parameters), parameters


@dataclass(frozen=True)
class ScoredEvidenceBatch:
    encoded: EncodedEvidenceMatrix
    raw_scores: np.ndarray
    calibrated_scores: np.ndarray | None


@dataclass
class TrainedEvidenceModel:
    estimator: Any
    calibrator: FittedScoreCalibrator | None
    encoder: EvidenceFeatureEncoder
    manifest: EvidenceModelManifestV1

    def score(self, examples: Sequence[EvidenceExampleV1]) -> ScoredEvidenceBatch:
        encoded = self.encoder.transform(examples)
        raw = np.asarray(self.estimator.predict_proba(encoded.values)[:, 1], dtype=float)
        calibrated = self.calibrator.transform(raw) if self.calibrator is not None else None
        return ScoredEvidenceBatch(
            encoded=encoded,
            raw_scores=raw,
            calibrated_scores=calibrated,
        )


def fit_evidence_model(
    train: Sequence[EvidenceExampleV1],
    calibration: Sequence[EvidenceExampleV1],
    *,
    stage: EvidenceStage,
    role: EvidenceModelRole,
    estimator_family: EstimatorFamily,
    calibration_method: CalibrationMethod,
    random_seed: int,
    feature_groups: Set[FeatureGroup] | None = None,
) -> TrainedEvidenceModel:
    _validate_role(stage, role)
    _validate_training_partitions(
        train,
        calibration,
        stage=stage,
        calibration_method=calibration_method,
    )
    selected_groups = frozenset(feature_groups or feature_groups_for_role(role))
    if (
        role != EvidenceModelRole.FULL_EVIDENCE_ENSEMBLE
        and FeatureGroup.CORPUS_FAMILIARITY in selected_groups
    ):
        raise ValueError("stage-specific plausibility models cannot include corpus familiarity")
    if (
        role == EvidenceModelRole.FULL_EVIDENCE_ENSEMBLE
        and FeatureGroup.CORPUS_FAMILIARITY in selected_groups
    ):
        raise ValueError("the primary full evidence ensemble excludes novelty/familiarity features")
    encoder = EvidenceFeatureEncoder.fit(train, allowed_groups=selected_groups)
    encoded_train = encoder.transform(train)
    estimator, hyperparameters = _estimator(estimator_family, random_seed=random_seed)
    estimator.fit(encoded_train.values, encoded_train.labels)
    calibrator: FittedScoreCalibrator | None = None
    calibration_digest: str | None = None
    if calibration_method != CalibrationMethod.NONE:
        encoded_calibration = encoder.transform(calibration)
        raw_calibration = np.asarray(
            estimator.predict_proba(encoded_calibration.values)[:, 1], dtype=float
        )
        calibrator = fit_score_calibrator(
            calibration_method,
            raw_calibration,
            encoded_calibration.labels,
        )
        calibration_digest = _group_digest(calibration)
    configuration = {
        "stage": stage.value,
        "role": role.value,
        "estimator_family": estimator_family.value,
        "calibration_method": calibration_method.value,
        "random_seed": random_seed,
        "feature_schema": encoder.schema.model_dump(mode="json"),
        "hyperparameters": hyperparameters,
        "train_parent_groups_sha256": _group_digest(train),
        "calibration_parent_groups_sha256": calibration_digest,
    }
    configuration_sha = _configuration_digest(configuration)
    manifest = EvidenceModelManifestV1(
        model_id=f"{stage.value}-{estimator_family.value}-{configuration_sha[:12]}",
        stage=stage,
        role=role,
        estimator_family=estimator_family,
        calibration_method=calibration_method,
        calibration_uses_held_out_groups=calibration_method != CalibrationMethod.NONE,
        feature_schema=encoder.schema,
        train_parent_groups_sha256=_group_digest(train),
        calibration_parent_groups_sha256=calibration_digest,
        configuration_sha256=configuration_sha,
        random_seed=random_seed,
        sklearn_version=str(sklearn.__version__),
        hyperparameters=hyperparameters,
        provenance=(
            ProvenanceRecord(
                source="synthaudit",
                source_version=__version__,
                adapter="fit_evidence_model",
                adapter_version="1",
                artifact_sha256=configuration_sha,
                license="Apache-2.0",
            ),
        ),
    )
    return TrainedEvidenceModel(
        estimator=estimator,
        calibrator=calibrator,
        encoder=encoder,
        manifest=manifest,
    )


def transparent_baseline(
    example: EvidenceExampleV1,
    *,
    role: EvidenceModelRole,
) -> TransparentBaselineResultV1:
    if role not in {
        EvidenceModelRole.CORPUS_FAMILIARITY_BASELINE,
        EvidenceModelRole.DETERMINISTIC_STRUCTURAL_BASELINE,
    }:
        raise ValueError("transparent baseline requires corpus or deterministic structural role")
    group = next(iter(feature_groups_for_role(role)))
    selected = [feature for feature in example.features if feature.group == group]
    available = {
        feature.feature_id: float(feature.value)
        for feature in selected
        if feature.availability == EvidenceAvailability.AVAILABLE and feature.value is not None
    }
    missing = tuple(
        feature.feature_id
        for feature in selected
        if feature.availability != EvidenceAvailability.AVAILABLE
    )
    if not selected or not available:
        return TransparentBaselineResultV1(
            example_id=example.example_id,
            stage=example.stage,
            role=role.value,
            availability=EvidenceAvailability.UNAVAILABLE,
            missing_features=missing or ("no selected baseline features",),
            semantics=(
                "corpus_familiarity_not_plausibility"
                if role == EvidenceModelRole.CORPUS_FAMILIARITY_BASELINE
                else "deterministic_representation_support_not_experimental_feasibility"
            ),
            provenance=example.provenance,
        )
    score = float(np.mean(tuple(available.values())))
    if role == EvidenceModelRole.DETERMINISTIC_STRUCTURAL_BASELINE:
        score = float(all(value >= 0.5 for value in available.values()))
    return TransparentBaselineResultV1(
        example_id=example.example_id,
        stage=example.stage,
        role=role.value,
        availability=EvidenceAvailability.AVAILABLE,
        score=score,
        component_values=available,
        missing_features=missing,
        semantics=(
            "corpus_familiarity_not_plausibility"
            if role == EvidenceModelRole.CORPUS_FAMILIARITY_BASELINE
            else "deterministic_representation_support_not_experimental_feasibility"
        ),
        provenance=example.provenance,
    )
