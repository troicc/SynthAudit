"""Provider-neutral evidence records."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field, JsonValue

from synthaudit.schema.common import ProvenanceRecord, StrictModel


class EvidenceAvailability(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    INDETERMINATE = "indeterminate"
    UNSUPPORTED = "unsupported"


class EvidenceValueV1(StrictModel):
    schema_version: Literal["synthaudit.evidence/1"] = "synthaudit.evidence/1"
    evidence_id: str = Field(min_length=1)
    stage: Literal["reaction_centre", "completion", "stereo", "route_context", "novelty"]
    availability: EvidenceAvailability
    value: float | None = None
    calibrated: bool = False
    calibration_method: str | None = None
    interpretation: str
    missing_reasons: tuple[str, ...] = ()
    provenance: tuple[ProvenanceRecord, ...] = ()
    metadata: dict[str, JsonValue] = Field(default_factory=dict)
