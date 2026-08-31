"""Common typed adapter results."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, JsonValue

from synthaudit.schema.common import StrictModel
from synthaudit.schema.reaction_ir import ReactionIRV1
from synthaudit.schema.route_ir import RouteIRV1


class AdapterWarningV1(StrictModel):
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    affected_atom_maps: tuple[int, ...] = ()
    details: dict[str, JsonValue] = Field(default_factory=dict)


class ReactionAdapterResultV1(StrictModel):
    schema_version: Literal["synthaudit.reaction-adapter-result/1"] = (
        "synthaudit.reaction-adapter-result/1"
    )
    adapter_id: str
    reaction_ir: ReactionIRV1
    warnings: tuple[AdapterWarningV1, ...] = ()
    unsupported_fields: tuple[str, ...] = ()
    source_payload: JsonValue


class RouteAdapterResultV1(StrictModel):
    schema_version: Literal["synthaudit.route-adapter-result/1"] = (
        "synthaudit.route-adapter-result/1"
    )
    adapter_id: str
    route_ir: RouteIRV1
    warnings: tuple[AdapterWarningV1, ...] = ()
    unsupported_fields: tuple[str, ...] = ()
    source_payload: JsonValue
