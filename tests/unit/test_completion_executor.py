from __future__ import annotations

import pytest

from synthaudit.graph import AttachmentCompletionExecutor, SanitationMode
from synthaudit.schema import (
    AttachFragmentEdit,
    DetachFragmentEdit,
    FragmentConnection,
    SetAtomStateEdit,
    SetExplicitHydrogenEdit,
)


def test_single_fragment_attachment_and_fresh_map_policy() -> None:
    edit = AttachFragmentEdit(
        fragment_smiles="[Cl:2]",
        connections=(FragmentConnection(product_atom_map=1, fragment_atom_map=2),),
    )
    result = AttachmentCompletionExecutor().execute("[CH3:1]", (edit,))
    assert result.success
    assert result.mapped_structures == ("[CH3:1][Cl:2]",)
    assert result.graph_diff is not None
    assert result.graph_diff.added_atoms[0].atom_map == 2

    nonsequential = edit.model_copy(update={"fragment_smiles": "[Cl:7]"})
    failed = AttachmentCompletionExecutor().execute("[CH3:1]", (nonsequential,))
    assert not failed.success
    assert failed.error is not None
    assert "fresh sequential" in failed.error.message


def test_multi_attachment_fragment_connects_two_sites() -> None:
    result = AttachmentCompletionExecutor().execute(
        ("[CH2:1][CH3:3]", "[CH2:2][CH3:4]"),
        (
            AttachFragmentEdit(
                fragment_smiles="[O:5]",
                connections=(
                    FragmentConnection(product_atom_map=1, fragment_atom_map=5),
                    FragmentConnection(product_atom_map=2, fragment_atom_map=5),
                ),
            ),
        ),
    )
    assert result.success
    assert len(result.mapped_structures) == 1
    assert result.graph_diff is not None
    assert len(result.graph_diff.added_bonds) == 2


def test_null_charge_only_and_atom_state_completion_are_distinct() -> None:
    null = AttachmentCompletionExecutor().execute(
        "[CH4:1]",
        (AttachFragmentEdit(attachment_kind="null", target_atom_map=1),),
    )
    charged = AttachmentCompletionExecutor().execute(
        "[NH3:1]",
        (AttachFragmentEdit(attachment_kind="charge_only", target_atom_map=1, charge_delta=1),),
    )
    state = AttachmentCompletionExecutor().execute(
        "[13CH3:1]",
        (),
        (
            SetAtomStateEdit(atom_map=1, property="isotope", from_value=13, to_value=12),
            SetExplicitHydrogenEdit(atom_map=1, from_count=3, to_count=4),
        ),
    )
    assert null.success and null.graph_diff is not None
    assert null.graph_diff.added_atoms == ()
    assert charged.success and charged.mapped_structures == ("[NH3+:1]",)
    assert state.success and state.graph_diff is not None
    changed = {item.property for item in state.graph_diff.changed_atom_properties}
    assert changed == {"explicit_hydrogens", "isotope"}


def test_detach_fragment_removes_declared_atoms() -> None:
    result = AttachmentCompletionExecutor().execute(
        "[CH3:1][Cl:2]",
        (DetachFragmentEdit(fragment_atom_maps=(2,), attachment_bonds=((1, 2),)),),
    )
    assert result.success
    assert result.mapped_structures == ("[CH3:1]",)
    assert result.graph_diff is not None
    assert result.graph_diff.removed_atoms[0].atom_map == 2


def test_completion_rolls_back_and_exposes_partial_diagnostic() -> None:
    result = AttachmentCompletionExecutor().execute(
        "[CH3:1]",
        (
            AttachFragmentEdit(
                fragment_smiles="[Cl:2]",
                connections=(FragmentConnection(product_atom_map=1, fragment_atom_map=2),),
            ),
            AttachFragmentEdit(
                fragment_smiles="[Br:3]",
                connections=(FragmentConnection(product_atom_map=99, fragment_atom_map=3),),
            ),
        ),
    )
    assert not result.success
    assert result.mapped_structures == ("[CH3:1]",)
    assert result.diagnostic_mapped_structures == ("[CH3:1][Cl:2]",)
    assert result.error is not None and result.error.operation_index == 1


def test_completion_rejects_invalid_input_maps_and_sanitation() -> None:
    unmapped = AttachmentCompletionExecutor().execute("C", ())
    invalid = AttachmentCompletionExecutor().execute("[CH5:1]", ())
    diagnostic = AttachmentCompletionExecutor().execute(
        "[CH5:1]", (), mode=SanitationMode.DIAGNOSTIC
    )
    assert not unmapped.success and unmapped.error is not None
    assert unmapped.error.error_type == "AtomMapError"
    assert not invalid.success and invalid.error is not None
    assert invalid.error.error_type == "InputSanitationError"
    assert not diagnostic.success and diagnostic.warnings


