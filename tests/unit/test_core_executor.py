from __future__ import annotations

import pytest

from synthaudit.graph import CoreGraphExecutor, SanitationMode
from synthaudit.schema import AddBondEdit, BreakBondEdit, ChangeBondOrderEdit


def test_break_bond_produces_synthons_and_graph_diff() -> None:
    result = CoreGraphExecutor().execute("[CH3:1][CH2:2][OH:3]", (BreakBondEdit(map_a=2, map_b=3),))
    assert result.success
    assert result.structurally_valid
    assert len(result.mapped_structures) == 2
    assert result.graph_diff is not None
    assert [(bond.map_a, bond.map_b) for bond in result.graph_diff.removed_bonds] == [(2, 3)]
    assert result.graph_diff.precursor_fragment_count_after == 2


def test_add_and_change_bond_order() -> None:
    added = CoreGraphExecutor().execute("[CH3:1].[CH3:2]", (AddBondEdit(map_a=1, map_b=2),))
    changed = CoreGraphExecutor().execute(
        "[CH2:1]=[CH2:2]",
        (ChangeBondOrderEdit(map_a=1, map_b=2, from_order=2, to_order=1),),
    )
    assert added.success and added.graph_diff is not None
    assert len(added.graph_diff.added_bonds) == 1
    assert changed.success and changed.graph_diff is not None
    assert changed.graph_diff.changed_bond_orders[0].before == 2
    assert changed.graph_diff.changed_bond_orders[0].after == 1


def test_transaction_rolls_back_after_later_operation_failure() -> None:
    product = "[CH3:1][CH2:2][OH:3]"
    result = CoreGraphExecutor().execute(
        product,
        (
            BreakBondEdit(map_a=2, map_b=3),
            BreakBondEdit(map_a=2, map_b=99),
        ),
    )
    assert not result.success
    assert result.mapped_structures == (product,)
    assert len(result.diagnostic_mapped_structures) == 2
    assert result.applied_operations == ("0:break_bond",)
    assert result.error is not None
    assert result.error.operation_index == 1
    assert result.error.affected_atom_maps == (2, 99)


def test_duplicate_or_missing_atom_maps_fail_before_execution() -> None:
    duplicate = CoreGraphExecutor().execute("[CH3:1][OH:1]", (BreakBondEdit(map_a=1, map_b=2),))
    missing = CoreGraphExecutor().execute("CO", ())
    assert not duplicate.success
    assert duplicate.error is not None
    assert duplicate.error.affected_atom_maps == (1,)
    assert not missing.success
    assert missing.error is not None
    assert missing.error.error_type == "AtomMapError"


def test_sanitation_failure_preserves_original_and_diagnostic_graph() -> None:
    result = CoreGraphExecutor().execute(
        "[CH4:1].[CH4:2]",
        (AddBondEdit(map_a=1, map_b=2),),
        SanitationMode.DIAGNOSTIC,
    )
    assert not result.success
    assert not result.structurally_valid
    assert set(result.mapped_structures) == {"[CH4:1]", "[CH4:2]"}
    assert result.diagnostic_mapped_structures == ("[CH4:1][CH4:2]",)
    assert result.error is not None
    assert result.error.error_type == "SanitationError"
    assert result.error.rdkit_error


@pytest.mark.parametrize(
    ("product", "edit", "message"),
    [
        ("[CH3:1].[OH:2]", BreakBondEdit(map_a=1, map_b=2), "does not exist"),
        (
            "[CH3:1][OH:2]",
            BreakBondEdit(map_a=1, map_b=2, expected_order=2),
            "order mismatch",
        ),
        ("[CH3:1][OH:2]", AddBondEdit(map_a=1, map_b=2), "already exists"),
        (
            "[CH3:1].[OH:2]",
            ChangeBondOrderEdit(map_a=1, map_b=2, from_order=1, to_order=2),
            "does not exist",
        ),
        (
            "[CH3:1][OH:2]",
            ChangeBondOrderEdit(map_a=1, map_b=2, from_order=2, to_order=1),
            "order mismatch",
        ),
        ("[CH3:1].[CH3:2]", AddBondEdit(map_a=1, map_b=2, order=2.5), "unsupported"),
    ],
)
def test_core_operation_mismatches_fail_closed(product: str, edit: object, message: str) -> None:
    result = CoreGraphExecutor().execute(product, (edit,))  # type: ignore[arg-type]
    assert not result.success
    assert result.error is not None
    assert message in result.error.message


def test_invalid_input_sanitation_is_never_structurally_valid() -> None:
    strict = CoreGraphExecutor().execute("[CH5:1]", ())
    diagnostic = CoreGraphExecutor().execute("[CH5:1]", (), SanitationMode.DIAGNOSTIC)
    assert not strict.success and strict.error is not None
    assert strict.error.error_type == "InputSanitationError"
    assert not diagnostic.success and not diagnostic.structurally_valid
    assert diagnostic.warnings


def test_operation_label_retains_edit_id() -> None:
    result = CoreGraphExecutor().execute(
        "[CH2:1]=[CH2:2]",
        (ChangeBondOrderEdit(edit_id="lower", map_a=1, map_b=2, from_order=2, to_order=1),),
    )
    assert result.applied_operations == ("0:change_bond_order:lower",)
