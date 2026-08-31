"""Versioned records for controlled, stage-aware counterfactual benchmarks."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field, JsonValue, model_validator

from synthaudit.schema.common import ProvenanceRecord, StrictModel
from synthaudit.schema.evidence import EvidenceAvailability
from synthaudit.schema.reaction_ir import ReactionIRV1
from synthaudit.schema.route_ir import RouteIRV1


class BenchmarkLabel(StrEnum):
    RECORDED_REACTION = "recorded_reaction"
    GENERATED_COUNTERFACTUAL = "generated_counterfactual"


class CounterfactualCategory(StrEnum):
    REPRESENTATION = "representation"
    REACTION_CENTRE = "reaction_centre"
    COMPLETION = "completion"
    STEREO = "stereo"
    ROUTE = "route"


class DifficultyLevel(StrEnum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class GenerationMethod(StrEnum):
    DUPLICATE_ATOM_MAPS = "duplicate_atom_maps"
    DANGLING_ATOM_MAPS = "dangling_atom_maps"
    MALFORMED_EDIT = "malformed_edit"
    MISSING_ATTACHMENT_REFERENCE = "missing_attachment_reference"
    IMPOSSIBLE_OPERATION_ORDERING = "impossible_operation_ordering"
    INVALID_LEAVING_GROUP_SYNTAX = "invalid_leaving_group_syntax"

    WRONG_BOND_BREAK = "wrong_bond_break"
    WRONG_BOND_ORDER_CHANGE = "wrong_bond_order_change"
    ALTERNATIVE_SITE_SWAP = "alternative_site_swap"
    WRONG_RING_CLOSURE_ATOM = "wrong_ring_closure_atom"
    CLASS_PRESERVING_CENTRE_DECOY = "class_preserving_reaction_centre_decoy"
    UNEXPLAINED_GRAPH_CHANGE = "unexplained_graph_change"

    WRONG_LEAVING_GROUP = "wrong_leaving_group"
    WRONG_ATTACHMENT_ATOM = "wrong_attachment_atom"
    MISSING_LEAVING_GROUP = "missing_leaving_group"
    DUPLICATE_LEAVING_GROUP = "duplicate_leaving_group"
    PRECURSOR_ANALOG_MISSING_HANDLE = "precursor_analog_lacking_required_handle"
    CHARGE_ONLY_COMPLETION_ERROR = "charge_only_completion_error"
    MULTI_ATTACHMENT_TOPOLOGY_ERROR = "multi_attachment_topology_error"

    UNINTENDED_INVERSION = "unintended_inversion"
    OMITTED_STEREOCHEMISTRY = "omitted_stereochemistry"
    INCORRECT_E_Z = "incorrect_e_z"
    INVALID_CHIRAL_CENTRE_OPERATION = "invalid_chiral_centre_operation"
    CYCLIC_STEREOCHEMISTRY_CORRUPTION = "cyclic_stereochemistry_corruption"

    DEPENDENCY_VIOLATING_STEP_SWAP = "dependency_violating_step_swap"
    DEPROTECTION_TOO_EARLY = "deprotection_too_early"
    PROTECTION_TOO_LATE = "protection_too_late"
    FRAGILE_INTERMEDIATE_INCOMPATIBLE_CONDITIONS = (
        "fragile_intermediate_before_incompatible_conditions"
    )
    PRECURSOR_NOT_PRODUCED = "precursor_not_produced_by_prior_step"


METHOD_CATEGORY: dict[GenerationMethod, CounterfactualCategory] = {
    **{
        method: CounterfactualCategory.REPRESENTATION
        for method in (
            GenerationMethod.DUPLICATE_ATOM_MAPS,
            GenerationMethod.DANGLING_ATOM_MAPS,
            GenerationMethod.MALFORMED_EDIT,
            GenerationMethod.MISSING_ATTACHMENT_REFERENCE,
            GenerationMethod.IMPOSSIBLE_OPERATION_ORDERING,
            GenerationMethod.INVALID_LEAVING_GROUP_SYNTAX,
        )
    },
    **{
        method: CounterfactualCategory.REACTION_CENTRE
        for method in (
            GenerationMethod.WRONG_BOND_BREAK,
            GenerationMethod.WRONG_BOND_ORDER_CHANGE,
            GenerationMethod.ALTERNATIVE_SITE_SWAP,
            GenerationMethod.WRONG_RING_CLOSURE_ATOM,
            GenerationMethod.CLASS_PRESERVING_CENTRE_DECOY,
            GenerationMethod.UNEXPLAINED_GRAPH_CHANGE,
        )
    },
    **{
        method: CounterfactualCategory.COMPLETION
        for method in (
            GenerationMethod.WRONG_LEAVING_GROUP,
            GenerationMethod.WRONG_ATTACHMENT_ATOM,
            GenerationMethod.MISSING_LEAVING_GROUP,
            GenerationMethod.DUPLICATE_LEAVING_GROUP,
            GenerationMethod.PRECURSOR_ANALOG_MISSING_HANDLE,
            GenerationMethod.CHARGE_ONLY_COMPLETION_ERROR,
            GenerationMethod.MULTI_ATTACHMENT_TOPOLOGY_ERROR,
        )
    },
    **{
        method: CounterfactualCategory.STEREO
        for method in (
            GenerationMethod.UNINTENDED_INVERSION,
            GenerationMethod.OMITTED_STEREOCHEMISTRY,
            GenerationMethod.INCORRECT_E_Z,
            GenerationMethod.INVALID_CHIRAL_CENTRE_OPERATION,
            GenerationMethod.CYCLIC_STEREOCHEMISTRY_CORRUPTION,
        )
    },
    **{
        method: CounterfactualCategory.ROUTE
        for method in (
            GenerationMethod.DEPENDENCY_VIOLATING_STEP_SWAP,
            GenerationMethod.DEPROTECTION_TOO_EARLY,
            GenerationMethod.PROTECTION_TOO_LATE,
            GenerationMethod.FRAGILE_INTERMEDIATE_INCOMPATIBLE_CONDITIONS,
            GenerationMethod.PRECURSOR_NOT_PRODUCED,
        )
    },
}


class FieldChangeV1(StrictModel):
    json_pointer: str = Field(pattern=r"^/(?:[^/~]|~[01])+(?:/(?:[^/~]|~[01])*)*$")
    operation: Literal["add", "remove", "replace", "reorder"]
    before: JsonValue
    after: JsonValue
    reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_change(self) -> FieldChangeV1:
        if self.operation in {"replace", "reorder"} and self.before == self.after:
            raise ValueError("a field change must alter its value")
        return self


class StepStructuralValidityV1(StrictModel):
    step_id: str = Field(min_length=1)
    execution_success: bool
    structurally_valid: bool
    error_type: str | None = None
    error_message: str | None = None


class StructuralValidityResultV1(StrictModel):
    schema_version: Literal["synthaudit.structural-validity/1"] = "synthaudit.structural-validity/1"
    evaluator: str = Field(min_length=1)
    evaluation_scope: Literal["reaction", "route", "raw_payload"]
    availability: EvidenceAvailability
    execution_success: bool | None = None
    structurally_valid: bool | None = None
    step_results: tuple[StepStructuralValidityV1, ...] = ()
    errors: tuple[str, ...] = ()
    provenance: tuple[ProvenanceRecord, ...] = ()

    @model_validator(mode="after")
    def validate_availability(self) -> StructuralValidityResultV1:
        if self.availability == EvidenceAvailability.AVAILABLE:
            if self.execution_success is None or self.structurally_valid is None:
                raise ValueError("available structural validation requires boolean results")
        elif self.execution_success is not None or self.structurally_valid is not None:
            raise ValueError("unavailable structural validation cannot contain boolean results")
        return self


class CounterfactualRecordV1(StrictModel):
    schema_version: Literal["synthaudit.counterfactual-record/1"] = (
        "synthaudit.counterfactual-record/1"
    )
    record_id: str = Field(min_length=1)
    label: BenchmarkLabel
    parent_reaction_id: str | None = None
    parent_route_id: str | None = None
    generation_method: GenerationMethod | None = None
    category: CounterfactualCategory | None = None
    seed: int | None = Field(default=None, ge=0)
    changed_fields: tuple[FieldChangeV1, ...] = ()
    structural_validity: StructuralValidityResultV1
    difficulty: DifficultyLevel | None = None
    reaction: ReactionIRV1 | None = None
    route: RouteIRV1 | None = None
    raw_candidate_payload: dict[str, JsonValue] | None = None
    source_dataset: str = Field(min_length=1)
    source_version: str = Field(min_length=1)
    data_license_status: str = Field(min_length=1)
    reaction_class: str | None = None
    product_scaffold_group: str = Field(min_length=1)
    tags: tuple[str, ...] = ()
    provenance: tuple[ProvenanceRecord, ...] = ()
    notice: Literal[
        "SynthAudit estimates representation validity, corpus novelty and evidence-based plausibility. It does not establish experimental feasibility, yield, selectivity, safety or scalability."
    ] = (
        "SynthAudit estimates representation validity, corpus novelty and evidence-based "
        "plausibility. It does not establish experimental feasibility, yield, selectivity, "
        "safety or scalability."
    )

    @model_validator(mode="after")
    def validate_label_contract(self) -> CounterfactualRecordV1:
        payload_count = sum(
            value is not None for value in (self.reaction, self.route, self.raw_candidate_payload)
        )
        if payload_count != 1:
            raise ValueError("a benchmark record requires exactly one candidate payload")
        if self.label == BenchmarkLabel.GENERATED_COUNTERFACTUAL:
            required = (
                self.parent_reaction_id,
                self.generation_method,
                self.category,
                self.seed,
                self.difficulty,
            )
            if any(value is None for value in required) or not self.changed_fields:
                raise ValueError(
                    "generated counterfactuals require parent, method, category, seed, "
                    "changed fields, and difficulty"
                )
            assert self.generation_method is not None
            if METHOD_CATEGORY[self.generation_method] != self.category:
                raise ValueError("counterfactual category does not match generation method")
        elif (
            any(
                value is not None
                for value in (
                    self.parent_reaction_id,
                    self.parent_route_id,
                    self.generation_method,
                    self.category,
                    self.seed,
                    self.difficulty,
                )
            )
            or self.changed_fields
        ):
            raise ValueError("recorded reactions cannot contain generation metadata")
        return self

    @property
    def grouping_parent_reaction_id(self) -> str:
        if self.parent_reaction_id is not None:
            return self.parent_reaction_id
        if self.reaction is not None:
            return self.reaction.reaction_id
        if self.route is not None and self.route.steps:
            return self.route.steps[-1].reaction.reaction_id
        return self.record_id


class CounterfactualDatasetManifestV1(StrictModel):
    schema_version: Literal["synthaudit.counterfactual-dataset-manifest/1"] = (
        "synthaudit.counterfactual-dataset-manifest/1"
    )
    dataset_id: str = Field(min_length=1)
    dataset_version: str = Field(min_length=1)
    purpose: Literal["software_verification_fixture", "research_benchmark"]
    record_count: int = Field(ge=0)
    records_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    label_counts: dict[BenchmarkLabel, int]
    category_counts: dict[CounterfactualCategory, int]
    difficulty_counts: dict[DifficultyLevel, int]
    generator_version: str = Field(min_length=1)
    global_seed: int = Field(ge=0)
    source_licenses: tuple[str, ...]
    metrics_status: Literal["not_run"] = "not_run"
    notice: Literal[
        "SynthAudit estimates representation validity, corpus novelty and evidence-based plausibility. It does not establish experimental feasibility, yield, selectivity, safety or scalability."
    ] = (
        "SynthAudit estimates representation validity, corpus novelty and evidence-based "
        "plausibility. It does not establish experimental feasibility, yield, selectivity, "
        "safety or scalability."
    )
    provenance: tuple[ProvenanceRecord, ...] = ()


class CounterfactualDatasetV1(StrictModel):
    schema_version: Literal["synthaudit.counterfactual-dataset/1"] = (
        "synthaudit.counterfactual-dataset/1"
    )
    manifest: CounterfactualDatasetManifestV1
    records: tuple[CounterfactualRecordV1, ...]

    @model_validator(mode="after")
    def validate_manifest_counts(self) -> CounterfactualDatasetV1:
        if self.manifest.record_count != len(self.records):
            raise ValueError("counterfactual manifest record count does not match records")
        record_ids = [record.record_id for record in self.records]
        if len(record_ids) != len(set(record_ids)):
            raise ValueError("counterfactual record IDs must be unique")
        expected_labels = {
            label: sum(record.label == label for record in self.records) for label in BenchmarkLabel
        }
        expected_categories = {
            category: sum(record.category == category for record in self.records)
            for category in CounterfactualCategory
        }
        expected_difficulties = {
            difficulty: sum(record.difficulty == difficulty for record in self.records)
            for difficulty in DifficultyLevel
        }
        if self.manifest.label_counts != expected_labels:
            raise ValueError("counterfactual manifest label counts do not match records")
        if self.manifest.category_counts != expected_categories:
            raise ValueError("counterfactual manifest category counts do not match records")
        if self.manifest.difficulty_counts != expected_difficulties:
            raise ValueError("counterfactual manifest difficulty counts do not match records")
        return self


class DatasetPartition(StrEnum):
    TRAIN = "train"
    CALIBRATION = "calibration"
    TEST = "test"


class EvaluationSlice(StrEnum):
    HIGH_NOVELTY = "high_novelty_test"
    RING_FORMING = "ring_forming_test"
    STEREO_SENSITIVE = "stereo_sensitive_test"


class SplitAssignmentV1(StrictModel):
    record_id: str = Field(min_length=1)
    parent_reaction_group: str = Field(min_length=1)
    product_scaffold_group: str = Field(min_length=1)
    reaction_class_group: str = Field(min_length=1)
    in_distribution: DatasetPartition
    scaffold_holdout: DatasetPartition
    reaction_class_holdout: DatasetPartition
    evaluation_slices: tuple[EvaluationSlice, ...] = ()
    product_novelty: float | None = Field(default=None, ge=0, le=1)


class NoveltySliceDefinitionV1(StrictModel):
    metric: Literal["one_minus_maximum_training_product_morgan_tanimoto"] = (
        "one_minus_maximum_training_product_morgan_tanimoto"
    )
    threshold: float = Field(ge=0, le=1)
    training_reference_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    fingerprint_method: str = Field(min_length=1)


class BenchmarkSplitManifestV1(StrictModel):
    schema_version: Literal["synthaudit.benchmark-splits/1"] = "synthaudit.benchmark-splits/1"
    dataset_id: str = Field(min_length=1)
    dataset_version: str = Field(min_length=1)
    records_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    split_seed: int = Field(ge=0)
    grouping_strategies: tuple[
        Literal["parent_reaction", "product_scaffold", "reaction_class"], ...
    ] = ("parent_reaction", "product_scaffold", "reaction_class")
    novelty_slice: NoveltySliceDefinitionV1 | None = None
    assignments: tuple[SplitAssignmentV1, ...]
    notice: Literal[
        "SynthAudit estimates representation validity, corpus novelty and evidence-based plausibility. It does not establish experimental feasibility, yield, selectivity, safety or scalability."
    ] = (
        "SynthAudit estimates representation validity, corpus novelty and evidence-based "
        "plausibility. It does not establish experimental feasibility, yield, selectivity, "
        "safety or scalability."
    )

    @model_validator(mode="after")
    def validate_no_group_leakage(self) -> BenchmarkSplitManifestV1:
        if len({item.record_id for item in self.assignments}) != len(self.assignments):
            raise ValueError("split assignments require unique record IDs")
        checks = (
            ("parent_reaction_group", "in_distribution"),
            ("product_scaffold_group", "scaffold_holdout"),
            ("reaction_class_group", "reaction_class_holdout"),
        )
        for group_field, split_field in checks:
            observed: dict[str, DatasetPartition] = {}
            for item in self.assignments:
                group = str(getattr(item, group_field))
                partition = getattr(item, split_field)
                if group in observed and observed[group] != partition:
                    raise ValueError(f"group leakage detected for {group_field}: {group}")
                observed[group] = partition
        high_novelty = {
            item.record_id
            for item in self.assignments
            if EvaluationSlice.HIGH_NOVELTY in item.evaluation_slices
        }
        if high_novelty and self.novelty_slice is None:
            raise ValueError("high-novelty assignments require a novelty-slice definition")
        if self.novelty_slice is not None:
            invalid = [
                item.record_id
                for item in self.assignments
                if EvaluationSlice.HIGH_NOVELTY in item.evaluation_slices
                and (
                    item.product_novelty is None
                    or item.product_novelty < self.novelty_slice.threshold
                )
            ]
            if invalid:
                raise ValueError(f"high-novelty slice contains below-threshold records: {invalid}")
        return self


class CounterfactualBenchmarkValidationV1(StrictModel):
    schema_version: Literal["synthaudit.counterfactual-benchmark-validation/1"] = (
        "synthaudit.counterfactual-benchmark-validation/1"
    )
    valid: Literal[True] = True
    dataset_id: str = Field(min_length=1)
    dataset_version: str = Field(min_length=1)
    record_count: int = Field(ge=0)
    records_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    label_counts: dict[BenchmarkLabel, int]
    category_counts: dict[CounterfactualCategory, int]
    method_count: int = Field(ge=0)
    split_partition_counts: dict[str, dict[DatasetPartition, int]]
    evaluation_slice_counts: dict[EvaluationSlice, int]
    human_review_row_count: int = Field(ge=0)
    leakage_checks: Literal["passed"] = "passed"
    metrics_status: Literal["not_run"] = "not_run"
    notice: Literal[
        "SynthAudit estimates representation validity, corpus novelty and evidence-based plausibility. It does not establish experimental feasibility, yield, selectivity, safety or scalability."
    ] = (
        "SynthAudit estimates representation validity, corpus novelty and evidence-based "
        "plausibility. It does not establish experimental feasibility, yield, selectivity, "
        "safety or scalability."
    )
