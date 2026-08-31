from __future__ import annotations

import pytest

from synthaudit.graph import SemanticHashError, reaction_ir_semantic_hash
from synthaudit.schema import BreakBondEdit, MoleculeRecord, MoleculeRole, ReactionIRV1


def _reaction(
    reaction_id: str,
    product: str,
    precursors: tuple[str, ...],
    edits: tuple[BreakBondEdit, ...],
) -> ReactionIRV1:
    return ReactionIRV1(
        reaction_id=reaction_id,
        product=MoleculeRecord(mapped_smiles=product, role=MoleculeRole.PRODUCT),
        expected_precursors=tuple(
            MoleculeRecord(mapped_smiles=smiles, role=MoleculeRole.PRECURSOR)
            for smiles in precursors
        ),
        core_edits=edits,
    )


def test_hash_ignores_traversal_ids_edit_order_and_precursor_order() -> None:
    left = _reaction(
        "left",
        "[CH3:1][CH2:2][OH:3]",
        ("[CH3:1][CH3:2]", "[OH2:3]"),
        (BreakBondEdit(map_a=2, map_b=3), BreakBondEdit(map_a=1, map_b=2)),
    )
    right = _reaction(
        "right",
        "[OH:3][CH2:2][CH3:1]",
        ("[OH2:3]", "[CH3:1][CH3:2]"),
        (BreakBondEdit(map_a=2, map_b=1), BreakBondEdit(map_a=3, map_b=2)),
    )
    assert reaction_ir_semantic_hash(left) == reaction_ir_semantic_hash(right)


def test_hash_can_use_reconstructed_precursors() -> None:
    reaction = _reaction("r", "[CH3:1][OH:2]", (), (BreakBondEdit(map_a=1, map_b=2),))
    value = reaction_ir_semantic_hash(reaction, ["[OH2:2]", "[CH4:1]"])
    assert len(value) == 64


def test_hash_rejects_invalid_smiles() -> None:
    reaction = _reaction("bad", "not-smiles", (), ())
    with pytest.raises(SemanticHashError):
        reaction_ir_semantic_hash(reaction)
