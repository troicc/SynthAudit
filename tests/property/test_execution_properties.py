from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from synthaudit.graph import CoreGraphExecutor
from synthaudit.schema import BreakBondEdit


@given(reverse=st.booleans())
def test_core_execution_is_deterministic_for_undirected_bond_reference(reverse: bool) -> None:
    maps = (2, 3) if not reverse else (3, 2)
    edit = BreakBondEdit(map_a=maps[0], map_b=maps[1])
    first = CoreGraphExecutor().execute("[CH3:1][CH2:2][OH:3]", (edit,))
    second = CoreGraphExecutor().execute("[CH3:1][CH2:2][OH:3]", (edit,))
    assert first == second


def test_failed_execution_never_returns_partial_graph_as_success() -> None:
    result = CoreGraphExecutor().execute(
        "[CH3:1][CH2:2][OH:3]",
        (BreakBondEdit(map_a=2, map_b=3), BreakBondEdit(map_a=2, map_b=99)),
    )
    assert not result.success
    assert result.mapped_structures == ("[CH3:1][CH2:2][OH:3]",)
    assert result.diagnostic_mapped_structures != result.mapped_structures