@pytest.mark.parametrize(
    "edit",
    [
        SetExplicitHydrogenEdit(atom_map=99, to_count=1),
        SetExplicitHydrogenEdit(atom_map=1, from_count=2, to_count=4),
        SetExplicitHydrogenEdit(atom_map=1, to_count=3),
        SetAtomStateEdit(atom_map=1, property="formal_charge", from_value=1, to_value=-1),
        SetAtomStateEdit(atom_map=1, property="formal_charge", to_value=0),
        SetAtomStateEdit(atom_map=1, property="atomic_number", to_value=0),
    ],
)
def test_atom_state_errors_report_the_operation(edit: object) -> None:
    result = AttachmentCompletionExecutor().execute(
        "[CH3:1]",
        (),
        (edit,),  # type: ignore[arg-type]
    )
    assert not result.success
    assert result.error is not None and result.error.operation_index == 0


def test_supported_atom_state_setters_are_applied() -> None:
    charge = AttachmentCompletionExecutor().execute(
        "[NH3+:1]",
        (),
        (SetAtomStateEdit(atom_map=1, property="formal_charge", from_value=1, to_value=0),),
    )
    element = AttachmentCompletionExecutor().execute(
        "[CH3:1]",
        (),
        (SetAtomStateEdit(atom_map=1, property="atomic_number", from_value=6, to_value=7),),
    )
    aromatic = AttachmentCompletionExecutor().execute(
        "[CH:1]1=[CH:2][CH:3]=[CH:4][CH:5]=[CH:6]1",
        (),
        (SetAtomStateEdit(atom_map=1, property="aromatic", to_value=True),),
    )
    assert charge.success
    assert element.success and "N" in element.mapped_structures[0]
    assert not aromatic.success  # one atom alone cannot form a consistent aromatic system


def test_null_and_charge_completion_validate_target_maps() -> None:
    null = AttachmentCompletionExecutor().execute(
        "[CH4:1]", (AttachFragmentEdit(attachment_kind="null", target_atom_map=99),)
    )
    charge = AttachmentCompletionExecutor().execute(
        "[NH3:1]",
        (AttachFragmentEdit(attachment_kind="charge_only", target_atom_map=99, charge_delta=1),),
    )
    assert not null.success and null.error is not None
    assert not charge.success and charge.error is not None


@pytest.mark.parametrize(
    ("fragment", "connections", "message"),
    [
        ("[Cl:1]", ((1, 1),), "reuses"),
        ("[Cl:2].[Br:3]", ((1, 99),), "not in the fragment"),
        ("[Cl:2]", ((99, 2),), "not in the synthon"),
        ("[Cl:2]", ((1, 2), (1, 2)), "duplicate fragment connection"),
    ],
)
def test_fragment_attachment_ambiguities_are_rejected(
    fragment: str, connections: tuple[tuple[int, int], ...], message: str
) -> None:
    edit = AttachFragmentEdit(
        fragment_smiles=fragment,
        connections=tuple(
            FragmentConnection(product_atom_map=map_a, fragment_atom_map=map_b)
            for map_a, map_b in connections
        ),
    )
    result = AttachmentCompletionExecutor().execute("[CH3:1]", (edit,))
    assert not result.success and result.error is not None
    assert message in result.error.message


def test_invalid_fragment_and_final_valence_keep_diagnostics() -> None:
    invalid_fragment = AttachmentCompletionExecutor().execute(
        "[CH3:1]",
        (
            AttachFragmentEdit(
                fragment_smiles="[CH5:2]",
                connections=(FragmentConnection(product_atom_map=1, fragment_atom_map=2),),
            ),
        ),
    )
    excessive_valence = AttachmentCompletionExecutor().execute(
        "[CH3:1]",
        (
            AttachFragmentEdit(
                fragment_smiles="[Cl:2].[Br:3]",
                connections=(
                    FragmentConnection(product_atom_map=1, fragment_atom_map=2),
                    FragmentConnection(product_atom_map=1, fragment_atom_map=3),
                ),
            ),
        ),
    )
    assert not invalid_fragment.success and invalid_fragment.error is not None
    assert not excessive_valence.success and excessive_valence.error is not None
    assert excessive_valence.error.error_type == "SanitationError"


@pytest.mark.parametrize(
    "edit",
    [
        DetachFragmentEdit(fragment_atom_maps=(2,), attachment_bonds=((1, 99),)),
        DetachFragmentEdit(fragment_atom_maps=(2,), attachment_bonds=((1, 2),)),
        DetachFragmentEdit(fragment_atom_maps=(99,), attachment_bonds=((1, 2),)),
    ],
)
def test_detach_errors_are_structured(edit: DetachFragmentEdit) -> None:
    source = "[CH3:1].[Cl:2]" if edit.attachment_bonds == ((1, 2),) else "[CH3:1][Cl:2]"
    result = AttachmentCompletionExecutor().execute(source, (edit,))
    assert not result.success and result.error is not None
