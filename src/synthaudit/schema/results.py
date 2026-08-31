"""Shared audit and semantic-comparison results."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field, JsonValue, model_validator

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


class AtomSnapshotV1(StrictModel):
    atom_map: int = Field(ge=1)
    atomic_number: int = Field(ge=0)
    formal_charge: int
    isotope: int = Field(ge=0)
    aromatic: bool
    explicit_hydrogens: int = Field(ge=0)
    chiral_tag: str


class AtomPropertyChangeV1(StrictModel):
    atom_map: int = Field(ge=1)
    property: str
    before: JsonValue
    after: JsonValue


class BondSnapshotV1(StrictModel):
    map_a: int = Field(ge=1)
    map_b: int = Field(ge=1)
    order: float = Field(gt=0)
    stereo: str


class BondOrderChangeV1(StrictModel):
    map_a: int = Field(ge=1)
    map_b: int = Field(ge=1)
    before: float = Field(gt=0)
    after: float = Field(gt=0)


class StereoChangeV1(StrictModel):
    atom_maps: tuple[int, ...]
    before: str
    after: str


class GraphDiffV1(StrictModel):
    schema_version: Literal["synthaudit.graph-diff/1"] = "synthaudit.graph-diff/1"
    added_atoms: tuple[AtomSnapshotV1, ...] = ()
    removed_atoms: tuple[AtomSnapshotV1, ...] = ()
    changed_atom_properties: tuple[AtomPropertyChangeV1, ...] = ()
    added_bonds: tuple[BondSnapshotV1, ...] = ()
    removed_bonds: tuple[BondSnapshotV1, ...] = ()
    changed_bond_orders: tuple[BondOrderChangeV1, ...] = ()
    changed_tetrahedral_stereo: tuple[StereoChangeV1, ...] = ()
    changed_bond_stereo: tuple[StereoChangeV1, ...] = ()
    precursor_fragment_count_before: int = Field(ge=0)
    precursor_fragment_count_after: int = Field(ge=0)
    ring_count_before: int = Field(ge=0)
    ring_count_after: int = Field(ge=0)


class ExecutionErrorV1(StrictModel):
    error_type: str = Field(min_length=1)
    message: str = Field(min_length=1)
    operation_index: int | None = Field(default=None, ge=0)
    operation_type: str | None = None
    affected_atom_maps: tuple[int, ...] = ()
    rdkit_error: str | None = None
    details: dict[str, JsonValue] = Field(default_factory=dict)


class ExecutionResultBase(StrictModel):
    success: bool
    structurally_valid: bool
    input_mapped_structures: tuple[str, ...]
    mapped_structures: tuple[str, ...]
    diagnostic_mapped_structures: tuple[str, ...] = ()
    applied_operations: tuple[str, ...] = ()
    graph_diff: GraphDiffV1 | None = None
    warnings: tuple[str, ...] = ()
    error: ExecutionErrorV1 | None = None
    provenance: tuple[ProvenanceRecord, ...] = ()

    @model_validator(mode="after")
    def validate_success_contract(self) -> ExecutionResultBase:
        if self.success:
            if not self.structurally_valid:
                raise ValueError("successful execution must be structurally valid")
            if self.error is not None:
                raise ValueError("successful execution cannot contain an error")
        elif self.error is None:
            raise ValueError("failed execution must contain a structured error")
        return self


class CoreExecutionResult(ExecutionResultBase):
    schema_version: Literal["synthaudit.core-execution-result/1"] = (
        "synthaudit.core-execution-result/1"
    )
    stage: Literal["core"] = "core"


class CompletionExecutionResult(ExecutionResultBase):
    schema_version: Literal["synthaudit.completion-execution-result/1"] = (
        "synthaudit.completion-execution-result/1"
    )
    stage: Literal["completion"] = "completion"


class StereoExecutionResult(ExecutionResultBase):
    schema_version: Literal["synthaudit.stereo-execution-result/1"] = (
        "synthaudit.stereo-execution-result/1"
    )
    stage: Literal["stereo"] = "stereo"


class FullExecutionResult(ExecutionResultBase):
    schema_version: Literal["synthaudit.full-execution-result/1"] = (
        "synthaudit.full-execution-result/1"
    )
    stage: Literal["full"] = "full"
    core_result: CoreExecutionResult
    completion_result: CompletionExecutionResult | None = None
    stereo_result: StereoExecutionResult | None = None
