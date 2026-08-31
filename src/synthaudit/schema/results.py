"""Shared audit and semantic-comparison results."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field, JsonValue

from synthaudit.schema.common import ProvenanceRecord, StrictModel


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    BLOCKING = "blocking"


class CheckStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    WARNING = "warning"
    INDETERMINATE = "indeterminate"
    UNAVAILABLE = "unavailable"
    UNSUPPORTED = "unsupported"


class CheckResultV1(StrictModel):
    schema_version: Literal["synthaudit.check-result/1"] = "synthaudit.check-result/1"
    check_id: str = Field(min_length=1)
    category: str = Field(min_length=1)
    severity: Severity
    status: CheckStatus
    message: str = Field(min_length=1)
    affected_atom_maps: tuple[int, ...] = ()
    evidence: dict[str, JsonValue] = Field(default_factory=dict)
    references: tuple[str, ...] = ()
    deterministic: bool = True


class ComparisonState(StrEnum):
    EQUIVALENT = "equivalent"
    DIFFERENT = "different"
    INDETERMINATE = "indeterminate"
    UNSUPPORTED = "unsupported"


class SemanticComparisonV1(StrictModel):
    schema_version: Literal["synthaudit.semantic-comparison/1"] = "synthaudit.semantic-comparison/1"
    state: ComparisonState
    exact_semantic_equivalence: bool | None
    equivalent_precursor_set: bool | None
    equivalent_reaction_centre: bool | None
    equivalent_attachment_completion: bool | None
    equivalent_stereo_result: bool | None
    mismatch_categories: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()
    provenance: tuple[ProvenanceRecord, ...] = ()
