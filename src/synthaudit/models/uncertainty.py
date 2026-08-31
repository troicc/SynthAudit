"""Parent-group bootstrap, provider disagreement, and explicit abstention."""

from __future__ import annotations

import hashlib
import random
from collections.abc import Mapping, Sequence, Set
from dataclasses import dataclass

import numpy as np

from synthaudit import __version__
from synthaudit.models.evidence import (
    AbstentionPolicyV1,
    CalibrationMethod,
    EstimatorFamily,
    EvidenceExampleV1,
    EvidenceModelRole,
    EvidencePredictionV1,
    EvidenceStage,
    FeatureGroup,
    ProviderDisagreementV1,
)
from synthaudit.models.training import TrainedEvidenceModel, fit_evidence_model
from synthaudit.schema.common import ProvenanceRecord
from synthaudit.schema.evidence import EvidenceAvailability


def provider_disagreement(
    provider_scores: Mapping[str, float | None],
) -> ProviderDisagreementV1:
    available = {
        provider: float(score) for provider, score in provider_scores.items() if score is not None
    }
    missing = tuple(
        sorted(provider for provider, score in provider_scores.items() if score is None)
    )
    if len(available) < 2:
        return ProviderDisagreementV1(
            availability=EvidenceAvailability.UNAVAILABLE,
            missing_providers=missing,
            interpretation="Provider disagreement is unavailable with fewer than two scores.",
        )
    values = np.asarray(tuple(available.values()), dtype=float)
    return ProviderDisagreementV1(
        availability=EvidenceAvailability.AVAILABLE,
        provider_scores=available,
        score_range=float(np.max(values) - np.min(values)),
        score_standard_deviation=float(np.std(values)),
        missing_providers=missing,
        interpretation=(
            "Dispersion across independent evidence providers; not experimental uncertainty."
        ),
    )


@dataclass(frozen=True)
class BootstrapEvidenceEnsemble:
    members: tuple[TrainedEvidenceModel, ...]

    def scores(self, examples: Sequence[EvidenceExampleV1]) -> np.ndarray:
        if len(self.members) < 2:
            raise ValueError("bootstrap ensemble requires at least two fitted members")
        columns = []
        for member in self.members:
            batch = member.score(examples)
            columns.append(
                batch.calibrated_scores if batch.calibrated_scores is not None else batch.raw_scores
            )
        return np.column_stack(columns)


def _bootstrap_training_sample(
    train: Sequence[EvidenceExampleV1],
    *,
    rng: random.Random,
    member_index: int,
) -> tuple[EvidenceExampleV1, ...]:
    by_group: dict[str, list[EvidenceExampleV1]] = {}
    for example in train:
        by_group.setdefault(example.parent_group_id, []).append(example)
    groups = sorted(by_group)
    selected = [rng.choice(groups) for _ in groups]
    sampled: list[EvidenceExampleV1] = []
    for draw_index, group in enumerate(selected):
        sampled.extend(
            example.model_copy(
                update={
                    "example_id": (f"{example.example_id}::bootstrap-{member_index}-{draw_index}")
                }
            )
            for example in by_group[group]
        )
    return tuple(sampled)


def fit_bootstrap_ensemble(
    train: Sequence[EvidenceExampleV1],
    calibration: Sequence[EvidenceExampleV1],
    *,
    stage: EvidenceStage,
    role: EvidenceModelRole,
    estimator_family: EstimatorFamily,
    calibration_method: CalibrationMethod,
    random_seed: int,
    member_count: int = 20,
    feature_groups: Set[FeatureGroup] | None = None,
) -> BootstrapEvidenceEnsemble:
    if member_count < 2:
        raise ValueError("bootstrap ensemble requires at least two members")
    rng = random.Random(random_seed)
    members: list[TrainedEvidenceModel] = []
    attempts = 0
    maximum_attempts = member_count * 20
    while len(members) < member_count and attempts < maximum_attempts:
        attempts += 1
        sampled = _bootstrap_training_sample(
            train,
            rng=rng,
            member_index=len(members),
        )
        if len({example.target_label for example in sampled}) != 2:
            continue
        members.append(
            fit_evidence_model(
                sampled,
                calibration,
                stage=stage,
                role=role,
                estimator_family=estimator_family,
                calibration_method=calibration_method,
                random_seed=random_seed + len(members) + 1,
                feature_groups=feature_groups,
            )
        )
    if len(members) != member_count:
        raise ValueError("could not form class-complete parent-group bootstrap samples")
    return BootstrapEvidenceEnsemble(tuple(members))


