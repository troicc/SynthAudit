"""Representation-independent ReactionIR semantic hashing."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from rdkit import Chem

from synthaudit.schema.edits import EditBase
from synthaudit.schema.reaction_ir import ReactionIRV1


class SemanticHashError(ValueError):
    """Raised when semantic material cannot be canonicalized safely."""


def canonicalize_mapped_smiles(smiles: str) -> str:
    """Canonicalize a mapped structure and deterministically order fragments."""
    molecule = Chem.MolFromSmiles(smiles)
    if molecule is None:
        raise SemanticHashError(f"cannot parse mapped SMILES: {smiles!r}")
    canonical = Chem.MolToSmiles(molecule, canonical=True, isomericSmiles=True)
    return ".".join(sorted(canonical.split(".")))


def _normalized_edit(edit: EditBase) -> dict[str, Any]:
    payload = edit.model_dump(
        mode="json",
        exclude_none=True,
        exclude={"edit_id", "source_range", "metadata"},
    )
    if "map_a" in payload and "map_b" in payload and payload["map_a"] > payload["map_b"]:
        payload["map_a"], payload["map_b"] = payload["map_b"], payload["map_a"]
        if "stereo_atom_a" in payload or "stereo_atom_b" in payload:
            payload["stereo_atom_a"], payload["stereo_atom_b"] = (
                payload.get("stereo_atom_b"),
                payload.get("stereo_atom_a"),
            )
    if "connections" in payload:
        payload["connections"] = sorted(
            payload["connections"],
            key=lambda item: (
                item["product_atom_map"],
                item["fragment_atom_map"],
                item["order"],
            ),
        )
    if "fragment_atom_maps" in payload:
        payload["fragment_atom_maps"] = sorted(payload["fragment_atom_maps"])
    if "attachment_bonds" in payload:
        payload["attachment_bonds"] = sorted(sorted(pair) for pair in payload["attachment_bonds"])
    return payload


def reaction_ir_semantic_payload(
    reaction: ReactionIRV1,
    reconstructed_precursors: tuple[str, ...] | list[str] | None = None,
) -> dict[str, Any]:
    """Build the stable chemical-semantic payload used by the hash."""

    def normalized_stage(edits: tuple[EditBase, ...]) -> list[dict[str, Any]]:
        normalized = [_normalized_edit(edit) for edit in edits]
        return sorted(
            normalized,
            key=lambda value: json.dumps(value, sort_keys=True, separators=(",", ":")),
        )

    precursor_smiles = (
        list(reconstructed_precursors)
        if reconstructed_precursors is not None
        else [item.mapped_smiles for item in reaction.expected_precursors]
    )
    return {
        "schema": "synthaudit.reaction-semantic-hash/1",
        "direction": reaction.direction,
        "product": canonicalize_mapped_smiles(reaction.product.mapped_smiles),
        "core_edits": normalized_stage(reaction.core_edits),
        "attachment_edits": normalized_stage(reaction.attachment_edits),
        "atom_state_edits": normalized_stage(reaction.atom_state_edits),
        "stereo_edits": normalized_stage(reaction.stereo_edits),
        "precursors": sorted(canonicalize_mapped_smiles(item) for item in precursor_smiles),
    }


def reaction_ir_semantic_hash(
    reaction: ReactionIRV1,
    reconstructed_precursors: tuple[str, ...] | list[str] | None = None,
) -> str:
    """Hash normalized edits and reconstructed or expected precursor graphs."""
    payload = reaction_ir_semantic_payload(reaction, reconstructed_precursors)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()
