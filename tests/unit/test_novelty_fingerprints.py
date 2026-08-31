from __future__ import annotations

from synthaudit.adapters.mapped_reaction_smiles import (
    MappedReactionSmilesAdapter,
    MappedReactionSmilesInput,
)
from synthaudit.novelty.fingerprints import (
    attachment_fingerprint,
    changed_bond_atom_fingerprint,
    edit_signature_fingerprint,
    fragmentation_fingerprint,
    morgan_fingerprint,
    normalized_edit_tokens,
    precursor_structures,
    reaction_centre_fingerprint,
    reaction_difference_fingerprint,
    ring_change_fingerprint,
    scaffold_fingerprint,
    stereo_fingerprint,
    tanimoto,
)
from synthaudit.schema import (
    InvertTetrahedralStereoEdit,
    MoleculeRecord,
    MoleculeRole,
    ReactionIRV1,
)


def _substitution(maps: tuple[int, int, int, int] = (1, 2, 3, 4)) -> ReactionIRV1:
    carbon, methylene, bromine, oxygen = maps
    return MappedReactionSmilesAdapter().to_reaction_ir(
        MappedReactionSmilesInput(
            reaction_smiles=(
                f"[CH3:{carbon}][CH2:{methylene}][Br:{bromine}].[OH-:{oxygen}]>>"
                f"[CH3:{carbon}][CH2:{methylene}][OH:{oxygen}]"
            )
        )
    )


def test_molecular_and_reaction_fingerprints_are_deterministic() -> None:
    reaction = _substitution()
    assert (
        tanimoto(
            morgan_fingerprint(reaction.product.mapped_smiles),
            morgan_fingerprint(reaction.product.mapped_smiles),
        )
        == 1.0
    )
    assert (
        tanimoto(
            reaction_difference_fingerprint(reaction),
            reaction_difference_fingerprint(reaction),
        )
        == 1.0
    )
    assert (
        tanimoto(
            changed_bond_atom_fingerprint(reaction),
            changed_bond_atom_fingerprint(reaction),
        )
        == 1.0
    )
    assert tanimoto(fragmentation_fingerprint(reaction), fragmentation_fingerprint(reaction)) == 1.0
    assert tanimoto(ring_change_fingerprint(reaction), ring_change_fingerprint(reaction)) == 1.0
    assert precursor_structures(reaction) == tuple(
        item.mapped_smiles for item in reaction.expected_precursors
    )


def test_edit_semantic_fingerprint_is_invariant_to_pure_map_renumbering() -> None:
    left = _substitution()
    right = _substitution((11, 12, 13, 14))
    assert tanimoto(edit_signature_fingerprint(left), edit_signature_fingerprint(right)) == 1.0
    assert normalized_edit_tokens(left) == normalized_edit_tokens(right)
    left_centre = reaction_centre_fingerprint(left)
    right_centre = reaction_centre_fingerprint(right)
    assert left_centre is not None and right_centre is not None
    assert tanimoto(left_centre, right_centre) == 1.0
    left_attachment = attachment_fingerprint(left)
    right_attachment = attachment_fingerprint(right)
    assert left_attachment is not None and right_attachment is not None
    assert tanimoto(left_attachment, right_attachment) == 1.0


def test_scaffold_and_optional_stage_fingerprints_are_explicit() -> None:
    assert scaffold_fingerprint("[CH3:1][CH2:2][OH:3]") is None
    aromatic = scaffold_fingerprint("[cH:1]1[cH:2][cH:3][cH:4][cH:5][cH:6]1")
    assert aromatic is not None

    reaction = ReactionIRV1(
        reaction_id="no-edits",
        product=MoleculeRecord(mapped_smiles="[CH4:1]", role=MoleculeRole.PRODUCT),
    )
    assert reaction_centre_fingerprint(reaction) is None
    assert attachment_fingerprint(reaction) is None
    assert stereo_fingerprint(reaction) is None
    assert normalized_edit_tokens(reaction) == ("no_declared_edit",)


def test_stereo_fingerprint_is_separate_from_other_edit_views() -> None:
    reaction = ReactionIRV1(
        reaction_id="stereo",
        product=MoleculeRecord(
            mapped_smiles="[F:1][C@:2]([Cl:3])([Br:4])[I:5]",
            role=MoleculeRole.PRODUCT,
        ),
        stereo_edits=(InvertTetrahedralStereoEdit(atom_map=2),),
    )
    assert stereo_fingerprint(reaction) is not None
    assert attachment_fingerprint(reaction) is None
