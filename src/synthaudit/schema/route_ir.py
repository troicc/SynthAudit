"""Versioned canonical route representation."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, JsonValue, model_validator

from synthaudit.schema.common import MoleculeRecord, ProvenanceRecord, StrictModel
from synthaudit.schema.reaction_ir import ReactionIRV1


class RouteStepIRV1(StrictModel):
    schema_version: Literal["synthaudit.route-step-ir/1"] = "synthaudit.route-step-ir/1"
    step_id: str = Field(min_length=1)
    reaction: ReactionIRV1
    depends_on: tuple[str, ...] = ()
    consumes: tuple[str, ...] = ()
    produces: tuple[str, ...] = ()
    strategy_text: str | None = None
    key_step: bool = False
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_dependencies(self) -> RouteStepIRV1:
        if self.step_id in self.depends_on:
            raise ValueError("a route step cannot depend on itself")
        if len(self.depends_on) != len(set(self.depends_on)):
            raise ValueError("route step dependencies must be unique")
        return self


class RouteIRV1(StrictModel):
    schema_version: Literal["synthaudit.route-ir/1"] = "synthaudit.route-ir/1"
    route_id: str = Field(min_length=1)
    target: MoleculeRecord
    starting_materials: tuple[MoleculeRecord, ...] = ()
    intermediates: tuple[MoleculeRecord, ...] = ()
    steps: tuple[RouteStepIRV1, ...] = ()
    strategy_text: str | None = None
    provenance: tuple[ProvenanceRecord, ...] = ()
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_step_identity_and_references(self) -> RouteIRV1:
        step_ids = [step.step_id for step in self.steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("route step IDs must be unique")
        known = set(step_ids)
        unknown = sorted(
            dependency
            for step in self.steps
            for dependency in step.depends_on
            if dependency not in known
        )
        if unknown:
            raise ValueError(f"unknown route dependency references: {unknown}")
        return self
