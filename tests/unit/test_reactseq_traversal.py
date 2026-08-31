from __future__ import annotations

import pytest

from synthaudit.adapters.reactseq.errors import ReactSeqTraversalIndeterminateError
from synthaudit.adapters.reactseq.tokenizer import parse_document
from synthaudit.adapters.reactseq.traversal import build_traversal_context


def test_unique_graph_isomorphism_resolves_reversed_product_traversal() -> None:
    document = parse_document("OCC>>>OC!C<[Br:1]><>")
    context = build_traversal_context(
        document,
        "[CH3:10][CH2:20][OH:30]",
    )

    assert context.mapping_method == "unique_graph_isomorphism"
    assert context.stable_map(1) == 30
    assert context.stable_map(2) == 20
    assert context.stable_map(3) == 10


def test_symmetric_nonindexed_product_mapping_is_indeterminate() -> None:
    document = parse_document("CCC>>>C!CC<><>")
    with pytest.raises(ReactSeqTraversalIndeterminateError) as error:
        build_traversal_context(
            document,
            "[CH2:2]([CH3:1])[CH3:3]",
        )
    assert error.value.code == "reactseq_traversal_indeterminate"
    assert error.value.details["candidate_mappings"] == 2


def test_identical_indexed_symmetric_traversal_is_safe() -> None:
    document = parse_document("CC>>>C!C<><>")
    context = build_traversal_context(document, "[CH3:8][CH3:4]")
    assert context.mapping_method == "indexed_source"
    assert context.stable_map(1) == 8
    assert context.stable_map(2) == 4
