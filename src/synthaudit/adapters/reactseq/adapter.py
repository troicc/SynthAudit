"""ReactSeq-to-ReactionIR normalization without importing legacy upstream code."""

from __future__ import annotations

import hashlib
from typing import cast

from rdkit import Chem

from synthaudit import __version__
from synthaudit.adapters.reactseq.header_parser import parse_header
from synthaudit.adapters.reactseq.models import (
    ReactSeqAdapterInput,
    ReactSeqAdapterResult,
)
from synthaudit.adapters.reactseq.tail_parser import parse_tails
from synthaudit.adapters.reactseq.tokenizer import parse_document
from synthaudit.adapters.reactseq.traversal import build_traversal_context
from synthaudit.schema.common import (
    MoleculeRecord,
    MoleculeRole,
    ProvenanceRecord,
    SourcePayloadReference,
)
from synthaudit.schema.reaction_ir import ReactionIRV1

REACTSEQ_UPSTREAM_COMMIT = "9838a3058e32e1c0ee04b2bab0448104dc293384"
REACTSEQ_REPOSITORY = "https://github.com/jiachengxiong/ReactSeq"


def _fallback_product_traversal(mapped_product_smiles: str) -> str:
    molecule = cast(Chem.Mol | None, Chem.MolFromSmiles(mapped_product_smiles))
    if molecule is None:
        return mapped_product_smiles
    for atom in molecule.GetAtoms():
        atom.SetAtomMapNum(0)
    return Chem.MolToSmiles(
        molecule,
        canonical=False,
        isomericSmiles=True,
        kekuleSmiles=True,
    )


class ReactSeqAdapter:
    """Normalize the pinned, source-inspected ReactSeq syntax conservatively."""

    def normalize(self, source: ReactSeqAdapterInput) -> ReactSeqAdapterResult:
        fallback = _fallback_product_traversal(source.mapped_product_smiles)
        document = parse_document(source.reactseq, fallback_product_smiles=fallback)
        context = build_traversal_context(document, source.mapped_product_smiles)
        header = parse_header(document, context, source.mapped_product_smiles)
        context = context.model_copy(
            update={"attachment_point_order": header.attachment_reactseq_indexes}
        )
        tails = parse_tails(
            document,
            context,
            header,
            source.mapped_product_smiles,
        )

        source_bytes = source.reactseq.encode("utf-8")
        digest = hashlib.sha256(source_bytes).hexdigest()
        reaction_id = source.reaction_id or f"reactseq-{digest[:16]}"
        warnings = list(tails.warnings)
        if header.hydrogen_attachment_reactseq_indexes:
            warnings.append(
                "ReactSeq '~' denotes direct attachment capacity from hydrogen; "
                "implicit hydrogen is consumed by the explicit completion bond"
            )
        provenance = (
            ProvenanceRecord(
                source=REACTSEQ_REPOSITORY,
                source_commit=REACTSEQ_UPSTREAM_COMMIT,
                adapter="synthaudit.adapters.reactseq.ReactSeqAdapter",
                adapter_version=__version__,
                license="LGPL-2.1",
                metadata={"compatibility": "source_inspected_safe_subset"},
            ),
        )
        reaction_ir = ReactionIRV1(
            reaction_id=reaction_id,
            product=MoleculeRecord(
                mapped_smiles=source.mapped_product_smiles,
                role=MoleculeRole.PRODUCT,
            ),
            expected_precursors=source.expected_precursors,
            core_edits=header.core_edits,
            attachment_edits=tails.attachment_edits,
            atom_state_edits=(*header.atom_state_edits, *tails.atom_state_edits),
            stereo_edits=header.stereo_edits,
            stage_metadata={
                "source_representation": "ReactSeq",
                "upstream_commit": REACTSEQ_UPSTREAM_COMMIT,
                "header_source_range": document.header_range.model_dump(mode="json"),
                "attachment_reactseq_indexes": list(header.attachment_reactseq_indexes),
                "hydrogen_attachment_reactseq_indexes": list(
                    header.hydrogen_attachment_reactseq_indexes
                ),
            },
            provenance=provenance,
            source_payload_reference=SourcePayloadReference(
                representation="reactseq",
                sha256=digest,
                media_type="text/plain; charset=utf-8",
                byte_length=len(source_bytes),
            ),
            metadata={"raw_source_preserved_by_sha256": True},
        )
        return ReactSeqAdapterResult(
            reaction_ir=reaction_ir,
            traversal_context=context,
            support_level="source_inspected_safe_subset",
            upstream_commit=REACTSEQ_UPSTREAM_COMMIT,
            warnings=tuple(dict.fromkeys(warnings)),
        )

    def to_reaction_ir(self, source: ReactSeqAdapterInput) -> ReactionIRV1:
        return self.normalize(source).reaction_ir
