from __future__ import annotations

import json
from pathlib import Path

from synthaudit.application.models import CommandEnvelopeV1, NormalizedReactionV1
from synthaudit.data.transfer import DataDownloadManifestV1, DataDownloadResultV1
from synthaudit.models.artifacts import EvidenceModelArtifactV1
from synthaudit.reports.models import EvidenceReportItemV1, ReactionReportV1, RouteReportV1
from synthaudit.schema.evidence import EvidenceValueV1
from synthaudit.schema.reaction_ir import ReactionIRV1
from synthaudit.schema.results import CheckResultV1, FullExecutionResult, SemanticComparisonV1
from synthaudit.schema.route_audit import RouteAuditResultV1
from synthaudit.schema.route_ir import RouteIRV1
from synthaudit.ui.workspace import BenchmarkWorkspaceV1


def test_committed_json_schemas_match_models() -> None:
    root = Path(__file__).resolve().parents[2] / "schemas"
    expected = {
        "reaction-ir-v1.schema.json": ReactionIRV1,
        "route-ir-v1.schema.json": RouteIRV1,
        "evidence-v1.schema.json": EvidenceValueV1,
        "check-result-v1.schema.json": CheckResultV1,
        "semantic-comparison-v1.schema.json": SemanticComparisonV1,
        "execution-result-v1.schema.json": FullExecutionResult,
        "route-audit-result-v1.schema.json": RouteAuditResultV1,
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
    for filename, model in expected.items():
        assert json.loads((root / filename).read_text()) == model.model_json_schema()
