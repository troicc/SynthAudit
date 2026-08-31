"""Export canonical JSON Schemas deterministically."""

from __future__ import annotations

import json
from pathlib import Path

from synthaudit.adapters.reactseq.models import (
    ReactSeqAdapterResult,
    ReactSeqBridgeRequest,
    ReactSeqBridgeResponse,
    ReactSeqTraversalContext,
)
from synthaudit.evaluation.reactseq_conformance import ReactSeqConformanceSummary
from synthaudit.schema.evidence import EvidenceValueV1
from synthaudit.schema.reaction_ir import ReactionIRV1
from synthaudit.schema.results import CheckResultV1, FullExecutionResult, SemanticComparisonV1
from synthaudit.schema.route_ir import RouteIRV1

SCHEMAS = {
    "reaction-ir-v1.schema.json": ReactionIRV1,
    "route-ir-v1.schema.json": RouteIRV1,
    "evidence-v1.schema.json": EvidenceValueV1,
    "check-result-v1.schema.json": CheckResultV1,
    "semantic-comparison-v1.schema.json": SemanticComparisonV1,
    "execution-result-v1.schema.json": FullExecutionResult,
    "reactseq-adapter-result-v1.schema.json": ReactSeqAdapterResult,
    "reactseq-traversal-context-v1.schema.json": ReactSeqTraversalContext,
    "reactseq-bridge-request-v1.schema.json": ReactSeqBridgeRequest,
    "reactseq-bridge-response-v1.schema.json": ReactSeqBridgeResponse,
    "reactseq-conformance-v1.schema.json": ReactSeqConformanceSummary,
}


def main() -> None:
    root = Path(__file__).resolve().parents[1] / "schemas"
    root.mkdir(parents=True, exist_ok=True)
    for filename, model in SCHEMAS.items():
        payload = model.model_json_schema()
        (root / filename).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
