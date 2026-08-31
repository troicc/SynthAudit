"""Provider-neutral contracts for prompt-robustness benchmark cases and results."""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Literal

from pydantic import Field, JsonValue, model_validator

from synthaudit.models.evidence import CalibrationSliceV1
from synthaudit.schema.common import ProvenanceRecord, ReactionConditions, StrictModel
from synthaudit.schema.evidence import EvidenceAvailability
from synthaudit.schema.reaction_ir import ReactionIRV1


class PromptVariantKind(StrEnum):
    EXACT = "exact"
    PARTIAL = "partial"
    AMBIGUOUS = "ambiguous"
    INCORRECT_STRUCTURALLY_PLAUSIBLE = "incorrect_structurally_plausible"
    CONTRADICTORY = "contradictory"


class PromptInstructionRelation(StrEnum):
    CORRECT = "correct"
    INCOMPLETE = "incomplete"
    AMBIGUOUS = "ambiguous"
    INCORRECT = "incorrect"
    CONTRADICTORY = "contradictory"


class PromptMutationKind(StrEnum):
    OMIT = "omit"
    GENERALIZE = "generalize"
    REPLACE = "replace"
    APPEND_CONTRADICTION = "append_contradiction"


class PromptInstructionV1(StrictModel):
    instruction_id: str = Field(min_length=1)
    edit_type: str = Field(min_length=1)
    atom_maps: tuple[int, ...] = ()
    operation_payload: dict[str, JsonValue]
    relation_to_reference: PromptInstructionRelation
    rendered_text: str = Field(min_length=1)


class PromptMutationV1(StrictModel):
    mutation_kind: PromptMutationKind
    reference_instruction_ids: tuple[str, ...] = Field(min_length=1)
    description: str = Field(min_length=1)


