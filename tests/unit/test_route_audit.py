from __future__ import annotations

import pytest
from pydantic import ValidationError

from synthaudit.adapters.mapped_reaction_smiles import (
    MappedReactionSmilesAdapter,
    MappedReactionSmilesInput,
)
from synthaudit.audit import RouteAuditor
from synthaudit.counterfactuals import CounterfactualGenerator, GenerationMethod
from synthaudit.schema import (
    MoleculeRecord,
    MoleculeRole,
    ProvenanceRecord,
    ReactionConditions,
    RouteAuditResultV1,
    RouteIRV1,
    RouteStepEvidenceV1,
    RouteStepIRV1,
)
from synthaudit.schema.results import CheckStatus

PROVENANCE = (
    ProvenanceRecord(
        source="authored-route-audit-fixture",
        source_version="1",
        license="Apache-2.0 fixture; no experimental evidence",
    ),
)


def _reaction(reaction_smiles: str, reaction_id: str):
    return MappedReactionSmilesAdapter().to_reaction_ir(
        MappedReactionSmilesInput(
            reaction_smiles=reaction_smiles,
            reaction_id=reaction_id,
        )
    )


def _route() -> RouteIRV1:
    first = _reaction(
        "[CH3:1][CH3:2]>>[CH3:1][CH2:2][Br:4]",
        "route-fixture-first",
    )
    second = _reaction(
        "[CH3:1][CH2:2][Br:4].[OH-:3]>>[CH3:1][CH2:2][OH:3]",
        "route-fixture-second",
    )
    return RouteIRV1(
        route_id="route-audit-fixture",
        target=second.product.model_copy(update={"identifiers": {"route_node_id": "target"}}),
        starting_materials=(
            first.expected_precursors[0].model_copy(
                update={
                    "role": MoleculeRole.STARTING_MATERIAL,
                    "identifiers": {"route_node_id": "start-carbon"},
                }
            ),
            second.expected_precursors[1].model_copy(
                update={
                    "role": MoleculeRole.STARTING_MATERIAL,
                    "identifiers": {"route_node_id": "start-hydroxide"},
                }
            ),
        ),
        intermediates=(
            first.product.model_copy(
                update={
                    "role": MoleculeRole.INTERMEDIATE,
                    "identifiers": {"route_node_id": "bromo-intermediate"},
                }
            ),
        ),
        steps=(
            RouteStepIRV1(
                step_id="step-1",
                reaction=first,
                consumes=("start-carbon",),
                produces=("bromo-intermediate",),
                strategy_text="protection",
                key_step=False,
            ),
            RouteStepIRV1(
                step_id="step-2",
                reaction=second,
                depends_on=("step-1",),
                consumes=("bromo-intermediate", "start-hydroxide"),
                produces=("target",),
                strategy_text="deprotection",
                key_step=True,
            ),
        ),
        provenance=PROVENANCE,
    )


def _evidence() -> tuple[RouteStepEvidenceV1, ...]:
    return (
        RouteStepEvidenceV1(
            step_id="step-1",
            calibrated_evidence_support_score=0.8,
            uncertainty=0.1,
            product_novelty=0.4,
            provenance=PROVENANCE,
        ),
        RouteStepEvidenceV1(
            step_id="step-2",
            calibrated_evidence_support_score=0.6,
            uncertainty=0.35,
            product_novelty=0.8,
            provenance=PROVENANCE,
        ),
    )


def _check_status(result: RouteAuditResultV1, check_id: str) -> CheckStatus:
    return next(item.status for item in result.checks if item.check_id == check_id)


def test_route_audit_reports_required_independent_outputs_without_success_probability() -> None:
    result = RouteAuditor().audit(
        _route(),
        step_evidence=_evidence(),
        high_uncertainty_threshold=0.3,
    )
    assert result.minimum_step_support == pytest.approx(0.6)
    assert result.maximum_uncertainty == pytest.approx(0.35)
    assert result.maximum_uncertainty_steps == ("step-2",)
    assert result.high_novelty_key_steps == ("step-2",)
    assert not result.structural_blocking_steps
    assert not result.unresolved_completion_failures
    assert result.exploratory_naive_independence_score is None
    assert "route_success_probability" not in result.model_dump()
    assert _check_status(result, "route.acyclic_dependencies") == CheckStatus.PASS
    assert _check_status(result, "route.atom_map_continuity") == CheckStatus.PASS
    assert [item.priority for item in result.expert_review_queue] == sorted(
        item.priority for item in result.expert_review_queue
    )


