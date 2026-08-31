"""Stable fail-closed adapter errors."""

from __future__ import annotations


class AdapterError(ValueError):
    code = "adapter_error"


class AtomMappingRequired(AdapterError):
    code = "atom_mapping_required"


class UnsupportedAdapterOperation(AdapterError):
    code = "unsupported_adapter_operation"


class UpstreamSpecificationUnavailable(AdapterError):
    code = "upstream_specification_unavailable"
