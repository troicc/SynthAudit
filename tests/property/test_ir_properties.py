from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from synthaudit.graph import reaction_ir_semantic_hash
from synthaudit.schema import (
    ChangeBondOrderEdit,
    MoleculeRecord,
    MoleculeRole,
    ReactionIRV1,
)


@given(
    reaction_id=st.text(min_size=1).filter(lambda value: value.strip() != ""),
    from_order=st.sampled_from([1.0, 2.0, 3.0]),
    to_order=st.sampled_from([1.0, 2.0, 3.0]),
)
def test_serialization_round_trip_is_deterministic(
    reaction_id: str, from_order: float, to_order: float
) -> None:
    if from_order == to_order:
        return
    reaction = ReactionIRV1(
        reaction_id=reaction_id,
        product=MoleculeRecord(mapped_smiles="[CH2:1]=[CH2:2]", role=MoleculeRole.PRODUCT),
        core_edits=(
            ChangeBondOrderEdit(map_a=1, map_b=2, from_order=from_order, to_order=to_order),
        ),
    )
    encoded = reaction.model_dump_json()
    assert ReactionIRV1.model_validate_json(encoded).model_dump_json() == encoded


@given(reverse=st.booleans())
def test_precursor_order_does_not_change_semantic_hash(reverse: bool) -> None:
    precursors = ["[CH4:1]", "[OH2:2]"]
    if reverse:
        precursors.reverse()
    reaction = ReactionIRV1(
        reaction_id="order",
        product=MoleculeRecord(mapped_smiles="[CH3:1][OH:2]", role=MoleculeRole.PRODUCT),
        expected_precursors=tuple(
            MoleculeRecord(mapped_smiles=item, role=MoleculeRole.PRECURSOR) for item in precursors
        ),
    )
    expected = ReactionIRV1(
        reaction_id="expected",
        product=MoleculeRecord(mapped_smiles="[CH3:1][OH:2]", role=MoleculeRole.PRODUCT),
        expected_precursors=tuple(
            MoleculeRecord(mapped_smiles=item, role=MoleculeRole.PRECURSOR)
            for item in reversed(precursors)
        ),
    )
    assert reaction_ir_semantic_hash(reaction) == reaction_ir_semantic_hash(expected)
