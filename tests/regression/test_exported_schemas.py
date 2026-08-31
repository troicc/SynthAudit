from __future__ import annotations

import json
from pathlib import Path

from synthaudit.schema.evidence import EvidenceValueV1
from synthaudit.schema.reaction_ir import ReactionIRV1
from synthaudit.schema.results import CheckResultV1, FullExecutionResult, SemanticComparisonV1
from synthaudit.schema.route_ir import RouteIRV1


def test_committed_json_schemas_match_models() -> None:
    root = Path(__file__).resolve().parents[2] / "schemas"
    expected = {
        "reaction-ir-v1.schema.json": ReactionIRV1,
        "route-ir-v1.schema.json": RouteIRV1,
        "evidence-v1.schema.json": EvidenceValueV1,
        "check-result-v1.schema.json": CheckResultV1,
        "semantic-comparison-v1.schema.json": SemanticComparisonV1,
        "execution-result-v1.schema.json": FullExecutionResult,
    }
    for filename, model in expected.items():
        assert json.loads((root / filename).read_text()) == model.model_json_schema()
