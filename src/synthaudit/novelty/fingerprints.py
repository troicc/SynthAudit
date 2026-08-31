"""Deterministic RDKit and semantic fingerprints for independent novelty views."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Sequence
from typing import Any, cast

from rdkit import Chem, DataStructs, rdBase
from rdkit.Chem import rdFingerprintGenerator
from rdkit.Chem.Scaffolds import MurckoScaffold

from synthaudit.graph.atom_maps import affected_atom_maps, atom_map_index
from synthaudit.graph.executor import ReactionExecutor
from synthaudit.schema.edits import AttachFragmentEdit, DetachFragmentEdit
from synthaudit.schema.reaction_ir import ReactionIRV1

MORGAN_RADIUS = 2
MORGAN_BITS = 2048
SEMANTIC_BITS = 2048


def _molecule(structures: str | Sequence[str]) -> Chem.Mol:
    values = (structures,) if isinstance(structures, str) else tuple(structures)
    molecule = cast(Chem.Mol | None, Chem.MolFromSmiles(".".join(values)))
    if molecule is None:
        raise ValueError("cannot fingerprint invalid molecular structure")
    return molecule


def _clear_maps(molecule: Chem.Mol) -> Chem.Mol:
    candidate = Chem.Mol(molecule)
    for atom in candidate.GetAtoms():
        atom.SetAtomMapNum(0)
    return candidate


def morgan_fingerprint(structures: str | Sequence[str]) -> Any:
    molecule = _clear_maps(_molecule(structures))
    generator = rdFingerprintGenerator.GetMorganGenerator(
        radius=MORGAN_RADIUS,
        fpSize=MORGAN_BITS,
        includeChirality=True,
    )
    return generator.GetFingerprint(molecule)


def scaffold_fingerprint(structures: str | Sequence[str]) -> Any | None:
    molecule = _clear_maps(_molecule(structures))
    fragments = Chem.GetMolFrags(molecule, asMols=True, sanitizeFrags=True)
    scaffold_smiles: list[str] = []
    for fragment in fragments:
        scaffold = MurckoScaffold.GetScaffoldForMol(fragment)  # type: ignore[no-untyped-call]
        if scaffold.GetNumAtoms():
            scaffold_smiles.append(Chem.MolToSmiles(scaffold, canonical=True, isomericSmiles=True))
    if not scaffold_smiles:
        return None
    return morgan_fingerprint(tuple(scaffold_smiles))


def precursor_structures(reaction: ReactionIRV1) -> tuple[str, ...]:
    if reaction.expected_precursors:
        return tuple(item.mapped_smiles for item in reaction.expected_precursors)
    execution = ReactionExecutor().execute(reaction)
    if not execution.success:
        raise ValueError(
            "precursor fingerprint unavailable because expected precursors are absent and "
            "ReactionIR execution failed"
        )
    return execution.mapped_structures


def _on_bits(fingerprint: Any) -> set[int]:
    return set(int(value) for value in fingerprint.GetOnBits())


def _bit_vector(bit_length: int, on_bits: Iterable[int]) -> Any:
    fingerprint = DataStructs.ExplicitBitVect(bit_length)
    for bit in on_bits:
        fingerprint.SetBit(int(bit))
    return fingerprint


def reaction_difference_fingerprint(reaction: ReactionIRV1) -> Any:
    product = _on_bits(morgan_fingerprint(reaction.product.mapped_smiles))
    precursors = _on_bits(morgan_fingerprint(precursor_structures(reaction)))
    gained = product - precursors
    lost = precursors - product
    return _bit_vector(
        MORGAN_BITS * 2,
        (*gained, *(MORGAN_BITS + value for value in lost)),
    )


def _hash_tokens(tokens: Iterable[str], *, bit_length: int = SEMANTIC_BITS) -> Any:
    bits: set[int] = set()
    for token in sorted(set(tokens)):
        digest = hashlib.sha256(token.encode()).digest()
        bits.add(int.from_bytes(digest[:8], "big") % bit_length)
    return _bit_vector(bit_length, bits)


def _canonical_unmapped(smiles: str) -> str:
    molecule = _clear_maps(_molecule(smiles))
    return Chem.MolToSmiles(molecule, canonical=True, isomericSmiles=True)


def _product_descriptors(reaction: ReactionIRV1) -> dict[int, str]:
    molecule = _molecule(reaction.product.mapped_smiles)
    mapping = atom_map_index(molecule)
    candidate = _clear_maps(molecule)
    ranks = tuple(Chem.CanonicalRankAtoms(candidate, breakTies=False, includeChirality=True))
    result: dict[int, str] = {}
    for atom_map, index in mapping.items():
        atom = candidate.GetAtomWithIdx(index)
        result[atom_map] = ":".join(
            map(
                str,
                (
                    atom.GetAtomicNum(),
                    atom.GetFormalCharge(),
                    int(atom.GetIsAromatic()),
                    atom.GetDegree(),
                    ranks[index],
                ),
            )
        )
    return result


def normalized_edit_tokens(reaction: ReactionIRV1) -> tuple[str, ...]:
    descriptors = _product_descriptors(reaction)
    tokens: list[str] = []
    for core_edit in reaction.core_edits:
        endpoints = sorted(
            (
                descriptors.get(core_edit.map_a, "missing"),
                descriptors.get(core_edit.map_b, "missing"),
            )
        )
        payload = core_edit.model_dump(
            mode="json",
            exclude={"edit_id", "source_range", "metadata", "map_a", "map_b"},
        )
        tokens.append(
            f"core:{core_edit.edit_type}:{endpoints}:{json.dumps(payload, sort_keys=True)}"
        )
    for atom_state_edit in reaction.atom_state_edits:
        payload = atom_state_edit.model_dump(
            mode="json",
            exclude={"edit_id", "source_range", "metadata", "atom_map"},
        )
        tokens.append(
            f"atom:{descriptors.get(atom_state_edit.atom_map, 'missing')}:"
            f"{json.dumps(payload, sort_keys=True)}"
        )
    for attachment_edit in reaction.attachment_edits:
        if isinstance(attachment_edit, AttachFragmentEdit):
            if attachment_edit.attachment_kind == "fragment":
                assert attachment_edit.fragment_smiles is not None
                fragment = _canonical_unmapped(attachment_edit.fragment_smiles)
                connections = sorted(
                    (
                        descriptors.get(item.product_atom_map, "missing"),
                        item.order,
                    )
                    for item in attachment_edit.connections
                )
                tokens.append(f"attachment:fragment:{fragment}:{connections}")
            else:
                tokens.append(
                    f"attachment:{attachment_edit.attachment_kind}:"
                    f"{descriptors.get(attachment_edit.target_atom_map or -1, 'missing')}:"
                    f"{attachment_edit.charge_delta}"
                )
        elif isinstance(attachment_edit, DetachFragmentEdit):
            tokens.append(
                "attachment:detach:"
                + ":".join(
                    sorted(
                        descriptors.get(item, "external")
                        for item in attachment_edit.fragment_atom_maps
                    )
                )
            )
    for stereo_edit in reaction.stereo_edits:
        payload = stereo_edit.model_dump(
            mode="json",
            exclude={
                "edit_id",
                "source_range",
                "metadata",
                "atom_map",
                "map_a",
                "map_b",
                "stereo_atom_a",
                "stereo_atom_b",
                "neighbour_maps",
            },
        )
        maps = affected_atom_maps(stereo_edit)
        contexts = sorted(descriptors.get(item, "external") for item in maps)
        tokens.append(
            f"stereo:{stereo_edit.edit_type}:{contexts}:{json.dumps(payload, sort_keys=True)}"
        )
    return tuple(tokens or ("no_declared_edit",))


def edit_signature_fingerprint(reaction: ReactionIRV1) -> Any:
    return _hash_tokens(normalized_edit_tokens(reaction))


def changed_bond_atom_fingerprint(reaction: ReactionIRV1) -> Any:
    """Fingerprint only declared core-bond and atom-state changes."""

    tokens = normalized_edit_tokens(reaction)
    selected = tuple(
        token for token in tokens if token.startswith("core:") or token.startswith("atom:")
    )
    return _hash_tokens(selected or ("no_changed_bond_or_atom",))


def reaction_centre_fingerprint(reaction: ReactionIRV1) -> Any | None:
    centre_maps = {
        atom_map for edit in reaction.core_edits for atom_map in affected_atom_maps(edit)
    }
    if not centre_maps:
        return None
    molecule = _molecule(reaction.product.mapped_smiles)
    mapping = atom_map_index(molecule)
    if not centre_maps <= set(mapping):
        raise ValueError("reaction-centre fingerprint contains dangling atom maps")
    atom_indexes = [mapping[item] for item in sorted(centre_maps)]
    candidate = _clear_maps(molecule)
    generator = rdFingerprintGenerator.GetMorganGenerator(
        radius=MORGAN_RADIUS,
        fpSize=MORGAN_BITS,
        includeChirality=True,
    )
    return generator.GetFingerprint(candidate, fromAtoms=atom_indexes)


def ring_change_fingerprint(reaction: ReactionIRV1) -> Any:
    product = _molecule(reaction.product.mapped_smiles)
    precursor = _molecule(precursor_structures(reaction))
    product_rings = len(Chem.GetSymmSSSR(product))
    precursor_rings = len(Chem.GetSymmSSSR(precursor))
    token = f"rings:{product_rings}:{precursor_rings}:{precursor_rings - product_rings}"
    return _hash_tokens((token,))


def fragmentation_fingerprint(reaction: ReactionIRV1) -> Any:
    product = _molecule(reaction.product.mapped_smiles)
    precursors = _molecule(precursor_structures(reaction))
    tokens = (
        f"product_fragments:{len(Chem.GetMolFrags(product))}",
        f"precursor_fragments:{len(Chem.GetMolFrags(precursors))}",
        f"heavy_atom_delta:{precursors.GetNumHeavyAtoms() - product.GetNumHeavyAtoms()}",
    )
    return _hash_tokens(tokens)


def attachment_fingerprint(reaction: ReactionIRV1) -> Any | None:
    tokens = [
        token for token in normalized_edit_tokens(reaction) if token.startswith("attachment:")
    ]
    return _hash_tokens(tokens) if tokens else None


def stereo_fingerprint(reaction: ReactionIRV1) -> Any | None:
    tokens = [token for token in normalized_edit_tokens(reaction) if token.startswith("stereo:")]
    return _hash_tokens(tokens) if tokens else None


def tanimoto(left: Any, right: Any) -> float:
    return float(DataStructs.TanimotoSimilarity(left, right))


def rdkit_version() -> str:
    return str(rdBase.rdkitVersion)
