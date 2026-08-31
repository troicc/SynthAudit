from __future__ import annotations

from synthaudit.adapters.mapped_reaction_smiles import (
    MappedReactionSmilesAdapter,
    MappedReactionSmilesInput,
)
from synthaudit.audit import ReactionCentreAudit
from synthaudit.schema import (
    AddBondEdit,
    BreakBondEdit,
    MoleculeRecord,
    MoleculeRole,
    ReactionIRV1,
)
from synthaudit.schema.results import CheckStatus


def _status(result: object, check_id: str) -> CheckStatus:
    checks = result.checks  # type: ignore[attr-defined]
    return next(item.status for item in checks if item.check_id == check_id)


def test_reaction_centre_matches_expected_precursor_graph_diff() -> None:
    reaction = MappedReactionSmilesAdapter().to_reaction_ir(
        MappedReactionSmilesInput(
            reaction_smiles="[CH3:1][CH2:2][Br:3].[OH-:4]>>[CH3:1][CH2:2][OH:4]"
        )
    )
    result = ReactionCentreAudit().run(reaction)
    assert result.status == CheckStatus.PASS
    assert _status(result, "reaction_centre.explained_graph_diff") == CheckStatus.PASS
    assert _status(result, "reaction_centre.expected_precursor_reconstruction") == CheckStatus.PASS


def test_reaction_centre_reports_dangling_and_wrong_bond_state() -> None:
    reaction = ReactionIRV1(
        reaction_id="bad-centre",
        product=MoleculeRecord(mapped_smiles="[CH3:1][CH3:2]", role=MoleculeRole.PRODUCT),
        core_edits=(
            BreakBondEdit(map_a=1, map_b=2, expected_order=2.0),
            AddBondEdit(map_a=1, map_b=99),
        ),
    )
    result = ReactionCentreAudit().run(reaction)
    assert _status(result, "reaction_centre.referenced_atoms") == CheckStatus.FAIL
    assert _status(result, "reaction_centre.declared_bond_state") == CheckStatus.FAIL
    assert _status(result, "reaction_centre.core_execution") == CheckStatus.FAIL


def test_reaction_centre_marks_symmetric_site_and_missing_expected_set() -> None:
    reaction = ReactionIRV1(
        reaction_id="symmetric",
        product=MoleculeRecord(mapped_smiles="[CH3:1][CH3:2]", role=MoleculeRole.PRODUCT),
        core_edits=(BreakBondEdit(map_a=1, map_b=2),),
    )
    result = ReactionCentreAudit().run(reaction)
    assert _status(result, "reaction_centre.alternative_site_ambiguity") == CheckStatus.WARNING
    assert (
        _status(result, "reaction_centre.expected_precursor_reconstruction")
        == CheckStatus.UNAVAILABLE
    )


def test_reaction_centre_ring_opening_is_explained() -> None:
    reaction = ReactionIRV1(
        reaction_id="ring-open",
        product=MoleculeRecord(mapped_smiles="[CH2:1]1[CH2:2][CH2:3]1", role=MoleculeRole.PRODUCT),
        core_edits=(BreakBondEdit(map_a=1, map_b=2),),
    )
    result = ReactionCentreAudit().run(reaction)
    assert _status(result, "reaction_centre.ring_change") == CheckStatus.PASS


def test_reaction_centre_detects_expected_precursor_mismatch() -> None:
    reaction = ReactionIRV1(
        reaction_id="mismatch",
        product=MoleculeRecord(mapped_smiles="[CH3:1][CH3:2]", role=MoleculeRole.PRODUCT),
        expected_precursors=(
            MoleculeRecord(mapped_smiles="[CH3:1].[CH3:2]", role=MoleculeRole.PRECURSOR),
        ),
    )
    result = ReactionCentreAudit().run(reaction)
    assert _status(result, "reaction_centre.expected_precursor_reconstruction") == CheckStatus.FAIL
