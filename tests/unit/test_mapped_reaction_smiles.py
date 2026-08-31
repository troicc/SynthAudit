from __future__ import annotations

import pytest

from synthaudit.adapters.errors import AtomMappingRequired
from synthaudit.adapters.mapped_reaction_smiles import (
    MappedReactionSmilesAdapter,
    MappedReactionSmilesInput,
)
from synthaudit.graph.executor import ReactionExecutor
from synthaudit.schema.edits import DetachFragmentEdit


def test_mapped_reaction_derives_staged_edits_and_reconstructs_precursors() -> None:
    source = "[CH3:1][CH2:2][Br:3].[OH-:4]>>[CH3:1][CH2:2][OH:4]"
    result = MappedReactionSmilesAdapter().normalize(
        MappedReactionSmilesInput(reaction_smiles=source)
    )

    reaction = result.reaction_ir
    assert reaction.core_edits[0].edit_type == "break_bond"
    assert reaction.attachment_edits[0].edit_type == "attach_fragment"
    assert reaction.attachment_edits[0].connections[0].fragment_atom_map == 5
    assert reaction.atom_state_edits[0].property == "formal_charge"
    execution = ReactionExecutor().execute(reaction)
    assert execution.success
    assert execution.mapped_structures == tuple(
        item.mapped_smiles for item in reaction.expected_precursors
    )


@pytest.mark.parametrize(
    "source",
    [
        "CC>>[CH3:1][CH3:2]",
        "[CH3:1][CH3:2]>>CC",
        "[CH3:1]C>>[CH3:1][CH3:2]",
    ],
)
def test_mapping_is_required_and_never_added_silently(source: str) -> None:
    with pytest.raises(AtomMappingRequired):
        MappedReactionSmilesAdapter().normalize(MappedReactionSmilesInput(reaction_smiles=source))


def test_unmapped_left_fragment_and_reagent_field_are_preserved_as_warnings() -> None:
    result = MappedReactionSmilesAdapter().normalize(
        MappedReactionSmilesInput(reaction_smiles="[CH3:1][OH:2].O>CCO>[CH3:1][OH:2]")
    )
    assert {warning.code for warning in result.warnings} == {
        "reagent_field_preserved",
        "unmapped_left_side_reagents",
    }
    assert result.reaction_ir.stage_metadata["unmapped_left_side_reagents"] == ["O"]


def test_missing_product_subgraph_becomes_explicit_detach() -> None:
    reaction = MappedReactionSmilesAdapter().to_reaction_ir(
        MappedReactionSmilesInput(reaction_smiles="[CH3:1][CH3:2]>>[CH3:1][CH2:2][Br:3]")
    )
    assert isinstance(reaction.attachment_edits[0], DetachFragmentEdit)
    assert reaction.attachment_edits[0].fragment_atom_maps == (3,)
    execution = ReactionExecutor().execute(reaction)
    assert execution.success
    assert execution.mapped_structures == ("[CH3:1][CH3:2]",)


def test_bond_order_and_stereo_differences_are_retained() -> None:
    order = MappedReactionSmilesAdapter().to_reaction_ir(
        MappedReactionSmilesInput(reaction_smiles="[CH3:1][CH3:2]>>[CH2:1]=[CH2:2]")
    )
    assert order.core_edits[0].edit_type == "change_bond_order"
    assert order.core_edits[0].to_order == 1.0

    stereo = MappedReactionSmilesAdapter().to_reaction_ir(
        MappedReactionSmilesInput(
            reaction_smiles=("[F:1]/[CH:2]=[CH:3]\\[F:4]>>[F:1]/[CH:2]=[CH:3]/[F:4]")
        )
    )
    assert stereo.stereo_edits
    assert stereo.stereo_edits[0].edit_type == "set_bond_stereo"


def test_external_map_renumbering_is_deterministic_and_disclosed() -> None:
    source = "[CH3:1][I:99].[CH3:2][Br:50]>>[CH3:1][CH3:2]"
    first = MappedReactionSmilesAdapter().normalize(
        MappedReactionSmilesInput(reaction_smiles=source)
    )
    second = MappedReactionSmilesAdapter().normalize(
        MappedReactionSmilesInput(reaction_smiles=source)
    )
    assert first.reaction_ir == second.reaction_ir
    assert first.reaction_ir.stage_metadata["source_external_map_to_fresh_map"] == {
        "50": 3,
        "99": 4,
    }
