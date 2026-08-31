"""Evidence feature extraction that preserves independent semantic groups."""

from __future__ import annotations

import math
from collections.abc import Sequence

from synthaudit import __version__
from synthaudit.models.evidence import EvidenceFeatureV1, FeatureGroup
from synthaudit.models.uncertainty import provider_disagreement
from synthaudit.novelty.models import MultiViewNoveltyResultV1, NoveltyMetricV1
from synthaudit.providers.forward import ForwardReactionEvidenceV1
from synthaudit.schema.common import ProvenanceRecord
from synthaudit.schema.evidence import EvidenceAvailability
from synthaudit.schema.results import CheckStatus, ReactionAuditResultV1, StageAuditResultV1


def _provenance(component: str) -> tuple[ProvenanceRecord, ...]:
    return (
        ProvenanceRecord(
            source="synthaudit",
            source_version=__version__,
            adapter=component,
            adapter_version="1",
            license="Apache-2.0",
        ),
    )


def _available(
    feature_id: str,
    group: FeatureGroup,
    value: float,
    interpretation: str,
    provenance: Sequence[ProvenanceRecord] = (),
) -> EvidenceFeatureV1:
    return EvidenceFeatureV1(
        feature_id=feature_id,
        group=group,
        availability=EvidenceAvailability.AVAILABLE,
        value=value,
        interpretation=interpretation,
        provenance=tuple(provenance) or _provenance("EvidenceFeatureExtractor"),
    )


def _missing(
    feature_id: str,
    group: FeatureGroup,
    reason: str,
    interpretation: str,
    *,
    availability: EvidenceAvailability = EvidenceAvailability.UNAVAILABLE,
) -> EvidenceFeatureV1:
    return EvidenceFeatureV1(
        feature_id=feature_id,
        group=group,
        availability=availability,
        missing_reason=reason,
        interpretation=interpretation,
    )


def _metric_feature(
    feature_id: str,
    metric: NoveltyMetricV1,
    *,
    group: FeatureGroup = FeatureGroup.CORPUS_FAMILIARITY,
) -> EvidenceFeatureV1:
    if (
        metric.availability == EvidenceAvailability.AVAILABLE
        and metric.maximum_similarity is not None
    ):
        return _available(
            feature_id,
            group,
            metric.maximum_similarity,
            "Maximum declared-corpus similarity; familiarity evidence, not plausibility.",
            metric.provenance,
        )
    return _missing(
        feature_id,
        group,
        "; ".join(metric.missing_reasons) or "novelty metric unavailable",
        "Corpus familiarity feature is missing and receives an explicit missing flag.",
        availability=metric.availability,
    )


def _stage_features(
    stage: StageAuditResultV1,
    *,
    prefix: str,
    group: FeatureGroup,
) -> tuple[EvidenceFeatureV1, ...]:
    total = len(stage.checks)
    pass_fraction = sum(check.status == CheckStatus.PASS for check in stage.checks) / total
    blocking_clear = float(
        not any(
            check.status == CheckStatus.FAIL and check.severity.value == "blocking"
            for check in stage.checks
        )
    )
    return (
        _available(
            f"{prefix}.pass_fraction",
            group,
            pass_fraction,
            "Fraction of deterministic checks with explicit pass status.",
        ),
        _available(
            f"{prefix}.blocking_clear",
            group,
            blocking_clear,
            "One only when no blocking deterministic check failed.",
        ),
    )


def _check_support(
    audit: StageAuditResultV1,
    check_id: str,
    *,
    feature_id: str,
    group: FeatureGroup,
) -> EvidenceFeatureV1:
    check = next((item for item in audit.checks if item.check_id == check_id), None)
    if check is None or check.status in {
        CheckStatus.UNAVAILABLE,
        CheckStatus.INDETERMINATE,
        CheckStatus.UNSUPPORTED,
    }:
        return _missing(
            feature_id,
            group,
            "source audit check unavailable or indeterminate",
            "Audit-derived support feature is unavailable.",
            availability=(
                EvidenceAvailability.INDETERMINATE
                if check is not None and check.status == CheckStatus.INDETERMINATE
                else EvidenceAvailability.UNAVAILABLE
            ),
        )
    return _available(
        feature_id,
        group,
        float(check.status == CheckStatus.PASS),
        "Binary support from the named deterministic audit check.",
    )


