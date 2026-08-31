from __future__ import annotations

import pytest

from synthaudit.graph import StereoExecutor
from synthaudit.schema import (
    ClearBondStereoEdit,
    ClearTetrahedralStereoEdit,
    InvertTetrahedralStereoEdit,
    SetBondStereoEdit,
    SetTetrahedralStereoEdit,
)


def test_invert_and_clear_tetrahedral_stereo() -> None:
    source = "[F:1][C@:2]([Cl:3])([Br:4])[I:5]"
    inverted = StereoExecutor().execute(source, (InvertTetrahedralStereoEdit(atom_map=2),))
    cleared = StereoExecutor().execute(source, (ClearTetrahedralStereoEdit(atom_map=2),))
    assert inverted.success and "@@" in inverted.mapped_structures[0]
    assert inverted.graph_diff is not None
    assert inverted.graph_diff.changed_tetrahedral_stereo
    assert cleared.success and "@" not in cleared.mapped_structures[0]


def test_set_absolute_tetrahedral_configuration() -> None:
    result = StereoExecutor().execute(
        "[F:1][C:2]([Cl:3])([Br:4])[I:5]",
        (SetTetrahedralStereoEdit(atom_map=2, configuration="R"),),
    )
    assert result.success
    assert "@" in result.mapped_structures[0]


def test_set_and_clear_ez_stereo() -> None:
    source = "[CH3:1][CH:2]=[CH:3][CH3:4]"
    set_result = StereoExecutor().execute(
        source,
        (
            SetBondStereoEdit(
                map_a=2,
                map_b=3,
                stereo="E",
                stereo_atom_a=1,
                stereo_atom_b=4,
            ),
        ),
    )
    assert set_result.success
    assert "/" in set_result.mapped_structures[0] or "\\" in set_result.mapped_structures[0]
    assert set_result.graph_diff is not None
    assert set_result.graph_diff.changed_bond_stereo

    clear_result = StereoExecutor().execute(
        set_result.mapped_structures,
        (ClearBondStereoEdit(map_a=2, map_b=3),),
    )
    assert clear_result.success
    assert "/" not in clear_result.mapped_structures[0]
    assert "\\" not in clear_result.mapped_structures[0]


def test_ambiguous_bond_stereo_neighbours_fail_indeterminate_path() -> None:
    result = StereoExecutor().execute(
        "[CH3:1][C:2]([F:5])=[C:3]([Cl:6])[CH3:4]",
        (SetBondStereoEdit(map_a=2, map_b=3, stereo="Z"),),
    )
    assert not result.success
    assert result.error is not None
    assert "ambiguous" in result.error.message


def test_invalid_inversion_is_transactional() -> None:
    source = "[CH3:1][CH2:2][OH:3]"
    result = StereoExecutor().execute(source, (InvertTetrahedralStereoEdit(atom_map=2),))
    assert not result.success
    assert result.mapped_structures == (source,)
    assert result.error is not None and result.error.operation_index == 0


def test_stereo_rejects_invalid_input_and_dangling_centres() -> None:
    unmapped = StereoExecutor().execute("CC", ())
    invalid = StereoExecutor().execute("[CH5:1]", ())
    dangling = StereoExecutor().execute(
        "[F:1][C:2]([Cl:3])([Br:4])[I:5]",
        (SetTetrahedralStereoEdit(atom_map=99, configuration="R"),),
    )
    assert not unmapped.success and unmapped.error is not None
    assert unmapped.error.error_type == "AtomMapError"
    assert not invalid.success and invalid.error is not None
    assert invalid.error.error_type == "InputSanitationError"
    assert not dangling.success and dangling.error is not None


def test_set_cw_ccw_degree_and_noop_paths() -> None:
    source = "[F:1][C:2]([Cl:3])([Br:4])[I:5]"
    cw = StereoExecutor().execute(
        source, (SetTetrahedralStereoEdit(atom_map=2, configuration="CW"),)
    )
    assert cw.success
    noop = StereoExecutor().execute(
        cw.mapped_structures,
        (SetTetrahedralStereoEdit(atom_map=2, configuration="CW"),),
    )
    low_degree = StereoExecutor().execute(
        "[CH3:1][CH2:2][OH:3]",
        (SetTetrahedralStereoEdit(atom_map=2, configuration="CCW"),),
    )
    indeterminate = StereoExecutor().execute(
        "[C:1]([F:2])([F:3])([Cl:4])[Br:5]",
        (SetTetrahedralStereoEdit(atom_map=1, configuration="R"),),
    )
    assert not noop.success
    assert not low_degree.success
    assert not indeterminate.success and indeterminate.error is not None
    assert "indeterminate" in indeterminate.error.message


def test_clear_unspecified_tetrahedral_and_bond_are_noops() -> None:
    tetra = StereoExecutor().execute(
        "[F:1][C:2]([Cl:3])([Br:4])[I:5]",
        (ClearTetrahedralStereoEdit(atom_map=2),),
    )
    bond = StereoExecutor().execute(
        "[CH3:1][CH:2]=[CH:3][CH3:4]",
        (ClearBondStereoEdit(map_a=2, map_b=3),),
    )
    assert not tetra.success
    assert not bond.success


@pytest.mark.parametrize(
    ("source", "edit", "message"),
    [
        (
            "[CH3:1][CH2:2]",
            SetBondStereoEdit(map_a=1, map_b=99, stereo="E"),
            "dangling",
        ),
        (
            "[CH3:1].[CH3:2]",
            SetBondStereoEdit(map_a=1, map_b=2, stereo="E"),
            "missing bond",
        ),
        (
            "[CH3:1][CH3:2]",
            SetBondStereoEdit(map_a=1, map_b=2, stereo="E"),
            "double bond",
        ),
        (
            "[CH3:1][CH:2]=[CH:3][CH3:4]",
            SetBondStereoEdit(map_a=2, map_b=3, stereo="E", stereo_atom_a=1),
            "both stereo",
        ),
        (
            "[CH3:1][CH:2]=[CH:3][CH3:4]",
            SetBondStereoEdit(map_a=2, map_b=3, stereo="E", stereo_atom_a=99, stereo_atom_b=4),
            "dangling stereo neighbour",
        ),
        (
            "[CH3:1][CH:2]=[CH:3][CH3:4].[F:5]",
            SetBondStereoEdit(map_a=2, map_b=3, stereo="E", stereo_atom_a=5, stereo_atom_b=4),
            "not a neighbour",
        ),
    ],
)
def test_bond_stereo_reference_errors(source: str, edit: SetBondStereoEdit, message: str) -> None:
    result = StereoExecutor().execute(source, (edit,))
    assert not result.success and result.error is not None
    assert message in result.error.message


def test_bond_stereo_auto_references_and_reversed_endpoints() -> None:
    source = "[CH3:1][CH:2]=[CH:3][CH3:4]"
    automatic = StereoExecutor().execute(source, (SetBondStereoEdit(map_a=2, map_b=3, stereo="Z"),))
    reversed_maps = StereoExecutor().execute(
        source,
        (
            SetBondStereoEdit(
                map_a=3,
                map_b=2,
                stereo="E",
                stereo_atom_a=4,
                stereo_atom_b=1,
            ),
        ),
    )
    assert automatic.success
    assert reversed_maps.success
