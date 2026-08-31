"""Shared versioned schema primitives."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, JsonValue


class StrictModel(BaseModel):
    """Base model with deterministic, fail-closed validation."""

    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)


class MoleculeRole(StrEnum):
    PRODUCT = "product"
    PRECURSOR = "precursor"
    SYNTHON = "synthon"
    FRAGMENT = "fragment"
    INTERMEDIATE = "intermediate"
    STARTING_MATERIAL = "starting_material"


class MoleculeRecord(StrictModel):
    """A molecular graph serialized as atom-mapped SMILES."""

    mapped_smiles: str = Field(min_length=1)
    role: MoleculeRole
    name: str | None = None
    identifiers: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class ProvenanceRecord(StrictModel):
    """Version and artifact information for one producing step."""

    source: str = Field(min_length=1)
    source_version: str | None = None
    source_commit: str | None = None
    adapter: str | None = None
    adapter_version: str | None = None
    artifact_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    license: str | None = None
    generated_at: datetime | None = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class SourcePayloadReference(StrictModel):
    """Reference to a preserved source payload without embedding secrets."""

    representation: str = Field(min_length=1)
    uri: str | None = None
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    media_type: str = "application/json"
    byte_length: int | None = Field(default=None, ge=0)


class ReactionConditions(StrictModel):
    """Structured conditions while retaining source-level text."""

    temperature_c: float | None = None
    time_hours: float | None = Field(default=None, ge=0)
    solvents: tuple[str, ...] = ()
    catalysts: tuple[str, ...] = ()
    reagents: tuple[str, ...] = ()
    atmosphere: str | None = None
    pressure_bar: float | None = Field(default=None, gt=0)
    source_text: str | None = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict)
