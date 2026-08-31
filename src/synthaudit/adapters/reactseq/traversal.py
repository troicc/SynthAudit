"""Resolve ReactSeq traversal indexes to stable atom-map identities."""

from __future__ import annotations

from rdkit import Chem

from synthaudit.adapters.reactseq.errors import (
    ReactSeqSyntaxError,
    ReactSeqTraversalIndeterminateError,
)
from synthaudit.adapters.reactseq.models import ReactSeqDocument, ReactSeqTraversalContext
from synthaudit.adapters.reactseq.tokenizer import atom_tokens
from synthaudit.graph.atom_maps import AtomMapError, atom_map_index, parse_mapped_molecule


def _unmapped_copy(molecule: Chem.Mol) -> Chem.Mol:
    copy = Chem.Mol(molecule)
    for atom in copy.GetAtoms():
        atom.SetAtomMapNum(0)
        atom.SetIsotope(0)
    try:
        Chem.SanitizeMol(copy)
    except Exception as exc:
        raise ReactSeqSyntaxError(
            f"product graph cannot be sanitized for traversal matching: {exc}"
        ) from exc
    return copy


def _indexed_graph_equal(left: Chem.Mol, right: Chem.Mol) -> bool:
    if left.GetNumAtoms() != right.GetNumAtoms() or left.GetNumBonds() != right.GetNumBonds():
        return False
    for index in range(left.GetNumAtoms()):
        atom_left = left.GetAtomWithIdx(index)
        atom_right = right.GetAtomWithIdx(index)
        if (
            atom_left.GetAtomicNum(),
            atom_left.GetFormalCharge(),
            atom_left.GetIsAromatic(),
        ) != (
            atom_right.GetAtomicNum(),
            atom_right.GetFormalCharge(),
            atom_right.GetIsAromatic(),
        ):
            return False
    left_bonds = {
        tuple(sorted((bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()))): bond.GetBondTypeAsDouble()
        for bond in left.GetBonds()
    }
    right_bonds = {
        tuple(sorted((bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()))): bond.GetBondTypeAsDouble()
        for bond in right.GetBonds()
    }
    return left_bonds == right_bonds


def build_traversal_context(
    document: ReactSeqDocument,
    mapped_product_smiles: str,
) -> ReactSeqTraversalContext:
    """Map source traversal atoms by indexed identity or a unique graph isomorphism."""
    source_molecule = Chem.MolFromSmiles(document.original_product_smiles)
    if source_molecule is None:
        raise ReactSeqSyntaxError("ReactSeq product traversal is not valid SMILES")
    try:
        mapped_molecule = parse_mapped_molecule(mapped_product_smiles)
    except AtomMapError as exc:
        raise ReactSeqSyntaxError(str(exc)) from exc

    source_unmapped = _unmapped_copy(source_molecule)
    mapped_unmapped = _unmapped_copy(mapped_molecule)
    if _indexed_graph_equal(source_unmapped, mapped_unmapped):
        source_to_mapped = tuple(range(source_molecule.GetNumAtoms()))
        mapping_method = "indexed_source"
    else:
        matches = mapped_unmapped.GetSubstructMatches(
            source_unmapped,
            uniquify=False,
            useChirality=True,
            maxMatches=1001,
        )
        complete_matches = tuple(
            match for match in matches if len(match) == mapped_unmapped.GetNumAtoms()
        )
        unique_matches = tuple(dict.fromkeys(complete_matches))
        if not unique_matches:
            raise ReactSeqSyntaxError(
                "ReactSeq product traversal and supplied mapped product are not isomorphic"
            )
        if len(unique_matches) != 1:
            raise ReactSeqTraversalIndeterminateError(
                "product traversal maps to multiple symmetric atom assignments",
                details={"candidate_mappings": len(unique_matches)},
            )
        source_to_mapped = unique_matches[0]
        mapping_method = "unique_graph_isomorphism"

    product_tokens = atom_tokens(document.original_product_smiles)
    if len(product_tokens) != source_molecule.GetNumAtoms():
        raise ReactSeqSyntaxError("product atom-token count does not match RDKit atom count")
    header_tokens = atom_tokens(document.header, source_offset=document.header_range.start)
    if len(header_tokens) != source_molecule.GetNumAtoms():
        raise ReactSeqSyntaxError(
            "ReactSeq header changes the product atom count; external atoms belong in tails"
        )

    map_to_index = atom_map_index(mapped_molecule)
    index_to_map = {index: atom_map for atom_map, index in map_to_index.items()}
    reactseq_to_rdkit = {
        source_index + 1: mapped_index for source_index, mapped_index in enumerate(source_to_mapped)
    }
    explicit = Chem.MolToSmiles(
        source_unmapped,
        canonical=False,
        allBondsExplicit=True,
        kekuleSmiles=True,
        isomericSmiles=True,
    )
    return ReactSeqTraversalContext(
        original_product_smiles=document.original_product_smiles,
        explicit_bond_product_smiles=explicit,
        atom_token_spans=header_tokens,
        reactseq_atom_index_to_rdkit_index=reactseq_to_rdkit,
        rdkit_index_to_atom_map=index_to_map,
        header_token_spans=tuple(token.source_range for token in header_tokens),
        tail_token_spans=tuple(tail.source_range for tail in document.tails),
        mapping_method=mapping_method,
    )
