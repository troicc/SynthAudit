"""Fail-closed ReactSeq parsing and bridge errors."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from synthaudit.schema.edits import SourceRange


class ReactSeqError(ValueError):
    """Base error carrying a stable category and optional source location."""

    code = "reactseq_error"

    def __init__(
        self,
        message: str,
        *,
        source_range: SourceRange | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.source_range = source_range
        self.details = dict(details or {})

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": str(self),
            "source_range": (
                self.source_range.model_dump(mode="json") if self.source_range else None
            ),
            "details": self.details,
        }


class ReactSeqSyntaxError(ReactSeqError):
    code = "reactseq_syntax_error"


class ReactSeqUnsupportedError(ReactSeqError):
    code = "reactseq_unsupported"


class ReactSeqTraversalIndeterminateError(ReactSeqError):
    code = "reactseq_traversal_indeterminate"


class ReactSeqOfficialBridgeError(ReactSeqError):
    code = "reactseq_official_bridge_error"
