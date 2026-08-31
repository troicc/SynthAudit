"""Offline conformance and research-evaluation entry points."""

from synthaudit.evaluation.cross_representation import compare_representations
from synthaudit.evaluation.evidence_model_smoke import (
    EvidenceModelContractSmokeV1,
    run_evidence_model_contract_smoke,
)
from synthaudit.evaluation.reactseq_conformance import (
    ReactSeqConformanceCaseResult,
    ReactSeqConformanceSummary,
    run_reactseq_conformance,
)
from synthaudit.evaluation.route_prompt_smoke import (
    RoutePromptContractSmokeV1,
    run_route_prompt_contract_smoke,
)

__all__ = [
    "EvidenceModelContractSmokeV1",
    "ReactSeqConformanceCaseResult",
    "ReactSeqConformanceSummary",
    "RoutePromptContractSmokeV1",
    "compare_representations",
    "run_evidence_model_contract_smoke",
    "run_reactseq_conformance",
    "run_route_prompt_contract_smoke",
]
