"""Versioned contracts for stage-specific evidence models and their non-claims."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field, JsonValue, model_validator

from synthaudit.schema.common import ProvenanceRecord, StrictModel
from synthaudit.schema.evidence import EvidenceAvailability


class FeatureGroup(StrEnum):
    CORPUS_FAMILIARITY = "corpus_familiarity"
    STRUCTURAL = "structural"
    REACTION_CENTRE = "reaction_centre"
    COMPLETION = "completion"
    STEREO = "stereo"
    CONDITION = "condition"
    PRECEDENT = "precedent"
    FORWARD_MODEL = "forward_model"
    PROVIDER_AGREEMENT = "provider_agreement"
    ROUTE = "route"


class EvidenceStage(StrEnum):
    REACTION_CENTRE = "reaction_centre_supported"
    COMPLETION_GIVEN_CENTRE = "completion_supported_given_reaction_centre"
    STEREO = "stereo_specification_supported"
    ROUTE_CONTEXT = "route_context_supported"


class EvidenceModelRole(StrEnum):
    CORPUS_FAMILIARITY_BASELINE = "corpus_familiarity_baseline"
    DETERMINISTIC_STRUCTURAL_BASELINE = "deterministic_structural_check_baseline"
    REACTION_CENTRE_MODEL = "reaction_centre_evidence_model"
    COMPLETION_MODEL = "completion_evidence_model"
    STEREO_MODEL = "stereo_evidence_model"
    FULL_EVIDENCE_ENSEMBLE = "full_evidence_ensemble"


class EstimatorFamily(StrEnum):
    LOGISTIC_REGRESSION = "logistic_regression"
    HIST_GRADIENT_BOOSTING = "hist_gradient_boosting_classifier"


class CalibrationMethod(StrEnum):
    NONE = "none"
    PLATT = "platt"
    ISOTONIC = "isotonic"


class EvidenceExampleSplit(StrEnum):
    TRAIN = "train"
    CALIBRATION = "calibration"
    TEST = "test"
    OOD_SCAFFOLD = "ood_scaffold"
    OOD_REACTION_CLASS = "ood_reaction_class"


class EvidenceStagePlanV1(StrictModel):
    stage: EvidenceStage
    role: EvidenceModelRole
    estimator_families: tuple[EstimatorFamily, ...] = Field(min_length=1)
    calibration_methods: tuple[CalibrationMethod, ...] = Field(min_length=1)
    feature_groups: tuple[FeatureGroup, ...] = Field(min_length=1)
    random_seed: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_stage_plan(self) -> EvidenceStagePlanV1:
        expected_role = {
            EvidenceStage.REACTION_CENTRE: EvidenceModelRole.REACTION_CENTRE_MODEL,
            EvidenceStage.COMPLETION_GIVEN_CENTRE: EvidenceModelRole.COMPLETION_MODEL,
            EvidenceStage.STEREO: EvidenceModelRole.STEREO_MODEL,
            EvidenceStage.ROUTE_CONTEXT: EvidenceModelRole.FULL_EVIDENCE_ENSEMBLE,
        }[self.stage]
        if self.role != expected_role:
            raise ValueError("stage plan role does not match the stage quantity")
        if len(self.estimator_families) != len(set(self.estimator_families)):
            raise ValueError("stage-plan estimator families must be unique")
        if len(self.calibration_methods) != len(set(self.calibration_methods)):
            raise ValueError("stage-plan calibration methods must be unique")
        if len(self.feature_groups) != len(set(self.feature_groups)):
            raise ValueError("stage-plan feature groups must be unique")
        if FeatureGroup.CORPUS_FAMILIARITY in self.feature_groups:
            raise ValueError("primary plausibility stage plans must exclude corpus familiarity")
        return self


class EvidenceModelPlanV1(StrictModel):
    schema_version: Literal["synthaudit.evidence-model-plan/1"] = "synthaudit.evidence-model-plan/1"
    plan_id: str = Field(min_length=1)
    status: Literal["contract_only_no_trained_research_artifact"] = (
        "contract_only_no_trained_research_artifact"
    )
    baseline_roles: tuple[EvidenceModelRole, ...] = Field(min_length=6, max_length=6)
    stage_models: tuple[EvidenceStagePlanV1, ...] = Field(min_length=4, max_length=4)
    split_grouping: Literal["parent_group_id"] = "parent_group_id"
    test_split_use: Literal["evaluation_only_no_calibration_or_threshold_selection"] = (
        "evaluation_only_no_calibration_or_threshold_selection"
    )
    bootstrap_grouping: Literal["parent_group_id"] = "parent_group_id"
    bootstrap_member_count: int = Field(ge=2)
    abstention_threshold_source: Literal["held_out_calibration"] = "held_out_calibration"
    ood_splits: tuple[EvidenceExampleSplit, ...] = Field(min_length=1)
    model_selection_status: Literal["not_run"] = "not_run"
    mandatory_notice: Literal[
        "SynthAudit estimates representation validity, corpus novelty and evidence-based plausibility. It does not establish experimental feasibility, yield, selectivity, safety or scalability."
    ] = (
        "SynthAudit estimates representation validity, corpus novelty and evidence-based "
        "plausibility. It does not establish experimental feasibility, yield, selectivity, "
        "safety or scalability."
    )

    @model_validator(mode="after")
    def validate_complete_plan(self) -> EvidenceModelPlanV1:
        expected_roles = set(EvidenceModelRole)
        if set(self.baseline_roles) != expected_roles:
            raise ValueError("model plan must declare all six required baseline roles exactly")
        expected_stages = set(EvidenceStage)
        if {item.stage for item in self.stage_models} != expected_stages:
            raise ValueError("model plan must declare all four stage-specific quantities")
        required_estimators = set(EstimatorFamily)
        required_calibrators = {CalibrationMethod.PLATT, CalibrationMethod.ISOTONIC}
        for stage_plan in self.stage_models:
            if set(stage_plan.estimator_families) != required_estimators:
                raise ValueError("every stage plan must exercise logistic regression and HGB")
            if set(stage_plan.calibration_methods) != required_calibrators:
                raise ValueError("every stage plan must exercise Platt and isotonic calibration")
        if set(self.ood_splits) != {
            EvidenceExampleSplit.OOD_SCAFFOLD,
            EvidenceExampleSplit.OOD_REACTION_CLASS,
        }:
            raise ValueError("model plan must declare scaffold and reaction-class OOD splits")
        return self


class EvidenceFeatureV1(StrictModel):
    feature_id: str = Field(min_length=1)
    group: FeatureGroup
    availability: EvidenceAvailability
    value: float | None = None
    missing_reason: str | None = None
    interpretation: str = Field(min_length=1)
    provenance: tuple[ProvenanceRecord, ...] = ()

    @model_validator(mode="after")
    def validate_availability_contract(self) -> EvidenceFeatureV1:
        if self.availability == EvidenceAvailability.AVAILABLE:
            if self.value is None:
                raise ValueError("available evidence feature requires a numeric value")
            if self.missing_reason is not None:
                raise ValueError("available evidence feature cannot contain a missing reason")
            if not self.provenance:
                raise ValueError("available evidence feature requires provenance")
        elif self.value is not None or not self.missing_reason:
            raise ValueError("missing evidence feature requires a reason and no numeric value")
        return self


class EvidenceExampleV1(StrictModel):
    schema_version: Literal["synthaudit.evidence-example/1"] = "synthaudit.evidence-example/1"
    example_id: str = Field(min_length=1)
    parent_group_id: str = Field(min_length=1)
    split: EvidenceExampleSplit
    stage: EvidenceStage
    target_label: Literal[0, 1]
    target_semantics: Literal["evidence_support_annotation"] = "evidence_support_annotation"
    target_source: str = Field(min_length=1)
    completion_condition_centre_supported: bool | None = None
    product_novelty: float | None = Field(default=None, ge=0, le=1)
    features: tuple[EvidenceFeatureV1, ...] = Field(min_length=1)
    provenance: tuple[ProvenanceRecord, ...] = Field(min_length=1)
    notice: Literal[
        "Evidence-model targets are support annotations, not experimental outcomes or feasibility probabilities."
    ] = (
        "Evidence-model targets are support annotations, not experimental outcomes or "
        "feasibility probabilities."
    )

    @model_validator(mode="after")
    def validate_example(self) -> EvidenceExampleV1:
        identifiers = [feature.feature_id for feature in self.features]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("evidence feature IDs must be unique within an example")
        if (
            self.stage == EvidenceStage.COMPLETION_GIVEN_CENTRE
            and self.completion_condition_centre_supported is not True
        ):
            raise ValueError(
                "completion training examples require reaction-centre support conditioning"
            )
        return self


class FeatureSchemaV1(StrictModel):
    schema_version: Literal["synthaudit.evidence-feature-schema/1"] = (
        "synthaudit.evidence-feature-schema/1"
    )
    ordered_feature_ids: tuple[str, ...] = Field(min_length=1)
    feature_groups: dict[str, FeatureGroup]
    imputation_values: dict[str, float]
    standardization_means: dict[str, float]
    standardization_scales: dict[str, float]
    missing_flag_suffix: Literal["__missing"] = "__missing"
    fit_parent_groups_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_keys(self) -> FeatureSchemaV1:
        if len(self.ordered_feature_ids) != len(set(self.ordered_feature_ids)):
            raise ValueError("ordered feature IDs must be unique")
        expected = set(self.ordered_feature_ids)
        for name, values in (
            ("feature groups", self.feature_groups),
            ("imputation values", self.imputation_values),
            ("standardization means", self.standardization_means),
            ("standardization scales", self.standardization_scales),
        ):
            if set(values) != expected:
                raise ValueError(f"{name} must cover every ordered feature exactly")
        if any(value <= 0 for value in self.standardization_scales.values()):
            raise ValueError("standardization scales must be positive")
        return self


class EvidenceModelManifestV1(StrictModel):
    schema_version: Literal["synthaudit.evidence-model-manifest/1"] = (
        "synthaudit.evidence-model-manifest/1"
    )
    model_id: str = Field(min_length=1)
    stage: EvidenceStage
    role: EvidenceModelRole
    estimator_family: EstimatorFamily
    calibration_method: CalibrationMethod
    calibration_uses_held_out_groups: bool
    feature_schema: FeatureSchemaV1
    train_parent_groups_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    calibration_parent_groups_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    configuration_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    random_seed: int = Field(ge=0)
    sklearn_version: str = Field(min_length=1)
    hyperparameters: dict[str, JsonValue]
    raw_score_semantics: Literal["uncalibrated_model_score"] = "uncalibrated_model_score"
    calibrated_score_semantics: Literal[
        "calibrated_evidence_support_score_not_experimental_probability"
    ] = "calibrated_evidence_support_score_not_experimental_probability"
    provenance: tuple[ProvenanceRecord, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_calibration_contract(self) -> EvidenceModelManifestV1:
        expected_stage = {
            EvidenceModelRole.REACTION_CENTRE_MODEL: EvidenceStage.REACTION_CENTRE,
            EvidenceModelRole.COMPLETION_MODEL: EvidenceStage.COMPLETION_GIVEN_CENTRE,
            EvidenceModelRole.STEREO_MODEL: EvidenceStage.STEREO,
        }.get(self.role)
        if expected_stage is not None and self.stage != expected_stage:
            raise ValueError("stage-specific model role does not match its stage")
        if self.calibration_method == CalibrationMethod.NONE:
            if self.calibration_uses_held_out_groups or self.calibration_parent_groups_sha256:
                raise ValueError("uncalibrated models cannot declare calibration groups")
        elif not self.calibration_uses_held_out_groups or not self.calibration_parent_groups_sha256:
            raise ValueError("calibration requires a digest of held-out parent groups")
        return self


class ProviderDisagreementV1(StrictModel):
    schema_version: Literal["synthaudit.provider-disagreement/1"] = (
        "synthaudit.provider-disagreement/1"
    )
    availability: EvidenceAvailability
    provider_scores: dict[str, float] = Field(default_factory=dict)
    score_range: float | None = Field(default=None, ge=0)
    score_standard_deviation: float | None = Field(default=None, ge=0)
    missing_providers: tuple[str, ...] = ()
    interpretation: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_disagreement(self) -> ProviderDisagreementV1:
        if any(not 0 <= value <= 1 for value in self.provider_scores.values()):
            raise ValueError("provider evidence scores must be within [0, 1]")
        if self.availability == EvidenceAvailability.AVAILABLE:
            if len(self.provider_scores) < 2:
                raise ValueError("provider disagreement requires at least two scores")
            if self.score_range is None or self.score_standard_deviation is None:
                raise ValueError("available disagreement requires range and standard deviation")
        elif (
            self.provider_scores
            or self.score_range is not None
            or self.score_standard_deviation is not None
        ):
            raise ValueError("unavailable provider disagreement cannot contain numeric evidence")
        return self


class AbstentionPolicyV1(StrictModel):
    schema_version: Literal["synthaudit.abstention-policy/1"] = "synthaudit.abstention-policy/1"
    policy_id: str = Field(min_length=1)
    threshold_source: Literal["prespecified", "held_out_calibration"]
    maximum_bootstrap_standard_deviation: float = Field(ge=0)
    maximum_missing_feature_fraction: float = Field(ge=0, le=1)
    maximum_ood_zscore: float = Field(ge=0)
    maximum_provider_score_range: float = Field(ge=0)
    calibration_parent_groups_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_source(self) -> AbstentionPolicyV1:
        if (
            self.threshold_source == "held_out_calibration"
            and self.calibration_parent_groups_sha256 is None
        ):
            raise ValueError("held-out calibration policy requires its parent-group digest")
        return self


class EvidencePredictionV1(StrictModel):
    schema_version: Literal["synthaudit.evidence-prediction/1"] = "synthaudit.evidence-prediction/1"
    example_id: str = Field(min_length=1)
    stage: EvidenceStage
    model_id: str = Field(min_length=1)
    model_configuration_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    raw_model_score: float = Field(ge=0, le=1)
    calibrated_evidence_support_score: float | None = Field(default=None, ge=0, le=1)
    bootstrap_member_count: int = Field(default=0, ge=0)
    bootstrap_mean_score: float | None = Field(default=None, ge=0, le=1)
    bootstrap_standard_deviation: float | None = Field(default=None, ge=0)
    bootstrap_interval_90: tuple[float, float] | None = None
    provider_disagreement: ProviderDisagreementV1 | None = None
    missing_feature_flags: tuple[str, ...] = ()
    missing_feature_fraction: float = Field(ge=0, le=1)
    ood_max_absolute_zscore: float = Field(ge=0)
    abstained: bool
    abstention_reasons: tuple[str, ...] = ()
    interpretation: Literal[
        "Evidence support score; not an experimental feasibility probability."
    ] = "Evidence support score; not an experimental feasibility probability."
    provenance: tuple[ProvenanceRecord, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_prediction(self) -> EvidencePredictionV1:
        if self.bootstrap_interval_90 is not None:
            lower, upper = self.bootstrap_interval_90
            if not 0 <= lower <= upper <= 1:
                raise ValueError("bootstrap interval must be ordered within [0, 1]")
            if self.bootstrap_mean_score is None or self.bootstrap_standard_deviation is None:
                raise ValueError("bootstrap interval requires mean and standard deviation")
            if self.bootstrap_member_count < 2:
                raise ValueError("bootstrap interval requires at least two ensemble members")
        elif self.bootstrap_member_count or any(
            value is not None
            for value in (self.bootstrap_mean_score, self.bootstrap_standard_deviation)
        ):
            raise ValueError("bootstrap fields must be populated together")
        if self.abstained != bool(self.abstention_reasons):
            raise ValueError("abstention flag must match explicit reasons")
        return self


class TransparentBaselineResultV1(StrictModel):
    schema_version: Literal["synthaudit.transparent-baseline/1"] = (
        "synthaudit.transparent-baseline/1"
    )
    example_id: str = Field(min_length=1)
    stage: EvidenceStage
    role: Literal["corpus_familiarity_baseline", "deterministic_structural_check_baseline"]
    availability: EvidenceAvailability
    score: float | None = Field(default=None, ge=0, le=1)
    component_values: dict[str, float] = Field(default_factory=dict)
    missing_features: tuple[str, ...] = ()
    semantics: Literal[
        "corpus_familiarity_not_plausibility",
        "deterministic_representation_support_not_experimental_feasibility",
    ]
    provenance: tuple[ProvenanceRecord, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_baseline(self) -> TransparentBaselineResultV1:
        if self.availability == EvidenceAvailability.AVAILABLE:
            if self.score is None or not self.component_values:
                raise ValueError("available baseline requires score and components")
        elif self.score is not None or self.component_values:
            raise ValueError("unavailable baseline cannot contain a score")
        return self


class ReliabilityBinV1(StrictModel):
    lower_bound: float = Field(ge=0, le=1)
    upper_bound: float = Field(ge=0, le=1)
    sample_count: int = Field(ge=0)
    mean_evidence_score: float | None = Field(default=None, ge=0, le=1)
    observed_support_fraction: float | None = Field(default=None, ge=0, le=1)


class CalibrationSliceV1(StrictModel):
    slice_id: str = Field(min_length=1)
    sample_count: int = Field(ge=0)
    brier_score: float | None = Field(default=None, ge=0, le=1)
    expected_calibration_error: float | None = Field(default=None, ge=0, le=1)
    reliability_bins: tuple[ReliabilityBinV1, ...]


class EvidenceEvaluationV1(StrictModel):
    schema_version: Literal["synthaudit.evidence-evaluation/1"] = "synthaudit.evidence-evaluation/1"
    evaluation_id: str = Field(min_length=1)
    stage: EvidenceStage
    model_id: str = Field(min_length=1)
    split: EvidenceExampleSplit
    scope: Literal["software_verification_fixture", "research_benchmark"]
    sample_count: int = Field(ge=0)
    auroc: float | None = Field(default=None, ge=0, le=1)
    average_precision: float | None = Field(default=None, ge=0, le=1)
    brier_score: float | None = Field(default=None, ge=0, le=1)
    expected_calibration_error: float | None = Field(default=None, ge=0, le=1)
    selective_risk: float | None = Field(default=None, ge=0, le=1)
    coverage: float = Field(ge=0, le=1)
    calibration_slices: tuple[CalibrationSliceV1, ...]
    limitations: tuple[str, ...] = Field(min_length=1)
    notice: Literal[
        "Evidence-model evaluation targets support annotations, not experimental feasibility."
    ] = "Evidence-model evaluation targets support annotations, not experimental feasibility."

    @model_validator(mode="after")
    def validate_evaluation(self) -> EvidenceEvaluationV1:
        if not self.calibration_slices or self.calibration_slices[0].slice_id != "all":
            raise ValueError("evaluation requires an overall reliability slice first")
        if self.calibration_slices[0].sample_count != self.sample_count:
            raise ValueError("overall reliability slice must cover every evaluation example")
        return self


class AblationResultV1(StrictModel):
    schema_version: Literal["synthaudit.evidence-ablation/1"] = "synthaudit.evidence-ablation/1"
    ablation_id: str = Field(min_length=1)
    retained_feature_groups: tuple[FeatureGroup, ...] = Field(min_length=1)
    evaluation: EvidenceEvaluationV1
    selection_prohibited: Literal[True] = True
    interpretation: Literal[
        "Held-out comparison only; test results are not used for calibration or threshold selection."
    ] = (
        "Held-out comparison only; test results are not used for calibration or threshold "
        "selection."
    )
