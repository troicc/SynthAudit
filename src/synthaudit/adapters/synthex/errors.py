"""SynthEx adapter-specific fail-closed errors."""

from synthaudit.adapters.errors import (
    UnsupportedAdapterOperation,
    UpstreamSpecificationUnavailable,
)

__all__ = ["UnsupportedAdapterOperation", "UpstreamSpecificationUnavailable"]
