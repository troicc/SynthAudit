from __future__ import annotations

from synthaudit.adapters.mapped_reaction_smiles import (
    MappedReactionSmilesAdapter,
    MappedReactionSmilesInput,
)
from synthaudit.audit import SynthonCompletionAudit
from synthaudit.schema import (
    AttachFragmentEdit,
    FragmentConnection,
    MoleculeRecord,
    MoleculeRole,
    ReactionIRV1,
)
from synthaudit.schema.results import CheckStatus


def _status(result: object, check_id: str) -> CheckStatus:
    checks = result.checks  # type: ignore[attr-defined]
    return next(item.status for item in checks if item.check_id == check_id)


def test_completion_audit_reconstructs_expected_precursors() -> None:
    reaction = MappedReactionSmilesAdapter().to_reaction_ir(
        MappedReactionSmilesInput(
            reaction_smiles="[CH3:1][CH2:2][Br:3].[OH-:4]>>[CH3:1][CH2:2][OH:4]"
        )
    )
    result = SynthonCompletionAudit().run(reaction)
    assert _status(result, "completion.execution") == CheckStatus.PASS
    assert _status(result, "completion.expected_precursor_reconstruction") == CheckStatus.PASS
    assert _status(result, "completion.leaving_group_review") == CheckStatus.UNAVAILABLE


def test_completion_audit_reports_missing_attachment_and_duplicate_pair() -> None:
    edit = AttachFragmentEdit(
        fragment_smiles="[Cl:2]",
        connections=(
            FragmentConnection(product_atom_map=99, fragment_atom_map=2),
            FragmentConnection(product_atom_map=99, fragment_atom_map=2),
        ),
    )
    reaction = ReactionIRV1(
        reaction_id="bad-completion",
        product=MoleculeRecord(mapped_smiles="[CH3:1]", role=MoleculeRole.PRODUCT),
        attachment_edits=(edit,),
    )
    result = SynthonCompletionAudit().run(reaction)
    assert _status(result, "completion.attachment_points") == CheckStatus.FAIL
    assert _status(result, "completion.attachment_identity") == CheckStatus.FAIL
    assert _status(result, "completion.execution") == CheckStatus.FAIL
    assert _status(result, "completion.charge_valence") == CheckStatus.FAIL


def test_completion_audit_handles_invalid_fragment_without_guessing() -> None:
    valid = AttachFragmentEdit(
        fragment_smiles="[Cl:2]",
        connections=(FragmentConnection(product_atom_map=1, fragment_atom_map=2),),
    )
    invalid = valid.model_copy(update={"fragment_smiles": "[Cl:2"})
    reaction = ReactionIRV1(
        reaction_id="invalid-fragment",
        product=MoleculeRecord(mapped_smiles="[CH3:1]", role=MoleculeRole.PRODUCT),
        attachment_edits=(invalid,),
    )
    result = SynthonCompletionAudit().run(reaction)
    assert _status(result, "completion.fragment_parsing") == CheckStatus.FAIL
    assert _status(result, "completion.execution") == CheckStatus.FAIL


def test_completion_audit_records_explicit_multi_attachment() -> None:
    reaction = ReactionIRV1(
        reaction_id="multi",
        product=MoleculeRecord(
            mapped_smiles="[CH2:1][CH3:3].[CH2:2][CH3:4]",
            role=MoleculeRole.PRODUCT,
        ),
        attachment_edits=(
            AttachFragmentEdit(
                fragment_smiles="[O:5]",
                connections=(
                    FragmentConnection(product_atom_map=1, fragment_atom_map=5),
                    FragmentConnection(product_atom_map=2, fragment_atom_map=5),
                ),
            ),
        ),
    )
    result = SynthonCompletionAudit().run(reaction)
    identity = next(
        item for item in result.checks if item.check_id == "completion.attachment_identity"
    )
    assert identity.status == CheckStatus.PASS
    assert identity.evidence["explicit_multi_attached_fragment_maps"] == [5]


def test_completion_audit_flags_unusual_fragment_for_review() -> None:
    reaction = ReactionIRV1(
        reaction_id="unusual",
        product=MoleculeRecord(mapped_smiles="[CH3:1]", role=MoleculeRole.PRODUCT),
        attachment_edits=(
            AttachFragmentEdit(
                fragment_smiles="[Fe:2]",
                connections=(FragmentConnection(product_atom_map=1, fragment_atom_map=2),),
            ),
        ),
    )
    result = SynthonCompletionAudit().run(reaction)
    assert _status(result, "completion.leaving_group_review") == CheckStatus.WARNING


def test_completion_audit_no_fragments_and_no_expected_set_are_explicit() -> None:
    reaction = ReactionIRV1(
        reaction_id="none",
        product=MoleculeRecord(mapped_smiles="[CH4:1]", role=MoleculeRole.PRODUCT),
    )
    result = SynthonCompletionAudit().run(reaction)
    assert _status(result, "completion.leaving_group_review") == CheckStatus.PASS
    assert (
        _status(result, "completion.expected_precursor_reconstruction") == CheckStatus.UNAVAILABLE
    )
