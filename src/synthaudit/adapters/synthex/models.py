"""Inputs for the visibly namespaced SynthEx paper-draft adapter."""

from __future__ import annotations

from pydantic import Field, JsonValue

from synthaudit.schema.common import StrictModel


class SynthExPaperDraftInput(StrictModel):
    payload: JsonValue
    mapped_product_smiles: str | None = Field(default=None, min_length=1)
    reaction_id: str | None = None


class SynthExPaperDraftRouteInput(StrictModel):
    payload: JsonValue
    route_id: str | None = None