def extract_reaction_evidence_features(
    audit: ReactionAuditResultV1,
    *,
    novelty: MultiViewNoveltyResultV1 | None = None,
    forward: ForwardReactionEvidenceV1 | None = None,
    condition_conflict_count: int | None = None,
    provider_scores: dict[str, float | None] | None = None,
) -> tuple[EvidenceFeatureV1, ...]:
    features: list[EvidenceFeatureV1] = []
    if novelty is None:
        for feature_id in (
            "corpus.product_nearest_similarity",
            "corpus.precursor_nearest_similarity",
            "corpus.transformation_nearest_similarity",
            "corpus.centre_nearest_similarity",
            "corpus.class_log_frequency",
            "corpus.classifier_recognized",
            "corpus.embedding_max_similarity",
            "corpus.percentile",
        ):
            features.append(
                _missing(
                    feature_id,
                    FeatureGroup.CORPUS_FAMILIARITY,
                    "multi-view novelty result was not supplied",
                    "Corpus-familiarity evidence is unavailable.",
                )
            )
    else:
        features.extend(
            (
                _metric_feature(
                    "corpus.product_nearest_similarity",
                    novelty.structure_novelty.product_morgan,
                ),
                _metric_feature(
                    "corpus.precursor_nearest_similarity",
                    novelty.structure_novelty.precursor_morgan,
                ),
                _metric_feature(
                    "corpus.transformation_nearest_similarity",
                    novelty.reaction_difference_novelty.reaction_difference,
                ),
                _metric_feature(
                    "corpus.centre_nearest_similarity",
                    novelty.edit_semantic_novelty.reaction_centre_neighbourhood,
                ),
                _metric_feature(
                    "corpus.embedding_max_similarity",
                    novelty.learned_transformation_novelty.reactseq_meo,
                ),
            )
        )
        taxonomy = novelty.taxonomy_recognition
        if (
            taxonomy.availability == EvidenceAvailability.AVAILABLE
            and taxonomy.class_frequency is not None
        ):
            features.append(
                _available(
                    "corpus.class_log_frequency",
                    FeatureGroup.CORPUS_FAMILIARITY,
                    math.log1p(taxonomy.class_frequency),
                    "Log-transformed declared-corpus reaction-class frequency.",
                    taxonomy.provenance,
                )
            )
        else:
            features.append(
                _missing(
                    "corpus.class_log_frequency",
                    FeatureGroup.CORPUS_FAMILIARITY,
                    "reaction-class frequency unavailable",
                    "Class-frequency familiarity evidence is unavailable.",
                    availability=taxonomy.availability,
                )
            )
        if (
            taxonomy.availability == EvidenceAvailability.AVAILABLE
            and taxonomy.recognized is not None
        ):
            features.append(
                _available(
                    "corpus.classifier_recognized",
                    FeatureGroup.CORPUS_FAMILIARITY,
                    float(taxonomy.recognized),
                    "Provider taxonomy recognition indicator, separate from raw confidence.",
                    taxonomy.provenance,
                )
            )
        else:
            features.append(
                _missing(
                    "corpus.classifier_recognized",
                    FeatureGroup.CORPUS_FAMILIARITY,
                    "reaction-class recognition unavailable",
                    "Classifier recognition evidence is unavailable.",
                    availability=taxonomy.availability,
                )
            )
        features.append(
            _missing(
                "corpus.percentile",
                FeatureGroup.CORPUS_FAMILIARITY,
                "reference-corpus percentile was not computed",
                "No percentile is inferred from nearest-neighbour similarity.",
            )
        )

    features.extend(
        (
            _available(
                "structural.structurally_valid",
                FeatureGroup.STRUCTURAL,
                float(audit.structurally_valid),
                "Observed staged executor structural-validity flag.",
                audit.provenance,
            ),
            _available(
                "structural.reaction_blocking_clear",
                FeatureGroup.STRUCTURAL,
                float(not audit.blocking),
                "One only when the reaction audit has no blocking failure.",
                audit.provenance,
            ),
            *_stage_features(
                audit.structural_audit,
                prefix="structural",
                group=FeatureGroup.STRUCTURAL,
            ),
            _check_support(
                audit.structural_audit,
                "structural.atom_conservation",
                feature_id="structural.atom_conservation_supported",
                group=FeatureGroup.STRUCTURAL,
            ),
            *_stage_features(
                audit.reaction_centre_audit,
                prefix="centre",
                group=FeatureGroup.REACTION_CENTRE,
            ),
            *_stage_features(
                audit.completion_audit,
                prefix="completion",
                group=FeatureGroup.COMPLETION,
            ),
            *_stage_features(
                audit.stereo_audit,
                prefix="stereo",
                group=FeatureGroup.STEREO,
            ),
        )
    )
    if condition_conflict_count is None:
        features.append(
            _missing(
                "condition.conflict_clear",
                FeatureGroup.CONDITION,
                "condition-conflict provider was not supplied",
                "Condition compatibility remains unavailable.",
            )
        )
    else:
        features.append(
            _available(
                "condition.conflict_clear",
                FeatureGroup.CONDITION,
                float(condition_conflict_count == 0),
                "One only when the configured condition provider reports no conflict.",
            )
        )

    hits = novelty.top_precedents if novelty is not None else ()
    for axis, attribute in (
        ("transformation", "transformation_similarity"),
        ("substrate", "substrate_similarity"),
        ("centre", "reaction_centre_similarity"),
        ("stereo", "stereo_similarity"),
    ):
        values = [float(value) for hit in hits if (value := getattr(hit, attribute)) is not None]
        if values:
            features.append(
                _available(
                    f"precedent.{axis}_maximum_similarity",
                    FeatureGroup.PRECEDENT,
                    max(values),
                    "Maximum retrieved precedent-axis similarity; support context only.",
                    hits[0].provenance,
                )
            )
        else:
            features.append(
                _missing(
                    f"precedent.{axis}_maximum_similarity",
                    FeatureGroup.PRECEDENT,
                    f"{axis} precedent evidence unavailable",
                    "Precedent evidence is missing and is not treated as validation.",
                )
            )

    if forward is not None and forward.availability == EvidenceAvailability.AVAILABLE:
        for feature_id, value, interpretation in (
            (
                "forward.target_similarity",
                forward.target_similarity,
                "Configured forward-provider target similarity.",
            ),
            (
                "forward.inverse_target_rank",
                1.0 / forward.target_rank if forward.target_rank else None,
                "Inverse target rank from the configured forward provider.",
            ),
            (
                "forward.model_uncertainty",
                forward.model_uncertainty,
                "Raw uncertainty reported by the configured forward provider.",
            ),
        ):
            features.append(
                _available(
                    feature_id,
                    FeatureGroup.FORWARD_MODEL,
                    float(value),
                    interpretation,
                    forward.provenance,
                )
                if value is not None
                else _missing(
                    feature_id,
                    FeatureGroup.FORWARD_MODEL,
                    "configured forward provider omitted this field",
                    interpretation,
                )
            )
    else:
        reason = (
            "; ".join(forward.missing_reasons)
            if forward is not None
            else "forward provider was not supplied"
        )
        for feature_id in (
            "forward.target_similarity",
            "forward.inverse_target_rank",
            "forward.model_uncertainty",
        ):
            features.append(
                _missing(
                    feature_id,
                    FeatureGroup.FORWARD_MODEL,
                    reason,
                    "Forward-model evidence is unavailable.",
                )
            )

    disagreement = provider_disagreement(provider_scores or {})
    if disagreement.availability == EvidenceAvailability.AVAILABLE:
        assert disagreement.score_range is not None
        features.append(
            _available(
                "providers.score_range",
                FeatureGroup.PROVIDER_AGREEMENT,
                disagreement.score_range,
                "Range across independent provider scores; higher means more disagreement.",
            )
        )
    else:
        features.append(
            _missing(
                "providers.score_range",
                FeatureGroup.PROVIDER_AGREEMENT,
                "fewer than two independent provider scores are available",
                "Provider-agreement evidence is unavailable.",
            )
        )
    features.append(
        _missing(
            "route.context_supported",
            FeatureGroup.ROUTE,
            "single-reaction feature extraction has no RouteAudit result",
            "Route-context support remains separate from single-step evidence.",
        )
    )
    return tuple(features)
