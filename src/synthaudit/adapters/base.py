"""Representation-independent adapter protocols."""

from __future__ import annotations

from typing import Protocol, TypeVar

from synthaudit.schema.reaction_ir import ReactionIRV1

SourceT = TypeVar("SourceT", contravariant=True)


class ReactionAdapter(Protocol[SourceT]):
    """Convert one external representation without executing or repairing it."""

    def to_reaction_ir(self, source: SourceT) -> ReactionIRV1:
        """Normalize a source object into the canonical reaction representation."""
        ...
