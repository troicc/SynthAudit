"""Train-only feature encoding with explicit missing flags and OOD diagnostics."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence, Set
from dataclasses import dataclass

import numpy as np

from synthaudit.models.evidence import (
    EvidenceExampleSplit,
    EvidenceExampleV1,
    EvidenceModelRole,
    FeatureGroup,
    FeatureSchemaV1,
)
from synthaudit.schema.evidence import EvidenceAvailability

PLAUSIBILITY_GROUPS = frozenset(
    {
        FeatureGroup.STRUCTURAL,
        FeatureGroup.REACTION_CENTRE,
        FeatureGroup.COMPLETION,
        FeatureGroup.STEREO,
        FeatureGroup.CONDITION,
        FeatureGroup.PRECEDENT,
        FeatureGroup.FORWARD_MODEL,
        FeatureGroup.PROVIDER_AGREEMENT,
        FeatureGroup.ROUTE,
    }
)


def feature_groups_for_role(role: EvidenceModelRole) -> frozenset[FeatureGroup]:
    if role == EvidenceModelRole.CORPUS_FAMILIARITY_BASELINE:
        return frozenset({FeatureGroup.CORPUS_FAMILIARITY})
    if role == EvidenceModelRole.DETERMINISTIC_STRUCTURAL_BASELINE:
        return frozenset({FeatureGroup.STRUCTURAL})
    if role == EvidenceModelRole.REACTION_CENTRE_MODEL:
        return frozenset(
            {
                FeatureGroup.STRUCTURAL,
                FeatureGroup.REACTION_CENTRE,
                FeatureGroup.CONDITION,
                FeatureGroup.PRECEDENT,
                FeatureGroup.FORWARD_MODEL,
                FeatureGroup.PROVIDER_AGREEMENT,
            }
        )
    if role == EvidenceModelRole.COMPLETION_MODEL:
        return frozenset(
            {
                FeatureGroup.STRUCTURAL,
                FeatureGroup.REACTION_CENTRE,
                FeatureGroup.COMPLETION,
                FeatureGroup.CONDITION,
                FeatureGroup.PRECEDENT,
                FeatureGroup.FORWARD_MODEL,
                FeatureGroup.PROVIDER_AGREEMENT,
            }
        )
    if role == EvidenceModelRole.STEREO_MODEL:
        return frozenset(
            {
                FeatureGroup.STRUCTURAL,
                FeatureGroup.STEREO,
                FeatureGroup.PRECEDENT,
                FeatureGroup.PROVIDER_AGREEMENT,
            }
        )
    return PLAUSIBILITY_GROUPS


def _parent_digest(examples: Sequence[EvidenceExampleV1]) -> str:
    values = "\n".join(sorted({example.parent_group_id for example in examples}))
    return hashlib.sha256(values.encode()).hexdigest()


@dataclass(frozen=True)
class EncodedEvidenceMatrix:
    values: np.ndarray
    labels: np.ndarray
    example_ids: tuple[str, ...]
    parent_groups: tuple[str, ...]
    missing_feature_flags: tuple[tuple[str, ...], ...]
    missing_feature_fractions: tuple[float, ...]
    ood_max_absolute_zscores: tuple[float, ...]


class EvidenceFeatureEncoder:
    """Median-impute from training only and append one visible flag per missing feature."""

    def __init__(self, schema: FeatureSchemaV1) -> None:
        self.schema = schema

    @classmethod
    def fit(
        cls,
        examples: Sequence[EvidenceExampleV1],
        *,
        allowed_groups: Set[FeatureGroup],
    ) -> EvidenceFeatureEncoder:
        if not examples:
            raise ValueError("feature encoder requires training examples")
        if any(example.split != EvidenceExampleSplit.TRAIN for example in examples):
            raise ValueError("feature encoder may be fit only on the training split")
        stage = examples[0].stage
        if any(example.stage != stage for example in examples):
            raise ValueError("feature encoder examples must share one evidence stage")
        reference = {
            feature.feature_id: feature.group
            for feature in examples[0].features
            if feature.group in allowed_groups
        }
        if not reference:
            raise ValueError("selected feature groups contain no features")
        for example in examples[1:]:
            current = {
                feature.feature_id: feature.group
                for feature in example.features
                if feature.group in allowed_groups
            }
            if current != reference:
                raise ValueError("all examples must expose the same selected feature schema")
        ordered = tuple(sorted(reference))
        imputation: dict[str, float] = {}
        means: dict[str, float] = {}
        scales: dict[str, float] = {}
        for feature_id in ordered:
            observed = [
                float(feature.value)
                for example in examples
                for feature in example.features
                if feature.feature_id == feature_id
                and feature.availability == EvidenceAvailability.AVAILABLE
                and feature.value is not None
            ]
            if not observed:
                raise ValueError(f"training feature has no available values: {feature_id}")
            median = float(np.median(np.asarray(observed, dtype=float)))
            imputation[feature_id] = median
            completed = [
                next(
                    (
                        float(feature.value)
                        for feature in example.features
                        if feature.feature_id == feature_id
                        and feature.availability == EvidenceAvailability.AVAILABLE
                        and feature.value is not None
                    ),
                    median,
                )
                for example in examples
            ]
            means[feature_id] = float(np.mean(completed))
            standard_deviation = float(np.std(completed))
            scales[feature_id] = standard_deviation if standard_deviation > 1e-12 else 1.0
        schema = FeatureSchemaV1(
            ordered_feature_ids=ordered,
            feature_groups=reference,
            imputation_values=imputation,
            standardization_means=means,
            standardization_scales=scales,
            fit_parent_groups_sha256=_parent_digest(examples),
        )
        return cls(schema)

    def transform(self, examples: Sequence[EvidenceExampleV1]) -> EncodedEvidenceMatrix:
        rows: list[list[float]] = []
        flags_by_row: list[tuple[str, ...]] = []
        missing_fractions: list[float] = []
        ood_scores: list[float] = []
        for example in examples:
            features = {feature.feature_id: feature for feature in example.features}
            missing_schema = sorted(set(self.schema.ordered_feature_ids) - set(features))
            if missing_schema:
                raise ValueError(f"example omits declared features: {missing_schema}")
            numeric: list[float] = []
            flags: list[float] = []
            missing_names: list[str] = []
            zscores: list[float] = []
            for feature_id in self.schema.ordered_feature_ids:
                feature = features[feature_id]
                if feature.group != self.schema.feature_groups[feature_id]:
                    raise ValueError(f"feature group changed for {feature_id}")
                missing = feature.availability != EvidenceAvailability.AVAILABLE
                value = (
                    self.schema.imputation_values[feature_id] if missing else float(feature.value)  # type: ignore[arg-type]
                )
                zscore = (value - self.schema.standardization_means[feature_id]) / (
                    self.schema.standardization_scales[feature_id]
                )
                numeric.append(zscore)
                flags.append(float(missing))
                zscores.append(abs(zscore))
                if missing:
                    missing_names.append(f"{feature_id}{self.schema.missing_flag_suffix}")
            rows.append([*numeric, *flags])
            flags_by_row.append(tuple(missing_names))
            missing_fractions.append(len(missing_names) / len(self.schema.ordered_feature_ids))
            ood_scores.append(max(zscores, default=0.0))
        return EncodedEvidenceMatrix(
            values=np.asarray(rows, dtype=float),
            labels=np.asarray([example.target_label for example in examples], dtype=int),
            example_ids=tuple(example.example_id for example in examples),
            parent_groups=tuple(example.parent_group_id for example in examples),
            missing_feature_flags=tuple(flags_by_row),
            missing_feature_fractions=tuple(missing_fractions),
            ood_max_absolute_zscores=tuple(ood_scores),
        )