def fit_abstention_policy_from_calibration(
    *,
    policy_id: str,
    calibration_parent_groups: Sequence[str],
    bootstrap_standard_deviations: Sequence[float],
    missing_feature_fractions: Sequence[float],
    ood_max_absolute_zscores: Sequence[float],
    provider_score_ranges: Sequence[float],
    quantile: float = 0.9,
) -> AbstentionPolicyV1:
    arrays = tuple(
        np.asarray(values, dtype=float)
        for values in (
            bootstrap_standard_deviations,
            missing_feature_fractions,
            ood_max_absolute_zscores,
            provider_score_ranges,
        )
    )
    if not 0 < quantile <= 1:
        raise ValueError("abstention calibration quantile must be in (0, 1]")
    if any(not len(values) for values in arrays):
        raise ValueError("abstention calibration requires every diagnostic on held-out data")
    if not calibration_parent_groups:
        raise ValueError("abstention calibration requires held-out parent groups")
    if any(len(values) != len(calibration_parent_groups) for values in arrays):
        raise ValueError("abstention diagnostics must align with held-out calibration examples")
    digest = hashlib.sha256("\n".join(sorted(set(calibration_parent_groups))).encode()).hexdigest()
    thresholds = [float(np.quantile(values, quantile)) for values in arrays]
    return AbstentionPolicyV1(
        policy_id=policy_id,
        threshold_source="held_out_calibration",
        maximum_bootstrap_standard_deviation=thresholds[0],
        maximum_missing_feature_fraction=thresholds[1],
        maximum_ood_zscore=thresholds[2],
        maximum_provider_score_range=thresholds[3],
        calibration_parent_groups_sha256=digest,
    )


def predict_with_uncertainty(
    model: TrainedEvidenceModel,
    examples: Sequence[EvidenceExampleV1],
    *,
    policy: AbstentionPolicyV1,
    bootstrap: BootstrapEvidenceEnsemble | None,
    provider_scores_by_example: Mapping[str, Mapping[str, float | None]],
) -> tuple[EvidencePredictionV1, ...]:
    batch = model.score(examples)
    bootstrap_scores = bootstrap.scores(examples) if bootstrap is not None else None
    predictions: list[EvidencePredictionV1] = []
    for index, example in enumerate(examples):
        disagreement = provider_disagreement(provider_scores_by_example.get(example.example_id, {}))
        reasons: list[str] = []
        calibrated = (
            float(batch.calibrated_scores[index]) if batch.calibrated_scores is not None else None
        )
        if calibrated is None:
            reasons.append("held-out calibration unavailable")
        bootstrap_mean: float | None = None
        bootstrap_standard_deviation: float | None = None
        bootstrap_interval: tuple[float, float] | None = None
        member_count = 0
        if bootstrap_scores is None:
            reasons.append("parent-group bootstrap uncertainty unavailable")
        else:
            values = bootstrap_scores[index]
            member_count = len(values)
            bootstrap_mean = float(np.mean(values))
            bootstrap_standard_deviation = float(np.std(values))
            bootstrap_interval = (
                float(np.quantile(values, 0.05)),
                float(np.quantile(values, 0.95)),
            )
            if bootstrap_standard_deviation > policy.maximum_bootstrap_standard_deviation:
                reasons.append("bootstrap uncertainty exceeds policy threshold")
        missing_fraction = batch.encoded.missing_feature_fractions[index]
        if missing_fraction > policy.maximum_missing_feature_fraction:
            reasons.append("missing-evidence fraction exceeds policy threshold")
        ood_score = batch.encoded.ood_max_absolute_zscores[index]
        if ood_score > policy.maximum_ood_zscore:
            reasons.append("out-of-distribution diagnostic exceeds policy threshold")
        if (
            disagreement.availability == EvidenceAvailability.AVAILABLE
            and disagreement.score_range is not None
            and disagreement.score_range > policy.maximum_provider_score_range
        ):
            reasons.append("provider disagreement exceeds policy threshold")
        predictions.append(
            EvidencePredictionV1(
                example_id=example.example_id,
                stage=example.stage,
                model_id=model.manifest.model_id,
                model_configuration_sha256=model.manifest.configuration_sha256,
                raw_model_score=float(batch.raw_scores[index]),
                calibrated_evidence_support_score=calibrated,
                bootstrap_member_count=member_count,
                bootstrap_mean_score=bootstrap_mean,
                bootstrap_standard_deviation=bootstrap_standard_deviation,
                bootstrap_interval_90=bootstrap_interval,
                provider_disagreement=disagreement,
                missing_feature_flags=batch.encoded.missing_feature_flags[index],
                missing_feature_fraction=missing_fraction,
                ood_max_absolute_zscore=ood_score,
                abstained=bool(reasons),
                abstention_reasons=tuple(reasons),
                provenance=(
                    ProvenanceRecord(
                        source="synthaudit",
                        source_version=__version__,
                        adapter="predict_with_uncertainty",
                        adapter_version="1",
                        artifact_sha256=model.manifest.configuration_sha256,
                        license="Apache-2.0",
                    ),
                ),
            )
        )
    return tuple(predictions)
