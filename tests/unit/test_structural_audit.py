from __future__ import annotations

from synthaudit.adapters.mapped_reaction_smiles import (
    MappedReactionSmilesAdapter,
    MappedReactionSmilesInput,
)
from synthaudit.audit import ReactionAuditor, StructuralAudit
from synthaudit.graph import ReactionExecutor
from synthaudit.schema import (
    AddBondEdit,
    AtomSnapshotV1,
    AttachFragmentEdit,
    BondOrderChangeV1,
    ChangeBondOrderEdit,
    ClearTetrahedralStereoEdit,
    DetachFragmentEdit,
    FragmentConnection,
    InvertTetrahedralStereoEdit,
    MoleculeRecord,
    MoleculeRole,
    ReactionIRV1,
    SetBondStereoEdit,
    SetExplicitHydrogenEdit,
)
from synthaudit.schema.results import CheckStatus


def _reaction() -> ReactionIRV1:
    return MappedReactionSmilesAdapter().to_reaction_ir(
        MappedReactionSmilesInput(
            reaction_smiles="[CH3:1][CH2:2][Br:3].[OH-:4]>>[CH3:1][CH2:2][OH:4]"
        )
    )


def _status(result: object, check_id: str) -> CheckStatus:
    checks = result.checks  # type: ignore[attr-defined]
    return next(item.status for item in checks if item.check_id == check_id)


def test_structural_audit_checks_every_required_invariant() -> None:
    report = ReactionAuditor().audit(_reaction())
    checks = report.structural_audit.checks
    assert len(checks) == 12
    assert len({item.check_id for item in checks}) == 12
    assert _status(report.structural_audit, "structural.map_uniqueness") == CheckStatus.PASS
    assert _status(report.structural_audit, "structural.atom_conservation") == CheckStatus.PASS
    assert (
        _status(report.structural_audit, "structural.unexplained_graph_changes") == CheckStatus.PASS
    )
    assert report.structurally_valid
    assert not report.blocking


def test_structural_audit_retains_invalid_maps_and_empty_fragments() -> None:
    reaction = ReactionIRV1(
        reaction_id="invalid-maps",
        product=MoleculeRecord(mapped_smiles="[CH3:1][OH:1]", role=MoleculeRole.PRODUCT),
        expected_precursors=(MoleculeRecord(mapped_smiles=".", role=MoleculeRole.PRECURSOR),),
        core_edits=(AddBondEdit(map_a=1, map_b=99),),
    )
    report = ReactionAuditor().audit(reaction)
    assert _status(report.structural_audit, "structural.map_uniqueness") == CheckStatus.FAIL
    assert _status(report.structural_audit, "structural.dangling_references") in {
        CheckStatus.FAIL,
        CheckStatus.INDETERMINATE,
    }
    assert _status(report.structural_audit, "structural.empty_fragments") == CheckStatus.FAIL
    assert report.blocking
    assert not report.structurally_valid


def test_structural_audit_flags_disconnected_product_extreme_charge_and_complexity() -> None:
    reaction = ReactionIRV1(
        reaction_id="review-rules",
        product=MoleculeRecord(mapped_smiles="[Fe+4:1].[Cl-:2]", role=MoleculeRole.PRODUCT),
        attachment_edits=tuple(
            AttachFragmentEdit(attachment_kind="null", target_atom_map=1) for _ in range(13)
        ),
    )
    result = StructuralAudit(edit_complexity_warning=12).run(reaction)
    assert _status(result, "structural.formal_charge") == CheckStatus.WARNING
    assert _status(result, "structural.connectivity") == CheckStatus.FAIL
    assert _status(result, "structural.edit_complexity") == CheckStatus.WARNING


def test_structural_audit_detects_noop_stereo_operation() -> None:
    reaction = ReactionIRV1(
        reaction_id="noop",
        product=MoleculeRecord(
            mapped_smiles="[F:1][C:2]([Cl:3])([Br:4])[I:5]",
            role=MoleculeRole.PRODUCT,
        ),
        stereo_edits=(ClearTetrahedralStereoEdit(atom_map=2),),
    )
    result = StructuralAudit().run(reaction)
    assert _status(result, "structural.operation_noops") == CheckStatus.FAIL


def test_structural_audit_rejects_invalid_threshold() -> None:
    try:
        StructuralAudit(edit_complexity_warning=0)
    except ValueError as exc:
        assert "positive" in str(exc)
    else:
        raise AssertionError("invalid threshold was accepted")


def test_structural_atom_accounting_and_diff_detect_injected_unexplained_change() -> None:
    reaction = _reaction()
    execution = ReactionExecutor().execute(reaction)
    assert execution.graph_diff is not None
    injected_diff = execution.graph_diff.model_copy(
        update={
            "added_atoms": (
                *execution.graph_diff.added_atoms,
                AtomSnapshotV1(
                    atom_map=99,
                    atomic_number=6,
                    formal_charge=0,
                    isotope=0,
                    aromatic=False,
                    explicit_hydrogens=0,
                    chiral_tag="CHI_UNSPECIFIED",
                ),
            )
        }
    )
    injected = execution.model_copy(update={"graph_diff": injected_diff})
    audit = StructuralAudit()
    result = audit.run(reaction, injected)
    assert _status(result, "structural.unexplained_graph_changes") == CheckStatus.FAIL

    output = (*execution.mapped_structures, "[CH4:99]")
    injected_atoms = execution.model_copy(update={"mapped_structures": output})
    atom_result = audit.run(reaction, injected_atoms)
    assert _status(atom_result, "structural.atom_conservation") == CheckStatus.FAIL