def test_exploratory_independence_product_is_opt_in_and_explicitly_not_probability() -> None:
    result = RouteAuditor().audit(
        _route(),
        step_evidence=_evidence(),
        compute_exploratory_naive_independence_score=True,
    )
    assert result.exploratory_naive_independence_score == pytest.approx(0.48)
    assert result.exploratory_score_interpretation is not None
    assert "not a route success probability" in result.exploratory_score_interpretation

    payload = result.model_dump(mode="json")
    payload["exploratory_score_interpretation"] = None
    with pytest.raises(ValidationError, match="requires its non-probability label"):
        RouteAuditResultV1.model_validate(payload)


def test_dependency_cycles_order_and_unproduced_precursors_are_blocking() -> None:
    route = _route()
    steps = (
        route.steps[0].model_copy(update={"depends_on": ("step-2",)}),
        route.steps[1].model_copy(
            update={"depends_on": ("step-1",), "consumes": ("missing-node",)}
        ),
    )
    result = RouteAuditor().audit(route.model_copy(update={"steps": steps}))
    assert result.blocking
    assert _check_status(result, "route.acyclic_dependencies") == CheckStatus.FAIL
    assert _check_status(result, "route.ordering") == CheckStatus.FAIL
    assert _check_status(result, "route.precursor_intermediate_continuity") == CheckStatus.FAIL


def test_atom_map_discontinuity_is_not_silently_normalized() -> None:
    route = _route()
    conflicting = MoleculeRecord(
        mapped_smiles="[CH3:10][CH2:20][Br:40]",
        role=MoleculeRole.INTERMEDIATE,
        identifiers={"route_node_id": "bromo-intermediate"},
    )
    result = RouteAuditor().audit(route.model_copy(update={"intermediates": (conflicting,)}))
    assert _check_status(result, "route.atom_map_continuity") == CheckStatus.FAIL
    assert result.blocking


def test_protection_and_fragile_condition_timing_are_transparent_rules() -> None:
    route = _route()
    bad_protection_steps = (
        route.steps[0].model_copy(update={"strategy_text": "deprotection"}),
        route.steps[1].model_copy(update={"strategy_text": "protection"}),
    )
    protection_result = RouteAuditor().audit(
        route.model_copy(update={"steps": bad_protection_steps})
    )
    assert (
        _check_status(protection_result, "route.protection_deprotection_timing") == CheckStatus.FAIL
    )

    fragile = route.intermediates[0].model_copy(
        update={"metadata": {"fragile_to_condition_tags": ["strong_acid"]}}
    )
    acidic_reaction = route.steps[1].reaction.model_copy(
        update={"conditions": ReactionConditions(reagents=("strong_acid",))}
    )
    acidic_step = route.steps[1].model_copy(update={"reaction": acidic_reaction})
    condition_result = RouteAuditor().audit(
        route.model_copy(
            update={"intermediates": (fragile,), "steps": (route.steps[0], acidic_step)}
        )
    )
    assert (
        _check_status(condition_result, "route.condition_sensitive_intermediate_lifetime")
        == CheckStatus.FAIL
    )
    assert condition_result.critical_condition_conflicts


@pytest.mark.parametrize(
    "method",
    [
        GenerationMethod.DEPENDENCY_VIOLATING_STEP_SWAP,
        GenerationMethod.DEPROTECTION_TOO_EARLY,
        GenerationMethod.PROTECTION_TOO_LATE,
        GenerationMethod.FRAGILE_INTERMEDIATE_INCOMPATIBLE_CONDITIONS,
        GenerationMethod.PRECURSOR_NOT_PRODUCED,
    ],
)
def test_all_route_counterfactual_perturbations_reach_a_named_route_check(
    method: GenerationMethod,
) -> None:
    generator = CounterfactualGenerator()
    parent = generator.recorded_route(
        _route(),
        record_id="recorded-route-audit-fixture",
        source_dataset="authored-route-audit-fixture",
        source_version="1",
        data_license_status="Apache-2.0 fixture; no experimental evidence",
        reaction_class="authored-route-contract",
    )
    candidate = generator.generate_route(parent, method=method, seed=17)
    assert candidate.route is not None
    result = RouteAuditor().audit(candidate.route)
    expected_check = {
        GenerationMethod.DEPENDENCY_VIOLATING_STEP_SWAP: "route.ordering",
        GenerationMethod.DEPROTECTION_TOO_EARLY: "route.protection_deprotection_timing",
        GenerationMethod.PROTECTION_TOO_LATE: "route.protection_deprotection_timing",
        GenerationMethod.FRAGILE_INTERMEDIATE_INCOMPATIBLE_CONDITIONS: (
            "route.condition_sensitive_intermediate_lifetime"
        ),
        GenerationMethod.PRECURSOR_NOT_PRODUCED: "route.precursor_intermediate_continuity",
    }[method]
    assert _check_status(result, expected_check) == CheckStatus.FAIL
