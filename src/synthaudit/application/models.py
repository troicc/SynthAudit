"""Versioned product-layer command and normalization contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field, JsonValue

from synthaudit.schema.common import ProvenanceRecord, StrictModel
from synthaudit.schema.reaction_ir import ReactionIRV1


class CommandStatus(StrEnum):
    OK = "ok"
    ERROR = "error"
    UNAVAILABLE = "unavailable"


class ReactionSourceKind(StrEnum):
    REACTION_IR = "reaction_ir"
    MAPPED_REACTION_SMILES = "mapped_reaction_smiles"
    REACTSEQ = "reactseq"
    SYNTHEX_PAPER_DRAFT = "synthaudit.synthex-paper-draft/0.1"


class NormalizedReactionV1(StrictModel):
    """One normalized reaction plus source-specific, non-semantic details."""

    schema_version: Literal["synthaudit.normalized-reaction/1"] = "synthaudit.normalized-reaction/1"
    source_kind: ReactionSourceKind
    adapter_id: str
    reaction_ir: ReactionIRV1
    warnings: tuple[str, ...] = ()
    unsupported_fields: tuple[str, ...] = ()
    traversal_context: dict[str, JsonValue] | None = None
    provenance: tuple[ProvenanceRecord, ...] = Field(min_length=1)


class CommandErrorV1(StrictModel):
    error_type: str = Field(min_length=1)
    message: str = Field(min_length=1)
    hint: str | None = None


class CommandEnvelopeV1(StrictModel):
    """Uniform JSON/Rich boundary for product-facing commands."""

    schema_version: Literal["synthaudit.command-envelope/1"] = "synthaudit.command-envelope/1"
    command: str = Field(min_length=1)
    status: CommandStatus
    payload: JsonValue | None = None
    error: CommandErrorV1 | None = None
    notice: Literal[
        "SynthAudit estimates representation validity, corpus novelty and evidence-based plausibility. It does not establish experimental feasibility, yield, selectivity, safety or scalability."
    ] = (
        "SynthAudit estimates representation validity, corpus novelty and evidence-based "
        "plausibility. It does not establish experimental feasibility, yield, selectivity, "
        "safety or scalability."
    )
    provenance: tuple[ProvenanceRecord, ...] = Field(min_length=1)

    @classmethod
    def success(cls, command: str, payload: JsonValue) -> CommandEnvelopeV1:
        from synthaudit import __version__

        return cls(
            command=command,
            status=CommandStatus.OK,
            payload=payload,
            provenance=(
                ProvenanceRecord(
                    source="synthaudit",
                    source_version=__version__,
                    adapter=f"cli:{command}",
                    adapter_version="1",
                    license="Apache-2.0",
                ),
            ),
        )

    @classmethod
    def failure(
        cls,
        command: str,
        exc: Exception,
        *,
        hint: str | None = None,
        unavailable: bool = False,
    ) -> CommandEnvelopeV1:
        from synthaudit import __version__

        return cls(
            command=command,
            status=CommandStatus.UNAVAILABLE if unavailable else CommandStatus.ERROR,
            error=CommandErrorV1(
                error_type=type(exc).__name__,
                message=str(exc),
                hint=hint,
            ),
            provenance=(
                ProvenanceRecord(
                    source="synthaudit",
                    source_version=__version__,
                    adapter=f"cli:{command}",
                    adapter_version="1",
                    license="Apache-2.0",
                ),
            ),
        )
