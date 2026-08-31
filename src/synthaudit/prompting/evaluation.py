"""Representation-level prompt evaluation; no model is treated as experimental ground truth."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Sequence
from typing import Any, Literal, cast

from pydantic import JsonValue

from synthaudit import __version__
from synthaudit.audit.common import canonical_structure_set
from synthaudit.calibration.metrics import reliability_summary
from synthaudit.graph.executor import ReactionExecutor
from synthaudit.prompting.models import (
    PromptBenchmarkCaseV1,
    PromptBenchmarkEvaluationV1,
    PromptInstructionRelation,
    PromptModelOutputV1,
    PromptProviderCalibrationV1,
    PromptProviderCaseEvaluationV1,
    PromptVariantEvaluationV1,
    PromptVariantKind,
    PromptVariantV1,
)
from synthaudit.schema.common import ProvenanceRecord
from synthaudit.schema.evidence import EvidenceAvailability
from synthaudit.schema.reaction_ir import ReactionIRV1


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


def _operation_payload(operation: Any) -> dict[str, JsonValue]:
    return cast(
        dict[str, JsonValue],
        operation.model_dump(
            mode="json",
            exclude={"edit_id", "source_range", "metadata"},
        ),
    )


def _operation_key(payload: dict[str, JsonValue]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _stage_keys(reaction: ReactionIRV1) -> tuple[set[str], set[str], set[str]]:
    centre = {_operation_key(_operation_payload(item)) for item in reaction.core_edits}
    completion = {
        _operation_key(_operation_payload(item))
        for item in (*reaction.attachment_edits, *reaction.atom_state_edits)
    }
    stereo = {_operation_key(_operation_payload(item)) for item in reaction.stereo_edits}
    return centre, completion, stereo


def _precursor_exact_match(reference: ReactionIRV1, candidate: ReactionIRV1) -> tuple[bool, bool]:
    executor = ReactionExecutor()
    reference_result = executor.execute(reference)
    candidate_result = executor.execute(candidate)
    if not reference_result.success:
        raise ValueError("reference reaction must execute for prompt evaluation")
    if not candidate_result.success:
        return False, False
    return (
        canonical_structure_set(reference_result.mapped_structures)
        == canonical_structure_set(candidate_result.mapped_structures),
        candidate_result.structurally_valid,
    )


def _prompt_obedience(variant: PromptVariantV1, candidate: ReactionIRV1) -> bool | None:
    if any(
        item.relation_to_reference == PromptInstructionRelation.AMBIGUOUS
        for item in variant.instructions
    ):
        return None
    candidate_keys = set().union(*_stage_keys(candidate))
    required = {
        _operation_key(item.operation_payload)
        for item in variant.instructions
        if item.relation_to_reference
        in {
            PromptInstructionRelation.CORRECT,
            PromptInstructionRelation.INCORRECT,
            PromptInstructionRelation.CONTRADICTORY,
        }
    }
    return required.issubset(candidate_keys)


def _confidence(
    output: PromptModelOutputV1,
) -> tuple[
    float | None,
    Literal[
        "calibrated_evidence_support_not_experimental_probability",
        "raw_uncalibrated_provider_score",
        "unavailable",
    ],
]:
    if output.calibrated_evidence_confidence is not None:
        return (
            output.calibrated_evidence_confidence,
            "calibrated_evidence_support_not_experimental_probability",
        )
    if output.raw_model_confidence is not None:
        return output.raw_model_confidence, "raw_uncalibrated_provider_score"
    return None, "unavailable"


def _evaluate_variant(
    case: PromptBenchmarkCaseV1,
    variant: PromptVariantV1,
    output: PromptModelOutputV1,
) -> PromptVariantEvaluationV1:
    confidence, confidence_semantics = _confidence(output)
    centre_accuracy: float | None = None
    precursor_match: bool | None = None
    completion_accuracy: float | None = None
    stereo_accuracy: float | None = None
    structural_validity: bool | None = None
    obedience: bool | None = None
    recovery: bool | None = None
    missing = list(output.missing_reasons)
    if output.availability == EvidenceAvailability.AVAILABLE and output.candidate_reaction:
        reference_stages = _stage_keys(case.reference_reaction)
        candidate_stages = _stage_keys(output.candidate_reaction)
        centre_accuracy = float(reference_stages[0] == candidate_stages[0])
        completion_accuracy = float(reference_stages[1] == candidate_stages[1])
        stereo_accuracy = float(reference_stages[2] == candidate_stages[2])
        precursor_match, structural_validity = _precursor_exact_match(
            case.reference_reaction, output.candidate_reaction
        )
        obedience = _prompt_obedience(variant, output.candidate_reaction)
        if variant.kind == PromptVariantKind.INCORRECT_STRUCTURALLY_PLAUSIBLE:
            recovery = bool(centre_accuracy == 1.0 and precursor_match)
    elif output.abstained:
        missing.append("provider abstained")
    else:
        missing.append("candidate reaction unavailable")
    return PromptVariantEvaluationV1(
        case_id=case.case_id,
        variant_id=variant.variant_id,
        variant_kind=variant.kind,
        provider_id=output.provider_id,
        model_id=output.model_id,
        availability=output.availability,
        reaction_centre_accuracy=centre_accuracy,
        precursor_exact_match=precursor_match,
        completion_accuracy=completion_accuracy,
        stereo_accuracy=stereo_accuracy,
        structural_validity=structural_validity,
        model_confidence=confidence,
        confidence_semantics=confidence_semantics,
        prompt_obedience=obedience,
        recovery_from_incorrect_prompt=recovery,
        abstained=output.abstained,
        missing_reasons=tuple(sorted(set(missing))),
        provenance=(*output.provenance, *_provenance("evaluate_prompt_variant")),
    )


def evaluate_prompt_provider_case(
    case: PromptBenchmarkCaseV1,
    outputs: Sequence[PromptModelOutputV1],
) -> PromptProviderCaseEvaluationV1:
    if len(outputs) != len(case.variants):
        raise ValueError("prompt provider evaluation requires one output per variant")
    output_by_variant = {item.variant_id: item for item in outputs}
    if len(output_by_variant) != len(outputs):
        raise ValueError("prompt-model variant output IDs must be unique")
    expected_ids = {item.variant_id for item in case.variants}
    if set(output_by_variant) != expected_ids:
        raise ValueError("prompt-model outputs do not match the benchmark variants")
    identities = {(item.provider_id, item.model_id, item.case_id) for item in outputs}
    if len(identities) != 1 or next(iter(identities))[2] != case.case_id:
        raise ValueError("prompt-model outputs must share provider/model/case identity")
    evaluations = [
        _evaluate_variant(case, variant, output_by_variant[variant.variant_id])
        for variant in case.variants
    ]
    exact = next(item for item in evaluations if item.variant_kind == PromptVariantKind.EXACT)
    contradiction_index = next(
        index
        for index, item in enumerate(evaluations)
        if item.variant_kind == PromptVariantKind.CONTRADICTORY
    )
    contradiction = evaluations[contradiction_index]
    if exact.model_confidence is not None and contradiction.model_confidence is not None:
        same_semantics = exact.confidence_semantics == contradiction.confidence_semantics
        if same_semantics:
            evaluations[contradiction_index] = contradiction.model_copy(
                update={
                    "confidence_drop_under_contradiction": (
                        exact.model_confidence - contradiction.model_confidence
                    )
                }
            )
    provider_id, model_id, _ = next(iter(identities))
    return PromptProviderCaseEvaluationV1(
        case_id=case.case_id,
        provider_id=provider_id,
        model_id=model_id,
        evaluations=tuple(evaluations),
    )


def build_prompt_benchmark_evaluation(
    provider_case_evaluations: Sequence[PromptProviderCaseEvaluationV1],
    *,
    evaluation_id: str,
    scope: Literal["software_verification_fixture", "research_benchmark"],
) -> PromptBenchmarkEvaluationV1:
    if not provider_case_evaluations:
        raise ValueError("prompt benchmark evaluation requires provider case results")
    by_provider: dict[tuple[str, str], list[PromptProviderCaseEvaluationV1]] = defaultdict(list)
    for result in provider_case_evaluations:
        by_provider[(result.provider_id, result.model_id)].append(result)
    calibration: list[PromptProviderCalibrationV1] = []
    for (provider_id, model_id), results in sorted(by_provider.items()):
        eligible = [
            item
            for result in results
            for item in result.evaluations
            if item.model_confidence is not None and item.precursor_exact_match is not None
        ]
        confidence_semantics_values: tuple[
            Literal[
                "calibrated_evidence_support_not_experimental_probability",
                "raw_uncalibrated_provider_score",
            ],
            ...,
        ] = (
            "calibrated_evidence_support_not_experimental_probability",
            "raw_uncalibrated_provider_score",
        )
        for semantics in confidence_semantics_values:
            semantic_items = [item for item in eligible if item.confidence_semantics == semantics]
            if not semantic_items:
                continue
            summary = reliability_summary(
                [int(bool(item.precursor_exact_match)) for item in semantic_items],
                [
                    float(item.model_confidence)
                    for item in semantic_items
                    if item.model_confidence is not None
                ],
                slice_id=f"all-prompt-variants:{semantics}",
            )
            calibration.append(
                PromptProviderCalibrationV1(
                    provider_id=provider_id,
                    model_id=model_id,
                    confidence_semantics=semantics,
                    summary=summary,
                )
            )
    providers = set(by_provider)
    limitations = [
        "Reference agreement is not experimental ground truth or feasibility.",
        "Prompt-model providers are evaluated independently; none is used as the truth label.",
        "Raw provider confidence remains explicitly uncalibrated.",
    ]
    if scope == "software_verification_fixture":
        limitations.append(
            "Authored software-fixture values verify metric plumbing and are not scientific results."
        )
    return PromptBenchmarkEvaluationV1(
        evaluation_id=evaluation_id,
        scope=scope,
        case_count=len({item.case_id for item in provider_case_evaluations}),
        provider_case_evaluations=tuple(provider_case_evaluations),
        provider_calibration=tuple(calibration),
        provider_count=len(providers),
        metrics_status=(
            "computed_software_fixture"
            if scope == "software_verification_fixture"
            else "computed_research_benchmark"
        ),
        limitations=tuple(limitations),
    )