def test_structural_dangling_paths_cover_fragment_null_detach_and_stereo() -> None:
    valid = AttachFragmentEdit(
        fragment_smiles="[Cl:2]",
        connections=(FragmentConnection(product_atom_map=1, fragment_atom_map=2),),
    )
    invalid_fragment = valid.model_copy(update={"fragment_smiles": "[Cl:2"})
    reaction = ReactionIRV1(
        reaction_id="all-dangling",
        product=MoleculeRecord(mapped_smiles="[CH3:1]", role=MoleculeRole.PRODUCT),
        attachment_edits=(
            invalid_fragment,
            AttachFragmentEdit(attachment_kind="null", target_atom_map=88),
            DetachFragmentEdit(fragment_atom_maps=(77,), attachment_bonds=((1, 77),)),
        ),
        stereo_edits=(InvertTetrahedralStereoEdit(atom_map=66),),
    )
    result = StructuralAudit().run(reaction)
    dangling = next(
        item for item in result.checks if item.check_id == "structural.dangling_references"
    )
    assert dangling.status == CheckStatus.FAIL
    assert set(dangling.affected_atom_maps) == {2, 66, 77, 88}


def test_structural_valence_and_aromatic_checks_retain_rdkit_failure() -> None:
    reaction = ReactionIRV1(
        reaction_id="bad-valence",
        product=MoleculeRecord(mapped_smiles="[CH5:1]", role=MoleculeRole.PRODUCT),
    )
    result = StructuralAudit().run(reaction)
    assert _status(result, "structural.valence") == CheckStatus.FAIL
    assert _status(result, "structural.aromaticity_kekule") == CheckStatus.FAIL


def test_structural_detach_operation_explains_removed_atoms_and_bonds() -> None:
    reaction = ReactionIRV1(
        reaction_id="detach",
        product=MoleculeRecord(mapped_smiles="[CH3:1][Cl:2]", role=MoleculeRole.PRODUCT),
        attachment_edits=(DetachFragmentEdit(fragment_atom_maps=(2,), attachment_bonds=((1, 2),)),),
    )
    result = StructuralAudit().run(reaction)
    assert _status(result, "structural.atom_conservation") == CheckStatus.PASS
    assert _status(result, "structural.unexplained_graph_changes") == CheckStatus.PASS


def test_structural_declared_add_bond_is_explained() -> None:
    reaction = ReactionIRV1(
        reaction_id="add-bond",
        product=MoleculeRecord(mapped_smiles="[CH3:1].[CH3:2]", role=MoleculeRole.PRODUCT),
        core_edits=(AddBondEdit(map_a=1, map_b=2),),
    )
    result = StructuralAudit().run(reaction)
    assert _status(result, "structural.unexplained_graph_changes") == CheckStatus.PASS


def test_structural_declared_atom_and_stereo_changes_are_explained() -> None:
    explicit_h = ReactionIRV1(
        reaction_id="explicit-h",
        product=MoleculeRecord(mapped_smiles="[CH3:1]", role=MoleculeRole.PRODUCT),
        atom_state_edits=(SetExplicitHydrogenEdit(atom_map=1, from_count=3, to_count=4),),
    )
    tetra = ReactionIRV1(
        reaction_id="tetra",
        product=MoleculeRecord(
            mapped_smiles="[F:1][C@:2]([Cl:3])([Br:4])[I:5]",
            role=MoleculeRole.PRODUCT,
        ),
        stereo_edits=(InvertTetrahedralStereoEdit(atom_map=2),),
    )
    ez = ReactionIRV1(
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
    for reaction in (explicit_h, tetra, ez):
        result = StructuralAudit().run(reaction)
        assert _status(result, "structural.unexplained_graph_changes") == CheckStatus.PASS


def test_structural_invalid_success_payload_fails_atom_conservation_parsing() -> None:
    reaction = _reaction()
    execution = ReactionExecutor().execute(reaction)
    invalid_output = execution.model_copy(update={"mapped_structures": ("[C:1",)})
    result = StructuralAudit().run(reaction, invalid_output)
    assert _status(result, "structural.atom_conservation") == CheckStatus.FAIL


def test_structural_change_order_declaration_is_accounted_when_diff_is_available() -> None:
    base = _reaction()
    execution = ReactionExecutor().execute(base)
    reaction = ReactionIRV1(
        reaction_id="change-order-declaration",
        product=MoleculeRecord(mapped_smiles="[CH2:1]=[CH2:2]", role=MoleculeRole.PRODUCT),
        core_edits=(ChangeBondOrderEdit(map_a=1, map_b=2, from_order=2.0, to_order=1.0),),
    )
    assert execution.graph_diff is not None
    changed = execution.graph_diff.model_copy(
        update={
            "added_atoms": (),
            "removed_atoms": (),
            "added_bonds": (),
            "removed_bonds": (),
            "changed_atom_properties": (),
            "changed_bond_orders": (BondOrderChangeV1(map_a=1, map_b=2, before=2.0, after=1.0),),
            "changed_tetrahedral_stereo": (),
            "changed_bond_stereo": (),
        }
    )
    synthetic = execution.model_copy(update={"graph_diff": changed})
    check_result = StructuralAudit()._unexplained_changes(reaction, synthetic)
    assert check_result.status == CheckStatus.PASS
