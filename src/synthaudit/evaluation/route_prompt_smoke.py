"""Offline Phase 10 contract smoke without provider experiments or performance metrics."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from synthaudit.adapters.mapped_reaction_smiles import (
    MappedReactionSmilesAdapter,
    MappedReactionSmilesInput,
)
from synthaudit.audit.route import RouteAuditor
from synthaudit.counterfactuals import CounterfactualGenerator, GenerationMethod
from synthaudit.prompting import (
    PromptModelRequestV1,
    PromptRobustnessCaseGenerator,
    PromptVariantKind,
    UnavailablePromptModelProvider,
)
from synthaudit.schema.common import MoleculeRecord, MoleculeRole, ProvenanceRecord, StrictModel
from synthaudit.schema.evidence import EvidenceAvailability
from synthaudit.schema.reaction_ir import ReactionIRV1
from synthaudit.schema.results import CheckStatus
from synthaudit.schema.route_ir import RouteIRV1, RouteStepIRV1

_PROVENANCE = (
    ProvenanceRecord(
        source="synthaudit-authored-route-prompt-smoke",
        source_version="1",
        license="Apache-2.0 fixture; no experimental evidence",
    ),
)


class RoutePromptContractSmokeV1(StrictModel):
    schema_version: Literal["synthaudit.route-prompt-contract-smoke/1"] = (
        "synthaudit.route-prompt-contract-smoke/1"
    )
    route_check_count: int = Field(ge=15)
    required_route_outputs_present: bool
    route_success_probability_reported: Literal[False] = False
    route_perturbation_count: Literal[5] = 5
    all_route_perturbations_detected: bool
    prompt_variant_count: Literal[5] = 5
    prompt_variant_kinds: tuple[PromptVariantKind, ...]
    default_prompt_provider_unavailable: bool
    expensive_provider_experiments_run: Literal[False] = False
    metrics_status: Literal["not_run"] = "not_run"
    notice: Literal[
        "SynthAudit estimates representation validity, corpus novelty and evidence-based plausibility. It does not establish experimental feasibility, yield, selectivity, safety or scalability."
    ] = (
        "SynthAudit estimates representation validity, corpus novelty and evidence-based "
        "plausibility. It does not establish experimental feasibility, yield, selectivity, "
        "safety or scalability."
    )


def _route() -> RouteIRV1:
    reactions = tuple(
        ReactionIRV1(
            reaction_id=f"route-prompt-smoke-reaction-{index}",
            product=MoleculeRecord(mapped_smiles=f"[CH4:{index}]", role=MoleculeRole.PRODUCT),
        )
        for index in (1, 2, 3)
    )
    return RouteIRV1(
        route_id="route-prompt-contract-smoke",
        target=reactions[-1].product.model_copy(
            update={"identifiers": {"route_node_id": "target"}}
        ),
        starting_materials=(
            MoleculeRecord(
                mapped_smiles="[CH4:10]",
                role=MoleculeRole.STARTING_MATERIAL,
                identifiers={"route_node_id": "start"},
            ),
        ),
        steps=(
            RouteStepIRV1(
                step_id="step-1",
                reaction=reactions[0],
                consumes=("start",),
                produces=("protected",),
                strategy_text="protection",
            ),
            RouteStepIRV1(
                step_id="step-2",
                reaction=reactions[1],
                depends_on=("step-1",),
                consumes=("protected",),
                produces=("fragile",),
                strategy_text="coupling",
            ),
            RouteStepIRV1(
                step_id="step-3",
                reaction=reactions[2],
                depends_on=("step-2",),
                consumes=("fragile",),
                produces=("target",),
                strategy_text="deprotection",
            ),
        ),
        provenance=_PROVENANCE,
    )


def _prompt_reaction() -> ReactionIRV1:
    return MappedReactionSmilesAdapter().to_reaction_ir(
        MappedReactionSmilesInput(
            reaction_smiles=("[CH3:1][CH2:2][Br:3].[OH-:4]>>[CH3:1][CH2:2][OH:4]"),
            reaction_id="route-prompt-smoke-prompt-reaction",
        )
    )


def run_route_prompt_contract_smoke() -> RoutePromptContractSmokeV1:
    route = _route()
    audit = RouteAuditor().audit(route)
    required_outputs = (
        all(
            hasattr(audit, name)
            for name in (
                "minimum_step_support",
                "maximum_uncertainty",
                "structural_blocking_steps",
                "unresolved_completion_failures",
                "stereo_sensitive_steps",
                "high_novelty_key_steps",
                "critical_condition_conflicts",
                "expert_review_queue",
            )
        )
        and "route_success_probability" not in audit.model_dump()
    )

    generator = CounterfactualGenerator()
    parent = generator.recorded_route(
        route,
        record_id="recorded-route-prompt-contract-smoke",
        source_dataset="synthaudit-authored-route-prompt-smoke",
        source_version="1",
        data_license_status="Apache-2.0 fixture; no experimental evidence",
        reaction_class="authored-route-contract",
    )
    methods = (
        GenerationMethod.DEPENDENCY_VIOLATING_STEP_SWAP,
        GenerationMethod.DEPROTECTION_TOO_EARLY,
        GenerationMethod.PROTECTION_TOO_LATE,
        GenerationMethod.FRAGILE_INTERMEDIATE_INCOMPATIBLE_CONDITIONS,
        GenerationMethod.PRECURSOR_NOT_PRODUCED,
    )
    expected_checks = {
        GenerationMethod.DEPENDENCY_VIOLATING_STEP_SWAP: "route.ordering",
        GenerationMethod.DEPROTECTION_TOO_EARLY: "route.protection_deprotection_timing",
        GenerationMethod.PROTECTION_TOO_LATE: "route.protection_deprotection_timing",
        GenerationMethod.FRAGILE_INTERMEDIATE_INCOMPATIBLE_CONDITIONS: (
            "route.condition_sensitive_intermediate_lifetime"
        ),
        GenerationMethod.PRECURSOR_NOT_PRODUCED: "route.precursor_intermediate_continuity",
    }
    detected = []
    for index, method in enumerate(methods):
        candidate = generator.generate_route(parent, method=method, seed=700 + index)
        if candidate.route is None:
            detected.append(False)
            continue
        candidate_audit = RouteAuditor().audit(candidate.route)
        detected.append(
            next(
                item.status
                for item in candidate_audit.checks
                if item.check_id == expected_checks[method]
            )
            == CheckStatus.FAIL
        )

    prompt_case = PromptRobustnessCaseGenerator().build_case(
        _prompt_reaction(),
        parent_group_id="route-prompt-smoke-parent",
        seed=811,
    )
    request = PromptModelRequestV1(
        request_id="route-prompt-smoke-request",
        case_id=prompt_case.case_id,
        variant=prompt_case.variants[0],
        mapped_product_smiles=prompt_case.reference_reaction.product.mapped_smiles,
    )
    provider_output = UnavailablePromptModelProvider().generate(request)
    return RoutePromptContractSmokeV1(
        route_check_count=len(audit.checks),
        required_route_outputs_present=required_outputs,
        all_route_perturbations_detected=all(detected),
        prompt_variant_kinds=tuple(item.kind for item in prompt_case.variants),
        default_prompt_provider_unavailable=(
            provider_output.availability == EvidenceAvailability.UNAVAILABLE
        ),
    )
