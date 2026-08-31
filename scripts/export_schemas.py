"""Export canonical JSON Schemas deterministically."""

from __future__ import annotations

import json
from pathlib import Path

from synthaudit.adapters.models import ReactionAdapterResultV1, RouteAdapterResultV1
from synthaudit.adapters.reactseq.models import (
    ReactSeqAdapterResult,
    ReactSeqBridgeRequest,
    ReactSeqBridgeResponse,
    ReactSeqTraversalContext,
)
from synthaudit.application.models import CommandEnvelopeV1, NormalizedReactionV1
from synthaudit.counterfactuals.models import (
    BenchmarkSplitManifestV1,
    CounterfactualBenchmarkValidationV1,
    CounterfactualDatasetV1,
    CounterfactualRecordV1,
)
from synthaudit.data.transfer import DataDownloadManifestV1, DataDownloadResultV1
from synthaudit.evaluation.evidence_model_smoke import EvidenceModelContractSmokeV1
from synthaudit.evaluation.reactseq_conformance import ReactSeqConformanceSummary
from synthaudit.evaluation.route_prompt_smoke import RoutePromptContractSmokeV1
from synthaudit.models.artifacts import EvidenceModelArtifactV1
from synthaudit.models.evidence import (
    AbstentionPolicyV1,
    EvidenceEvaluationV1,
    EvidenceExampleV1,
    EvidenceModelManifestV1,
    EvidenceModelPlanV1,
    EvidencePredictionV1,
)
from synthaudit.novelty.models import MultiViewNoveltyResultV1
from synthaudit.precedent.models import (
    ConditionEvidenceV1,
    PrecedentSearchResultV1,
    ProcedureEvidenceV1,
    ReferenceIndexArtifactV1,
)
from synthaudit.prompting.models import (
    PromptBenchmarkCaseV1,
    PromptBenchmarkDatasetV1,
    PromptBenchmarkEvaluationV1,
    PromptBenchmarkValidationV1,
    PromptModelOutputV1,
    PromptModelRequestV1,
)
from synthaudit.providers.forward import ForwardReactionEvidenceV1
from synthaudit.providers.llm_critic import IndependentCriticEvidenceV1
from synthaudit.reports.models import EvidenceReportItemV1, ReactionReportV1, RouteReportV1
from synthaudit.schema.evidence import EvidenceValueV1
from synthaudit.schema.reaction_ir import ReactionIRV1
from synthaudit.schema.results import (
    CheckResultV1,
    FullExecutionResult,
    ReactionAuditResultV1,
    RepresentationConformanceV1,
    SemanticComparisonV1,
)
from synthaudit.schema.route_audit import RouteAuditResultV1, RouteStepEvidenceV1
from synthaudit.schema.route_ir import RouteIRV1
from synthaudit.ui.workspace import BenchmarkWorkspaceV1

SCHEMAS = {
    "reaction-ir-v1.schema.json": ReactionIRV1,
    "route-ir-v1.schema.json": RouteIRV1,
    "evidence-v1.schema.json": EvidenceValueV1,
    "check-result-v1.schema.json": CheckResultV1,
    "semantic-comparison-v1.schema.json": SemanticComparisonV1,
    "execution-result-v1.schema.json": FullExecutionResult,
    "reaction-audit-result-v1.schema.json": ReactionAuditResultV1,
    "reactseq-adapter-result-v1.schema.json": ReactSeqAdapterResult,
    "reactseq-traversal-context-v1.schema.json": ReactSeqTraversalContext,
    "reactseq-bridge-request-v1.schema.json": ReactSeqBridgeRequest,
    "reactseq-bridge-response-v1.schema.json": ReactSeqBridgeResponse,
    "reactseq-conformance-v1.schema.json": ReactSeqConformanceSummary,
    "reaction-adapter-result-v1.schema.json": ReactionAdapterResultV1,
    "route-adapter-result-v1.schema.json": RouteAdapterResultV1,
    "representation-conformance-v1.schema.json": RepresentationConformanceV1,
    "multi-view-novelty-v1.schema.json": MultiViewNoveltyResultV1,
    "precedent-search-v1.schema.json": PrecedentSearchResultV1,
    "reference-index-v1.schema.json": ReferenceIndexArtifactV1,
    "procedure-evidence-v1.schema.json": ProcedureEvidenceV1,
    "condition-evidence-v1.schema.json": ConditionEvidenceV1,
    "counterfactual-record-v1.schema.json": CounterfactualRecordV1,
    "counterfactual-dataset-v1.schema.json": CounterfactualDatasetV1,
    "benchmark-splits-v1.schema.json": BenchmarkSplitManifestV1,
    "counterfactual-benchmark-validation-v1.schema.json": (CounterfactualBenchmarkValidationV1),
    "evidence-example-v1.schema.json": EvidenceExampleV1,
    "evidence-model-manifest-v1.schema.json": EvidenceModelManifestV1,
    "evidence-model-plan-v1.schema.json": EvidenceModelPlanV1,
    "evidence-prediction-v1.schema.json": EvidencePredictionV1,
    "evidence-evaluation-v1.schema.json": EvidenceEvaluationV1,
    "abstention-policy-v1.schema.json": AbstentionPolicyV1,
    "forward-reaction-evidence-v1.schema.json": ForwardReactionEvidenceV1,
    "independent-critic-evidence-v1.schema.json": IndependentCriticEvidenceV1,
    "evidence-model-contract-smoke-v1.schema.json": EvidenceModelContractSmokeV1,
    "route-audit-result-v1.schema.json": RouteAuditResultV1,
    "route-step-evidence-v1.schema.json": RouteStepEvidenceV1,
    "prompt-benchmark-case-v1.schema.json": PromptBenchmarkCaseV1,
    "prompt-benchmark-dataset-v1.schema.json": PromptBenchmarkDatasetV1,
    "prompt-benchmark-validation-v1.schema.json": PromptBenchmarkValidationV1,
    "prompt-model-request-v1.schema.json": PromptModelRequestV1,
    "prompt-model-output-v1.schema.json": PromptModelOutputV1,
    "prompt-benchmark-evaluation-v1.schema.json": PromptBenchmarkEvaluationV1,
    "route-prompt-contract-smoke-v1.schema.json": RoutePromptContractSmokeV1,
    "command-envelope-v1.schema.json": CommandEnvelopeV1,
    "normalized-reaction-v1.schema.json": NormalizedReactionV1,
    "data-download-manifest-v1.schema.json": DataDownloadManifestV1,
    "data-download-result-v1.schema.json": DataDownloadResultV1,
    "evidence-model-artifact-v1.schema.json": EvidenceModelArtifactV1,
    "evidence-report-item-v1.schema.json": EvidenceReportItemV1,
    "reaction-report-v1.schema.json": ReactionReportV1,
    "route-report-v1.schema.json": RouteReportV1,
    "benchmark-workspace-v1.schema.json": BenchmarkWorkspaceV1,
}


def main() -> None:
    root = Path(__file__).resolve().parents[1] / "schemas"
    root.mkdir(parents=True, exist_ok=True)
    for filename, model in SCHEMAS.items():
        payload = model.model_json_schema()
        (root / filename).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
