"""Optional prompt-model provider interface with a fail-closed default."""

from __future__ import annotations

from typing import Protocol

from synthaudit.prompting.models import PromptModelOutputV1, PromptModelRequestV1
from synthaudit.schema.evidence import EvidenceAvailability


class PromptModelProvider(Protocol):
    provider_id: str
    model_id: str

    def generate(self, request: PromptModelRequestV1) -> PromptModelOutputV1: ...


class UnavailablePromptModelProvider:
    provider_id = "unavailable-prompt-model-provider"
    model_id = "unconfigured"

    def generate(self, request: PromptModelRequestV1) -> PromptModelOutputV1:
        return PromptModelOutputV1(
            request_id=request.request_id,
            case_id=request.case_id,
            variant_id=request.variant.variant_id,
            provider_id=self.provider_id,
            model_id=self.model_id,
            availability=EvidenceAvailability.UNAVAILABLE,
            missing_reasons=(
                "no versioned prompt-capable model artifact and local inference provider was configured",
            ),
        )
