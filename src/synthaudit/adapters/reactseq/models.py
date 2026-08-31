"""Typed ReactSeq source, traversal, provider, and bridge models."""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import Field, JsonValue

from synthaudit.schema.common import MoleculeRecord, ProvenanceRecord, StrictModel
from synthaudit.schema.edits import (
    AtomStateEdit,
    AttachmentEdit,
    CoreEdit,
    SourceRange,
    StereoEdit,
)
from synthaudit.schema.reaction_ir import ReactionIRV1


class ReactSeqAtomToken(StrictModel):
    reactseq_atom_index: int = Field(ge=1)
    text: str
    source_range: SourceRange


class ReactSeqTailRecord(StrictModel):
    attachment_ordinal: int = Field(ge=0)
    raw: str
    source_range: SourceRange


class ReactSeqDocument(StrictModel):
    source: str
    original_product_smiles: str
    header: str
    header_range: SourceRange
    tails: tuple[ReactSeqTailRecord, ...]


class ReactSeqTraversalContext(StrictModel):
    """Resolve traversal-local atom identities before constructing ReactionIR."""

    schema_version: Literal["synthaudit.reactseq-traversal-context/1"] = (
        "synthaudit.reactseq-traversal-context/1"
    )
    original_product_smiles: str
    explicit_bond_product_smiles: str
    atom_token_spans: tuple[ReactSeqAtomToken, ...]
    reactseq_atom_index_to_rdkit_index: dict[int, int]
    rdkit_index_to_atom_map: dict[int, int]
    header_token_spans: tuple[SourceRange, ...]
    tail_token_spans: tuple[SourceRange, ...]
    attachment_point_order: tuple[int, ...] = ()
    mapping_method: Literal["indexed_source", "unique_graph_isomorphism"]

    def stable_map(self, reactseq_atom_index: int) -> int:
        rdkit_index = self.reactseq_atom_index_to_rdkit_index[reactseq_atom_index]
        return self.rdkit_index_to_atom_map[rdkit_index]


class ReactSeqHeaderParseResult(StrictModel):
    core_edits: tuple[CoreEdit, ...] = ()
    atom_state_edits: tuple[AtomStateEdit, ...] = ()
    stereo_edits: tuple[StereoEdit, ...] = ()
    attachment_reactseq_indexes: tuple[int, ...] = ()
    hydrogen_attachment_reactseq_indexes: tuple[int, ...] = ()


class ReactSeqTailParseResult(StrictModel):
    attachment_edits: tuple[AttachmentEdit, ...] = ()
    atom_state_edits: tuple[AtomStateEdit, ...] = ()
    warnings: tuple[str, ...] = ()


class ReactSeqAdapterResult(StrictModel):
    schema_version: Literal["synthaudit.reactseq-adapter-result/1"] = (
        "synthaudit.reactseq-adapter-result/1"
    )
    reaction_ir: ReactionIRV1
    traversal_context: ReactSeqTraversalContext
    support_level: Literal["source_inspected_safe_subset", "official_bridge"]
    upstream_commit: str
    warnings: tuple[str, ...] = ()
    unsupported_fields: tuple[str, ...] = ()


class ReactSeqAdapterInput(StrictModel):
    reactseq: str = Field(min_length=1)
    mapped_product_smiles: str = Field(min_length=1)
    reaction_id: str | None = None
    expected_precursors: tuple[MoleculeRecord, ...] = ()


class ReactSeqCandidate(StrictModel):
    reactseq: str
    rank: int = Field(ge=1)
    token_log_probabilities: tuple[float, ...] | None = None
    header_log_probability: float | None = None
    tail_log_probability: float | None = None
    total_log_probability: float | None = None
    meo_embedding: tuple[float, ...] | None = None
    provenance: tuple[ProvenanceRecord, ...] = ()


class ReactSeqPrediction(StrictModel):
    product_smiles: str
    prompt: str | None = None
    candidates: tuple[ReactSeqCandidate, ...]
    provenance: tuple[ProvenanceRecord, ...]


class ReactSeqModelProvider(Protocol):
    """Optional model boundary; core parsing never requires a checkpoint."""

    def predict(
        self,
        product_smiles: str,
        *,
        prompt: str | None = None,
        beam_size: int = 10,
    ) -> ReactSeqPrediction: ...


class ReactSeqBridgeRequest(StrictModel):
    protocol_version: Literal["synthaudit.reactseq-bridge/1"] = "synthaudit.reactseq-bridge/1"
    request_id: str = Field(min_length=1)
    operation: Literal["convert_reaction", "reconstruct_precursors", "inspect_runtime"]
    upstream_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    payload: dict[str, JsonValue] = Field(default_factory=dict)


class ReactSeqBridgeResponse(StrictModel):
    protocol_version: Literal["synthaudit.reactseq-bridge/1"] = "synthaudit.reactseq-bridge/1"
    request_id: str = Field(min_length=1)
    success: bool
    upstream_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    result: dict[str, JsonValue] = Field(default_factory=dict)
    error: dict[str, JsonValue] | None = None
    runtime: dict[str, JsonValue] = Field(default_factory=dict)
