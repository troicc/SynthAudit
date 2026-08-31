"""Source-preserving tokenizer for the public ReactSeq surface syntax."""

from __future__ import annotations

from synthaudit.adapters.reactseq.errors import ReactSeqSyntaxError
from synthaudit.adapters.reactseq.models import (
    ReactSeqAtomToken,
    ReactSeqDocument,
    ReactSeqTailRecord,
)
from synthaudit.schema.edits import SourceRange

_AROMATIC_TWO = {"se", "as"}


def atom_tokens(smiles: str, *, source_offset: int = 0) -> tuple[ReactSeqAtomToken, ...]:
    """Locate SMILES atom tokens without treating their positions as atom maps."""
    tokens: list[ReactSeqAtomToken] = []
    index = 0
    position = 0
    while position < len(smiles):
        char = smiles[position]
        if char == "[":
            end = smiles.find("]", position + 1)
            if end < 0:
                raise ReactSeqSyntaxError(
                    "unclosed bracket atom",
                    source_range=SourceRange(
                        start=source_offset + position, end=source_offset + len(smiles)
                    ),
                )
            index += 1
            tokens.append(
                ReactSeqAtomToken(
                    reactseq_atom_index=index,
                    text=smiles[position : end + 1],
                    source_range=SourceRange(
                        start=source_offset + position,
                        end=source_offset + end + 1,
                    ),
                )
            )
            position = end + 1
            continue
        if smiles[position : position + 2] in _AROMATIC_TWO:
            end = position + 2
        elif char.isupper():
            end = position + 1
            if end < len(smiles) and smiles[end].islower():
                end += 1
        elif char in "bcnops*":
            end = position + 1
        else:
            position += 1
            continue
        index += 1
        tokens.append(
            ReactSeqAtomToken(
                reactseq_atom_index=index,
                text=smiles[position:end],
                source_range=SourceRange(start=source_offset + position, end=source_offset + end),
            )
        )
        position = end
    return tuple(tokens)


def parse_document(
    source: str,
    *,
    fallback_product_smiles: str | None = None,
) -> ReactSeqDocument:
    """Split `product>>>header<tail>...` while retaining half-open ranges."""
    if source.count(">>>") > 1:
        raise ReactSeqSyntaxError("ReactSeq contains more than one '>>>' delimiter")
    if ">>>" in source:
        original_product, encoded = source.split(">>>", 1)
        if not original_product:
            raise ReactSeqSyntaxError("ReactSeq product prefix is empty")
        encoded_offset = len(original_product) + 3
    else:
        if fallback_product_smiles is None:
            raise ReactSeqSyntaxError("ReactSeq without '>>>' requires a product traversal")
        original_product = fallback_product_smiles
        encoded = source
        encoded_offset = 0

    first_tail = encoded.find("<")
    if first_tail < 0:
        header = encoded
        tail_source = ""
    else:
        header = encoded[:first_tail]
        tail_source = encoded[first_tail:]
    if not header:
        raise ReactSeqSyntaxError("ReactSeq edit header is empty")

    tails: list[ReactSeqTailRecord] = []
    cursor = 0
    while cursor < len(tail_source):
        absolute = encoded_offset + first_tail + cursor
        if tail_source[cursor] != "<":
            raise ReactSeqSyntaxError(
                "unexpected text outside a ReactSeq tail record",
                source_range=SourceRange(start=absolute, end=absolute + 1),
            )
        end = tail_source.find(">", cursor + 1)
        if end < 0:
            raise ReactSeqSyntaxError(
                "unclosed ReactSeq tail record",
                source_range=SourceRange(
                    start=absolute,
                    end=encoded_offset + first_tail + len(tail_source),
                ),
            )
        raw = tail_source[cursor + 1 : end]
        if "<" in raw:
            raise ReactSeqSyntaxError(
                "nested ReactSeq tail delimiters are unsupported",
                source_range=SourceRange(start=absolute, end=encoded_offset + first_tail + end + 1),
            )
        if raw and any(item == "" for item in raw.split(",")):
            raise ReactSeqSyntaxError(
                "empty item inside a non-empty ReactSeq tail",
                source_range=SourceRange(start=absolute, end=encoded_offset + first_tail + end + 1),
            )
        tails.append(
            ReactSeqTailRecord(
                attachment_ordinal=len(tails),
                raw=raw,
                source_range=SourceRange(start=absolute, end=encoded_offset + first_tail + end + 1),
            )
        )
        cursor = end + 1

    return ReactSeqDocument(
        source=source,
        original_product_smiles=original_product,
        header=header,
        header_range=SourceRange(start=encoded_offset, end=encoded_offset + len(header)),
        tails=tuple(tails),
    )
