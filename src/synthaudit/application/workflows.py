"""Fail-closed file and normalization workflows shared across product surfaces."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from pydantic import JsonValue

from synthaudit import __version__
from synthaudit.adapters.mapped_reaction_smiles import (
    MappedReactionSmilesAdapter,
    MappedReactionSmilesInput,
)
from synthaudit.adapters.reactseq import ReactSeqAdapter, ReactSeqAdapterInput
from synthaudit.adapters.synthex import SynthExPaperDraftAdapter, SynthExPaperDraftInput
from synthaudit.application.models import NormalizedReactionV1, ReactionSourceKind
from synthaudit.precedent.index import ReferenceIndex
from synthaudit.precedent.models import ReferenceReactionV1
from synthaudit.schema.common import ProvenanceRecord
from synthaudit.schema.reaction_ir import ReactionIRV1
from synthaudit.schema.route_ir import RouteIRV1


def read_json(path: str | Path) -> JsonValue:
    """Read JSON without repairing malformed content."""
    return cast(JsonValue, json.loads(Path(path).read_text(encoding="utf-8")))


def write_json(path: str | Path, payload: JsonValue) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


def _object(payload: JsonValue, *, label: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return {str(key): value for key, value in payload.items()}


def load_reaction_ir(path: str | Path) -> ReactionIRV1:
    return ReactionIRV1.model_validate(read_json(path))


def load_route_ir(path: str | Path) -> RouteIRV1:
    return RouteIRV1.model_validate(read_json(path))


def normalize_reaction_source(
    source_kind: ReactionSourceKind | str,
    source_text: str,
    *,
    mapped_product_smiles: str | None = None,
    reaction_id: str | None = None,
) -> NormalizedReactionV1:
    """Normalize one explicitly declared representation without semantic guessing."""
    kind = ReactionSourceKind(source_kind)
    workflow_provenance = (
        ProvenanceRecord(
            source="synthaudit",
            source_version=__version__,
            adapter="normalize_reaction_source",
            adapter_version="1",
            license="Apache-2.0",
            metadata={"source_kind": kind.value},
        ),
    )
    if kind == ReactionSourceKind.REACTION_IR:
        reaction = ReactionIRV1.model_validate(json.loads(source_text))
        if reaction_id is not None:
            reaction = reaction.model_copy(update={"reaction_id": reaction_id})
        return NormalizedReactionV1(
            source_kind=kind,
            adapter_id="synthaudit.reaction-ir/1",
            reaction_ir=reaction,
            provenance=(*reaction.provenance, *workflow_provenance),
        )
    if kind == ReactionSourceKind.MAPPED_REACTION_SMILES:
        mapped_result = MappedReactionSmilesAdapter().normalize(
            MappedReactionSmilesInput(
                reaction_smiles=source_text.strip(),
                reaction_id=reaction_id,
            )
        )
        return NormalizedReactionV1(
            source_kind=kind,
            adapter_id=mapped_result.adapter_id,
            reaction_ir=mapped_result.reaction_ir,
            warnings=tuple(item.message for item in mapped_result.warnings),
            unsupported_fields=mapped_result.unsupported_fields,
            provenance=(*mapped_result.reaction_ir.provenance, *workflow_provenance),
        )
    if kind == ReactionSourceKind.REACTSEQ:
        if not mapped_product_smiles:
            raise ValueError("ReactSeq normalization requires an explicitly mapped product")
        reactseq_result = ReactSeqAdapter().normalize(
            ReactSeqAdapterInput(
                reactseq=source_text,
                mapped_product_smiles=mapped_product_smiles,
                reaction_id=reaction_id,
            )
        )
        return NormalizedReactionV1(
            source_kind=kind,
            adapter_id="synthaudit.reactseq-source-inspected-safe-subset/1",
            reaction_ir=reactseq_result.reaction_ir,
            warnings=reactseq_result.warnings,
            unsupported_fields=reactseq_result.unsupported_fields,
            traversal_context=reactseq_result.traversal_context.model_dump(mode="json"),
            provenance=(*reactseq_result.reaction_ir.provenance, *workflow_provenance),
        )
    if not mapped_product_smiles:
        payload = _object(json.loads(source_text), label="SynthEx paper-draft payload")
        product = payload.get("mapped_product_smiles")
        mapped_product_smiles = product if isinstance(product, str) else None
    draft_result = SynthExPaperDraftAdapter().normalize(
        SynthExPaperDraftInput(
            payload=json.loads(source_text),
            mapped_product_smiles=mapped_product_smiles,
            reaction_id=reaction_id,
        )
    )
    return NormalizedReactionV1(
        source_kind=kind,
        adapter_id=draft_result.adapter_id,
        reaction_ir=draft_result.reaction_ir,
        warnings=tuple(item.message for item in draft_result.warnings),
        unsupported_fields=draft_result.unsupported_fields,
        provenance=(*draft_result.reaction_ir.provenance, *workflow_provenance),
    )


def prepare_reference_index(
    records_path: str | Path,
    output_path: str | Path,
    *,
    corpus_id: str,
    corpus_version: str,
) -> ReferenceIndex:
    """Build a content-addressed local index from strict JSONL reference records."""
    records: list[ReferenceReactionV1] = []
    for line_number, line in enumerate(
        Path(records_path).read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        try:
            records.append(ReferenceReactionV1.model_validate_json(line))
        except Exception as exc:
            raise ValueError(f"invalid reference record at line {line_number}: {exc}") from exc
    index = ReferenceIndex.build(
        records,
        corpus_id=corpus_id,
        corpus_version=corpus_version,
    )
    index.save(output_path)
    return index
