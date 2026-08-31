from __future__ import annotations

import pytest

from synthaudit.adapters.reactseq.errors import ReactSeqSyntaxError
from synthaudit.adapters.reactseq.tokenizer import atom_tokens, parse_document


def test_document_preserves_header_and_tail_ranges() -> None:
    source = "CC>>>C!C<><[Br:1]>"
    document = parse_document(source)

    assert document.original_product_smiles == "CC"
    assert document.header == "C!C"
    assert document.header_range.start == 5
    assert document.header_range.end == 8
    assert [source[item.source_range.start : item.source_range.end] for item in document.tails] == [
        "<>",
        "<[Br:1]>",
    ]


def test_atom_tokenizer_handles_brackets_two_letter_elements_and_aromatic_atoms() -> None:
    tokens = atom_tokens("[rC@H](Cl)(Br)c1ncccc1")
    assert [token.text for token in tokens] == [
        "[rC@H]",
        "Cl",
        "Br",
        "c",
        "n",
        "c",
        "c",
        "c",
        "c",
    ]
    assert [token.reactseq_atom_index for token in tokens] == list(range(1, 10))


@pytest.mark.parametrize(
    "source",
    ["CC>>>C!C<", "CC>>>C!C<x", "CC>>>C!C<a,,b>", "CC>>>>>>C!C"],
)
def test_malformed_documents_fail_closed(source: str) -> None:
    with pytest.raises(ReactSeqSyntaxError):
        parse_document(source)
