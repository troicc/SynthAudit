"""Observed structural-validity results for benchmark candidates."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from synthaudit import __version__
from synthaudit.counterfactuals.models import (
    StepStructuralValidityV1,
    StructuralValidityResultV1,
)
from synthaudit.graph.executor import ReactionExecutor
from synthaudit.schema.common import ProvenanceRecord
from synthaudit.schema.evidence import EvidenceAvailability
from synthaudit.schema.reaction_ir import ReactionIRV1
from synthaudit.schema.route_ir import RouteIRV1


def _provenance(evaluator: str) -> tuple[ProvenanceRecord, ...]:
    return (
        ProvenanceRecord(
            source="synthaudit",
            source_version=__version__,
            adapter=evaluator,
            adapter_version="1",
            license="Apache-2.0",
        ),
    )


def evaluate_reaction(reaction: ReactionIRV1) -> StructuralValidityResultV1:
    result = ReactionExecutor().execute(reaction)
    errors: tuple[str, ...] = ()
    if result.error is not None:
        errors = (f"{result.error.error_type}: {result.error.message}",)
    return StructuralValidityResultV1(
        evaluator="ReactionExecutor",
        evaluation_scope="reaction",
        availability=EvidenceAvailability.AVAILABLE,
        execution_success=result.success,
        structurally_valid=result.structurally_valid,
        errors=errors,
        provenance=_provenance("ReactionExecutor"),
    )


def evaluate_reaction_payload(
    payload: Mapping[str, Any],
) -> tuple[ReactionIRV1 | None, StructuralValidityResultV1]:
    try:
        reaction = ReactionIRV1.model_validate(payload)
    except ValidationError as exc:
        return None, StructuralValidityResultV1(
            evaluator="ReactionIRV1.model_validate",
            evaluation_scope="raw_payload",
            availability=EvidenceAvailability.AVAILABLE,
            execution_success=False,
            structurally_valid=False,
            errors=(str(exc),),
            provenance=_provenance("ReactionIRV1.model_validate"),
        )
    return reaction, evaluate_reaction(reaction)


def evaluate_route(route: RouteIRV1) -> StructuralValidityResultV1:
    step_results: list[StepStructuralValidityV1] = []
    errors: list[str] = []
    ordered_step_ids: set[str] = set()
    produced: set[str] = {
        identifier
        for molecule in route.starting_materials
        for identifier in (
            molecule.identifiers.get("route_node_id"),
            molecule.name,
        )
        if identifier
    }
    for step in route.steps:
        result = ReactionExecutor().execute(step.reaction)
        step_results.append(
            StepStructuralValidityV1(
                step_id=step.step_id,
                execution_success=result.success,
                structurally_valid=result.structurally_valid,
                error_type=result.error.error_type if result.error else None,
                error_message=result.error.message if result.error else None,
            )
        )
        missing_dependencies = sorted(set(step.depends_on) - ordered_step_ids)
        if missing_dependencies:
            errors.append(f"step {step.step_id} appears before dependencies {missing_dependencies}")
        missing_inputs = sorted(set(step.consumes) - produced)
        if missing_inputs:
            errors.append(f"step {step.step_id} consumes unavailable nodes {missing_inputs}")
        ordered_step_ids.add(step.step_id)
        produced.update(step.produces)
    execution_success = all(item.execution_success for item in step_results) and not errors
    structurally_valid = all(item.structurally_valid for item in step_results) and not errors
    return StructuralValidityResultV1(
        evaluator="ReactionExecutor+declared-route-order-v1",
        evaluation_scope="route",
        availability=EvidenceAvailability.AVAILABLE,
        execution_success=execution_success,
        structurally_valid=structurally_valid,
        step_results=tuple(step_results),
        errors=tuple(errors),
        provenance=_provenance("declared-route-order-v1"),
    )


def evaluate_route_payload(
    payload: Mapping[str, Any],
) -> tuple[RouteIRV1 | None, StructuralValidityResultV1]:
    try:
        route = RouteIRV1.model_validate(payload)
    except ValidationError as exc:
        return None, StructuralValidityResultV1(
            evaluator="RouteIRV1.model_validate",
            evaluation_scope="raw_payload",
            availability=EvidenceAvailability.AVAILABLE,
            execution_success=False,
            structurally_valid=False,
            errors=(str(exc),),
            provenance=_provenance("RouteIRV1.model_validate"),
        )
    return route, evaluate_route(route)
