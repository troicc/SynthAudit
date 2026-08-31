from __future__ import annotations

from synthaudit.graph import ReactionExecutor
from synthaudit.schema import (
    AttachFragmentEdit,
    BreakBondEdit,
    FragmentConnection,
    MoleculeRecord,
    MoleculeRole,
    ReactionIRV1,
)


def test_full_execution_preserves_stage_separation() -> None:
    reaction = ReactionIRV1(
        reaction_id="full",
        product=MoleculeRecord(mapped_smiles="[CH3:1][CH2:2][OH:3]", role=MoleculeRole.PRODUCT),
        core_edits=(BreakBondEdit(map_a=2, map_b=3),),
        attachment_edits=(
            AttachFragmentEdit(
                fragment_smiles="[Br:4]",
                connections=(FragmentConnection(product_atom_map=2, fragment_atom_map=4),),
            ),
        ),
    )
    result = ReactionExecutor().execute(reaction)
    assert result.success
    assert result.core_result.mapped_structures == ("[CH3:1][CH2:2]", "[OH:3]")
    assert result.completion_result is not None
    assert result.completion_result.mapped_structures == (
        "[CH3:1][CH2:2][Br:4]",
        "[OH:3]",
    )
    assert result.stereo_result is not None and result.stereo_result.success
    assert result.graph_diff is not None
    assert [item.atom_map for item in result.graph_diff.added_atoms] == [4]


def test_full_execution_stops_after_core_failure() -> None:
    reaction = ReactionIRV1(
        reaction_id="failure",
        product=MoleculeRecord(mapped_smiles="[CH3:1][OH:2]", role=MoleculeRole.PRODUCT),
        core_edits=(BreakBondEdit(map_a=1, map_b=99),),
    )
    result = ReactionExecutor().execute(reaction)
    assert not result.success
    assert result.completion_result is None
    assert result.stereo_result is None
    assert result.mapped_structures == (reaction.product.mapped_smiles,)


def test_full_execution_rolls_back_completion_failure() -> None:
    reaction = ReactionIRV1(
        reaction_id="completion-failure",
        product=MoleculeRecord(mapped_smiles="[CH3:1]", role=MoleculeRole.PRODUCT),
        attachment_edits=(
            AttachFragmentEdit(
                fragment_smiles="[Cl:2]",
                connections=(FragmentConnection(product_atom_map=99, fragment_atom_map=2),),
            ),
        ),
    )
    result = ReactionExecutor().execute(reaction)
    assert not result.success
    assert result.completion_result is not None
    assert result.stereo_result is None
    assert result.mapped_structures == ("[CH3:1]",)