class PromptVariantV1(StrictModel):
    schema_version: Literal["synthaudit.prompt-variant/1"] = "synthaudit.prompt-variant/1"
    variant_id: str = Field(min_length=1)
    reaction_id: str = Field(min_length=1)
    kind: PromptVariantKind
    prompt_version: str = Field(min_length=1)
    prompt_text: str = Field(min_length=1)
    instructions: tuple[PromptInstructionV1, ...] = Field(min_length=1)
    mutations: tuple[PromptMutationV1, ...] = ()
    omitted_reference_instruction_ids: tuple[str, ...] = ()
    source_reaction_semantic_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    generation_seed: int = Field(ge=0)
    provider_neutral: Literal[True] = True
    provenance: tuple[ProvenanceRecord, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_variant_semantics(self) -> PromptVariantV1:
        instruction_ids = [item.instruction_id for item in self.instructions]
        if len(instruction_ids) != len(set(instruction_ids)):
            raise ValueError("prompt instruction IDs must be unique within a variant")
        relations = {item.relation_to_reference for item in self.instructions}
        if self.kind == PromptVariantKind.EXACT:
            if relations != {PromptInstructionRelation.CORRECT}:
                raise ValueError("exact prompt instructions must all be correct")
            if self.mutations or self.omitted_reference_instruction_ids:
                raise ValueError("exact prompts cannot declare mutations or omissions")
        elif self.kind == PromptVariantKind.PARTIAL:
            if not self.omitted_reference_instruction_ids or not self.mutations:
                raise ValueError("partial prompts require explicit omissions")
        elif self.kind == PromptVariantKind.AMBIGUOUS:
            if PromptInstructionRelation.AMBIGUOUS not in relations:
                raise ValueError("ambiguous prompts require an ambiguous instruction")
        elif self.kind == PromptVariantKind.INCORRECT_STRUCTURALLY_PLAUSIBLE:
            if PromptInstructionRelation.INCORRECT not in relations:
                raise ValueError("incorrect prompts require an incorrect instruction")
        elif PromptInstructionRelation.CONTRADICTORY not in relations:
            raise ValueError("contradictory prompts require a contradictory instruction")
        return self


class PromptBenchmarkCaseV1(StrictModel):
    schema_version: Literal["synthaudit.prompt-benchmark-case/1"] = (
        "synthaudit.prompt-benchmark-case/1"
    )
    case_id: str = Field(min_length=1)
    parent_group_id: str = Field(min_length=1)
    reference_reaction: ReactionIRV1
    variants: tuple[PromptVariantV1, ...] = Field(min_length=5, max_length=5)
    eligibility_rule: Literal["at_least_one_centre_and_two_total_declared_edit_operations"] = (
        "at_least_one_centre_and_two_total_declared_edit_operations"
    )
    reference_semantics: Literal["reference_representation_not_experimental_ground_truth"] = (
        "reference_representation_not_experimental_ground_truth"
    )
    provenance: tuple[ProvenanceRecord, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_case(self) -> PromptBenchmarkCaseV1:
        kinds = {item.kind for item in self.variants}
        if kinds != set(PromptVariantKind):
            raise ValueError("prompt benchmark case requires exactly one of every variant kind")
        if len({item.variant_id for item in self.variants}) != len(self.variants):
            raise ValueError("prompt benchmark variant IDs must be unique")
        if any(item.reaction_id != self.reference_reaction.reaction_id for item in self.variants):
            raise ValueError("prompt variants must reference the case reaction")
        expected_hashes = {item.source_reaction_semantic_hash for item in self.variants}
        if len(expected_hashes) != 1:
            raise ValueError("all prompt variants must use the same reference semantic hash")
        return self


def canonical_prompt_cases_text(cases: tuple[PromptBenchmarkCaseV1, ...]) -> str:
    ordered = sorted(cases, key=lambda item: item.case_id)
    return "".join(
        json.dumps(item.model_dump(mode="json"), sort_keys=True, separators=(",", ":")) + "\n"
        for item in ordered
    )


def prompt_cases_sha256(cases: tuple[PromptBenchmarkCaseV1, ...]) -> str:
    return hashlib.sha256(canonical_prompt_cases_text(cases).encode()).hexdigest()


class PromptBenchmarkDatasetManifestV1(StrictModel):
    schema_version: Literal["synthaudit.prompt-benchmark-dataset-manifest/1"] = (
        "synthaudit.prompt-benchmark-dataset-manifest/1"
    )
    dataset_id: str = Field(min_length=1)
    dataset_version: str = Field(min_length=1)
    purpose: Literal["software_verification_fixture", "research_benchmark"]
    source_dataset_id: str = Field(min_length=1)
    source_dataset_version: str = Field(min_length=1)
    source_records_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_license_status: str = Field(min_length=1)
    source_label_semantics: Literal[
        "recorded_reaction_is_a_reference_representation_not_guaranteed_experimental_success"
    ] = "recorded_reaction_is_a_reference_representation_not_guaranteed_experimental_success"
    eligibility_rule: Literal["at_least_one_centre_and_two_total_declared_edit_operations"] = (
        "at_least_one_centre_and_two_total_declared_edit_operations"
    )
    case_count: int = Field(ge=1)
    variant_count: int = Field(ge=5)
    variant_kind_counts: dict[PromptVariantKind, int]
    cases_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    metrics_status: Literal["not_run"] = "not_run"
    provenance: tuple[ProvenanceRecord, ...] = Field(min_length=1)
    notice: Literal[
        "SynthAudit estimates representation validity, corpus novelty and evidence-based plausibility. It does not establish experimental feasibility, yield, selectivity, safety or scalability."
    ] = (
        "SynthAudit estimates representation validity, corpus novelty and evidence-based "
        "plausibility. It does not establish experimental feasibility, yield, selectivity, "
        "safety or scalability."
    )

    @model_validator(mode="after")
    def validate_manifest_counts(self) -> PromptBenchmarkDatasetManifestV1:
        if set(self.variant_kind_counts) != set(PromptVariantKind):
            raise ValueError("prompt dataset manifest must count every variant kind")
        if any(value != self.case_count for value in self.variant_kind_counts.values()):
            raise ValueError("every prompt case must contribute one of each variant kind")
        if self.variant_count != self.case_count * len(PromptVariantKind):
            raise ValueError("prompt variant count must equal five variants per case")
        return self


class PromptBenchmarkDatasetV1(StrictModel):
    schema_version: Literal["synthaudit.prompt-benchmark-dataset/1"] = (
        "synthaudit.prompt-benchmark-dataset/1"
    )
    manifest: PromptBenchmarkDatasetManifestV1
    cases: tuple[PromptBenchmarkCaseV1, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_dataset(self) -> PromptBenchmarkDatasetV1:
        if len({item.case_id for item in self.cases}) != len(self.cases):
            raise ValueError("prompt benchmark case IDs must be unique")
        if len(self.cases) != self.manifest.case_count:
            raise ValueError("prompt case count does not match the manifest")
        if prompt_cases_sha256(self.cases) != self.manifest.cases_sha256:
            raise ValueError("prompt cases do not match the manifest SHA-256")
        counts = {
            kind: sum(variant.kind == kind for case in self.cases for variant in case.variants)
            for kind in PromptVariantKind
        }
        if counts != self.manifest.variant_kind_counts:
            raise ValueError("prompt variant-kind counts do not match the manifest")
        return self


class PromptBenchmarkValidationV1(StrictModel):
    schema_version: Literal["synthaudit.prompt-benchmark-validation/1"] = (
        "synthaudit.prompt-benchmark-validation/1"
    )
    valid: Literal[True] = True
    dataset_id: str = Field(min_length=1)
    dataset_version: str = Field(min_length=1)
    case_count: int = Field(ge=1)
    variant_count: int = Field(ge=5)
    variant_kind_counts: dict[PromptVariantKind, int]
    cases_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    parent_group_atomicity: Literal["passed"] = "passed"
    metrics_status: Literal["not_run"] = "not_run"
    notice: Literal[
        "SynthAudit estimates representation validity, corpus novelty and evidence-based plausibility. It does not establish experimental feasibility, yield, selectivity, safety or scalability."
    ] = (
        "SynthAudit estimates representation validity, corpus novelty and evidence-based "
        "plausibility. It does not establish experimental feasibility, yield, selectivity, "
        "safety or scalability."
    )


class PromptModelRequestV1(StrictModel):
    schema_version: Literal["synthaudit.prompt-model-request/1"] = (
        "synthaudit.prompt-model-request/1"
    )
    request_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    variant: PromptVariantV1
    mapped_product_smiles: str = Field(min_length=1)
    conditions: ReactionConditions | None = None
    requested_candidate_count: int = Field(default=1, ge=1, le=100)


class PromptModelOutputV1(StrictModel):
    schema_version: Literal["synthaudit.prompt-model-output/1"] = "synthaudit.prompt-model-output/1"
    request_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    variant_id: str = Field(min_length=1)
    provider_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    availability: EvidenceAvailability
    candidate_reaction: ReactionIRV1 | None = None
    abstained: bool = False
    raw_response: str | None = None
    raw_model_confidence: float | None = Field(default=None, ge=0, le=1)
    raw_confidence_is_calibrated_probability: Literal[False] = False
    calibrated_evidence_confidence: float | None = Field(default=None, ge=0, le=1)
    calibration_method: str | None = None
    missing_reasons: tuple[str, ...] = ()
    provenance: tuple[ProvenanceRecord, ...] = ()
    interpretation: Literal[
        "Candidate output for representation-level prompt evaluation; not experimental evidence."
    ] = "Candidate output for representation-level prompt evaluation; not experimental evidence."

    @model_validator(mode="after")
    def validate_output(self) -> PromptModelOutputV1:
        if self.availability == EvidenceAvailability.AVAILABLE:
            if not self.raw_response or not self.provenance:
                raise ValueError(
                    "available prompt-model output requires raw response and provenance"
                )
            if self.abstained == (self.candidate_reaction is not None):
                raise ValueError("available output must contain either a candidate or abstention")
            if (self.calibrated_evidence_confidence is None) != (self.calibration_method is None):
                raise ValueError(
                    "calibrated confidence and calibration method must appear together"
                )
        elif (
            any(
                value is not None
                for value in (
                    self.candidate_reaction,
                    self.raw_response,
                    self.raw_model_confidence,
                    self.calibrated_evidence_confidence,
                    self.calibration_method,
                )
            )
            or self.abstained
        ):
            raise ValueError("unavailable prompt-model output cannot contain model results")
        elif not self.missing_reasons:
            raise ValueError("unavailable prompt-model output requires explicit reasons")
        return self


class PromptVariantEvaluationV1(StrictModel):
    schema_version: Literal["synthaudit.prompt-variant-evaluation/1"] = (
        "synthaudit.prompt-variant-evaluation/1"
    )
    case_id: str = Field(min_length=1)
    variant_id: str = Field(min_length=1)
    variant_kind: PromptVariantKind
    provider_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    availability: EvidenceAvailability
    reaction_centre_accuracy: float | None = Field(default=None, ge=0, le=1)
    precursor_exact_match: bool | None = None
    completion_accuracy: float | None = Field(default=None, ge=0, le=1)
    stereo_accuracy: float | None = Field(default=None, ge=0, le=1)
    structural_validity: bool | None = None
    model_confidence: float | None = Field(default=None, ge=0, le=1)
    confidence_semantics: Literal[
        "calibrated_evidence_support_not_experimental_probability",
        "raw_uncalibrated_provider_score",
        "unavailable",
    ]
    prompt_obedience: bool | None = None
    recovery_from_incorrect_prompt: bool | None = None
    abstained: bool
    confidence_drop_under_contradiction: float | None = Field(default=None, ge=-1, le=1)
    reference_semantics: Literal[
        "agreement_with_reference_representation_not_experimental_truth"
    ] = "agreement_with_reference_representation_not_experimental_truth"
    missing_reasons: tuple[str, ...] = ()
    provenance: tuple[ProvenanceRecord, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_evaluation(self) -> PromptVariantEvaluationV1:
        if self.confidence_semantics == "unavailable" and self.model_confidence is not None:
            raise ValueError("unavailable confidence semantics cannot carry a score")
        if self.confidence_semantics != "unavailable" and self.model_confidence is None:
            raise ValueError("available confidence semantics requires a score")
        if (
            self.variant_kind != PromptVariantKind.INCORRECT_STRUCTURALLY_PLAUSIBLE
            and self.recovery_from_incorrect_prompt is not None
        ):
            raise ValueError("incorrect-prompt recovery belongs only to incorrect variants")
        if (
            self.variant_kind != PromptVariantKind.CONTRADICTORY
            and self.confidence_drop_under_contradiction is not None
        ):
            raise ValueError("contradiction confidence drop belongs only to contradictory variants")
        return self


class PromptProviderCaseEvaluationV1(StrictModel):
    schema_version: Literal["synthaudit.prompt-provider-case-evaluation/1"] = (
        "synthaudit.prompt-provider-case-evaluation/1"
    )
    case_id: str = Field(min_length=1)
    provider_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    evaluations: tuple[PromptVariantEvaluationV1, ...] = Field(min_length=5, max_length=5)

    @model_validator(mode="after")
    def validate_provider_case(self) -> PromptProviderCaseEvaluationV1:
        if {item.variant_kind for item in self.evaluations} != set(PromptVariantKind):
            raise ValueError("provider case evaluation requires every prompt variant")
        if any(
            item.case_id != self.case_id
            or item.provider_id != self.provider_id
            or item.model_id != self.model_id
            for item in self.evaluations
        ):
            raise ValueError("variant evaluations must match the provider case identity")
        return self


class PromptProviderCalibrationV1(StrictModel):
    provider_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    target: Literal["precursor_exact_match_against_reference_representation"] = (
        "precursor_exact_match_against_reference_representation"
    )
    confidence_semantics: Literal[
        "calibrated_evidence_support_not_experimental_probability",
        "raw_uncalibrated_provider_score",
    ]
    interpretation: Literal[
        "Reliability diagnostic against reference agreement; it does not calibrate raw scores retroactively."
    ] = (
        "Reliability diagnostic against reference agreement; it does not calibrate raw scores "
        "retroactively."
    )
    summary: CalibrationSliceV1


class PromptBenchmarkEvaluationV1(StrictModel):
    schema_version: Literal["synthaudit.prompt-benchmark-evaluation/1"] = (
        "synthaudit.prompt-benchmark-evaluation/1"
    )
    evaluation_id: str = Field(min_length=1)
    scope: Literal["software_verification_fixture", "research_benchmark"]
    case_count: int = Field(ge=1)
    provider_case_evaluations: tuple[PromptProviderCaseEvaluationV1, ...] = Field(min_length=1)
    provider_calibration: tuple[PromptProviderCalibrationV1, ...] = ()
    provider_count: int = Field(ge=1)
    metrics_status: Literal["computed_software_fixture", "computed_research_benchmark"]
    single_provider_as_ground_truth_permitted: Literal[False] = False
    comparison_policy: Literal[
        "providers_evaluated_independently_against_reference_representation"
    ] = "providers_evaluated_independently_against_reference_representation"
    limitations: tuple[str, ...] = Field(min_length=1)
    notice: Literal[
        "SynthAudit estimates representation validity, corpus novelty and evidence-based plausibility. It does not establish experimental feasibility, yield, selectivity, safety or scalability."
    ] = (
        "SynthAudit estimates representation validity, corpus novelty and evidence-based "
        "plausibility. It does not establish experimental feasibility, yield, selectivity, "
        "safety or scalability."
    )

    @model_validator(mode="after")
    def validate_benchmark_evaluation(self) -> PromptBenchmarkEvaluationV1:
        providers = {(item.provider_id, item.model_id) for item in self.provider_case_evaluations}
        if len(providers) != self.provider_count:
            raise ValueError("provider count must match distinct provider/model pairs")
        if len({item.case_id for item in self.provider_case_evaluations}) != self.case_count:
            raise ValueError("case count must match evaluated cases")
        expected_status = (
            "computed_software_fixture"
            if self.scope == "software_verification_fixture"
            else "computed_research_benchmark"
        )
        if self.metrics_status != expected_status:
            raise ValueError("metrics status must visibly match evaluation scope")
        calibration_keys = {(item.provider_id, item.model_id) for item in self.provider_calibration}
        if not calibration_keys.issubset(providers):
            raise ValueError("calibration summaries must match evaluated providers")
        return self
