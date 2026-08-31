from __future__ import annotations

import pytest
from pydantic import ValidationError

from synthaudit.schema import (
    AddBondEdit,
    AttachFragmentEdit,
    BreakBondEdit,
    ChangeBondOrderEdit,
    ClearBondStereoEdit,
    ClearTetrahedralStereoEdit,
    DetachFragmentEdit,
    FragmentConnection,
    InvertTetrahedralStereoEdit,
    MoleculeRecord,
    MoleculeRole,
    ReactionIRV1,
    SetAtomStateEdit,
    SetBondStereoEdit,
    SetExplicitHydrogenEdit,
    SetTetrahedralStereoEdit,
)


def _reaction_with_every_edit() -> ReactionIRV1:
    return ReactionIRV1(
        reaction_id="all-edits",
        product=MoleculeRecord(mapped_smiles="[CH3:1][CH2:2][OH:3]", role=MoleculeRole.PRODUCT),
        expected_precursors=(
            MoleculeRecord(mapped_smiles="[CH3:1][CH3:2].[OH2:3]", role=MoleculeRole.PRECURSOR),
        ),
        core_edits=(
            BreakBondEdit(edit_id="break", map_a=2, map_b=3, expected_order=1),
            AddBondEdit(edit_id="add", map_a=1, map_b=3, order=1),
            ChangeBondOrderEdit(edit_id="order", map_a=1, map_b=2, from_order=1, to_order=2),
        ),
        attachment_edits=(
            AttachFragmentEdit(
                edit_id="attach",
                fragment_smiles="[Cl:4]",
                connections=(FragmentConnection(product_atom_map=2, fragment_atom_map=4),),
            ),
            AttachFragmentEdit(edit_id="null", attachment_kind="null", target_atom_map=3),
            AttachFragmentEdit(
                edit_id="charge",
                attachment_kind="charge_only",
                target_atom_map=3,
                charge_delta=-1,
            ),
            DetachFragmentEdit(
                edit_id="detach", fragment_atom_maps=(4,), attachment_bonds=((2, 4),)
            ),
        ),
        atom_state_edits=(
            SetAtomStateEdit(
                edit_id="state",
                atom_map=3,
                property="formal_charge",
                from_value=0,
                to_value=-1,
            ),
            SetExplicitHydrogenEdit(edit_id="hydrogen", atom_map=3, from_count=1, to_count=0),
        ),
        stereo_edits=(
            SetTetrahedralStereoEdit(edit_id="set-tetra", atom_map=2, configuration="R"),
            InvertTetrahedralStereoEdit(edit_id="invert", atom_map=2),
            ClearTetrahedralStereoEdit(edit_id="clear-tetra", atom_map=2),
            SetBondStereoEdit(edit_id="set-bond", map_a=1, map_b=2, stereo="E"),
            ClearBondStereoEdit(edit_id="clear-bond", map_a=1, map_b=2),
        ),
    )


def test_every_edit_type_round_trips_through_discriminated_unions() -> None:
    reaction = _reaction_with_every_edit()
    restored = ReactionIRV1.model_validate_json(reaction.model_dump_json())
    assert restored == reaction
    assert restored.edit_count == 14
    assert isinstance(restored.attachment_edits[0], AttachFragmentEdit)


@pytest.mark.parametrize(
    "edit",
    [
        lambda: BreakBondEdit(map_a=1, map_b=1),
        lambda: ChangeBondOrderEdit(map_a=1, map_b=2, from_order=1, to_order=1),
        lambda: AttachFragmentEdit(attachment_kind="fragment", fragment_smiles="[Cl:4]"),
        lambda: AttachFragmentEdit(attachment_kind="null"),
        lambda: AttachFragmentEdit(
            attachment_kind="charge_only", target_atom_map=1, charge_delta=0
        ),
        lambda: SetAtomStateEdit(atom_map=1, property="aromatic", to_value=1),
    ],
)
def test_invalid_edits_fail_closed(edit: object) -> None:
    with pytest.raises(ValidationError):
        edit()  # type: ignore[operator]


def test_reaction_rejects_duplicate_edit_ids() -> None:
    with pytest.raises(ValidationError, match="edit_id values must be unique"):
        ReactionIRV1(
            reaction_id="duplicate",
            product=MoleculeRecord(mapped_smiles="[CH3:1][OH:2]", role=MoleculeRole.PRODUCT),
            core_edits=(BreakBondEdit(edit_id="same", map_a=1, map_b=2),),
            stereo_edits=(ClearBondStereoEdit(edit_id="same", map_a=1, map_b=2),),
        )
