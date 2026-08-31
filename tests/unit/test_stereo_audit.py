from __future__ import annotations

from synthaudit.audit import StereoAudit
from synthaudit.schema import (
    InvertTetrahedralStereoEdit,
    MoleculeRecord,
    MoleculeRole,
    ReactionIRV1,
    SetBondStereoEdit,
    SetTetrahedralStereoEdit,
)
from synthaudit.schema.results import CheckStatus


def _status(result: object, check_id: str) -> CheckStatus:
    checks = result.checks  # type: ignore[attr-defined]
    return next(item.status for item in checks if item.check_id == check_id)


def test_stereo_audit_verifies_cip_inversion() -> None:
    reaction = ReactionIRV1(
        reaction_id="invert",
        product=MoleculeRecord(
            mapped_smiles="[F:1][C@:2]([Cl:3])([Br:4])[I:5]",
            role=MoleculeRole.PRODUCT,
        ),
        stereo_edits=(InvertTetrahedralStereoEdit(atom_map=2),),
    )
    result = StereoAudit().run(reaction)
    assert _status(result, "stereo.execution") == CheckStatus.PASS
    assert _status(result, "stereo.cip_intent") == CheckStatus.PASS
    assert _status(result, "stereo.silent_erasure") == CheckStatus.PASS


def test_stereo_audit_sets_absolute_configuration() -> None:
    reaction = ReactionIRV1(
        reaction_id="set-r",
        product=MoleculeRecord(
            mapped_smiles="[F:1][C:2]([Cl:3])([Br:4])[I:5]",
            role=MoleculeRole.PRODUCT,
        ),
        stereo_edits=(SetTetrahedralStereoEdit(atom_map=2, configuration="R"),),
    )
    result = StereoAudit().run(reaction)
    assert _status(result, "stereo.cip_intent") == CheckStatus.PASS
    assert _status(result, "stereo.new_centres") == CheckStatus.PASS


def test_stereo_audit_marks_symmetric_absolute_target_indeterminate() -> None:
    reaction = ReactionIRV1(
        reaction_id="symmetric",
        product=MoleculeRecord(
            mapped_smiles="[C:1]([F:2])([F:3])([Cl:4])[Br:5]",
            role=MoleculeRole.PRODUCT,
        ),
        stereo_edits=(SetTetrahedralStereoEdit(atom_map=1, configuration="R"),),
    )
    result = StereoAudit().run(reaction)
    assert _status(result, "stereo.symmetric_centres") == CheckStatus.INDETERMINATE
    assert _status(result, "stereo.execution") == CheckStatus.FAIL


def test_stereo_audit_validates_ez_neighbours() -> None:
    valid = ReactionIRV1(
        reaction_id="ez",
        product=MoleculeRecord(
            mapped_smiles="[CH3:1][CH:2]=[CH:3][CH3:4]",
            role=MoleculeRole.PRODUCT,
        ),
        stereo_edits=(
            SetBondStereoEdit(
                map_a=2,
                map_b=3,
                stereo="E",
                stereo_atom_a=1,
                stereo_atom_b=4,
            ),
        ),
    )
    assert _status(StereoAudit().run(valid), "stereo.bond_references") == CheckStatus.PASS

    invalid_edit = valid.stereo_edits[0].model_copy(update={"stereo_atom_a": 99})
    invalid = valid.model_copy(update={"stereo_edits": (invalid_edit,)})
    result = StereoAudit().run(invalid)
    assert _status(result, "stereo.bond_references") == CheckStatus.FAIL


def test_stereo_audit_uses_dedicated_cyclic_warning_path() -> None:
    reaction = ReactionIRV1(
        reaction_id="cyclic",
        product=MoleculeRecord(
            mapped_smiles="[C@H:1]1([F:7])[CH2:2][CH2:3][CH2:4][CH2:5][CH2:6]1",
            role=MoleculeRole.PRODUCT,
        ),
        stereo_edits=(InvertTetrahedralStereoEdit(atom_map=1),),
    )
    result = StereoAudit().run(reaction)
    assert _status(result, "stereo.cyclic_path") == CheckStatus.WARNING


def test_stereo_audit_no_edits_is_not_missing_evidence() -> None:
    reaction = ReactionIRV1(
        reaction_id="achiral",
        product=MoleculeRecord(mapped_smiles="[CH4:1]", role=MoleculeRole.PRODUCT),
    )
    result = StereoAudit().run(reaction)
    assert _status(result, "stereo.cip_intent") == CheckStatus.PASS
    assert _status(result, "stereo.symmetric_centres") == CheckStatus.PASS
