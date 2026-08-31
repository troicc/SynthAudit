from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from synthaudit import SCIENTIFIC_NOTICE
from synthaudit.audit import ReactionAuditor, RouteAuditor
from synthaudit.reports import (
    EvidenceReportItemV1,
    ReactionReportV1,
    RouteReportV1,
    render_reaction_report_html,
    render_route_report_html,
    write_reaction_report,
    write_route_report,
)
from synthaudit.reports.standalone import report_provenance, route_svg
from synthaudit.ui.workspace import demo_reaction, demo_route


def _reaction_report() -> ReactionReportV1:
    reaction = demo_reaction()
    return ReactionReportV1(
        reaction=reaction,
        audit=ReactionAuditor().audit(reaction),
        provenance=report_provenance("test/reaction-report"),
    )


def _route_report() -> RouteReportV1:
    route = demo_route()
    return RouteReportV1(
        route=route,
        audit=RouteAuditor().audit(route),
        provenance=report_provenance("test/route-report"),
    )


def test_reaction_product_report_has_all_layout_sections_and_offline_assets(
    tmp_path: Path,
) -> None:
    report = _reaction_report()
    html = render_reaction_report_html(report)
    for heading in (
        "1. Input and source",
        "2. Representation normalization",
        "3. Product-to-synthon stage",
        "4. Synthon-to-precursor stage",
        "5. Stereo analysis",
        "6. Structural alerts and stage checks",
        "7. Multi-view novelty",
        "8. Precedents",
        "9. Evidence-based plausibility",
        "10. Uncertainty and abstention",
        "11. Limitations",
    ):
        assert heading in html
    assert SCIENTIFIC_NOTICE in html
    assert "Unavailable: no declared, versioned reference corpus" in html
    assert "No confidence value" not in html
    assert "<style>" in html and "<svg" in html
    assert "<script src=" not in html and "<link href=" not in html
    assert "prefers-reduced-motion" in html

    html_path, sidecar = write_reaction_report(tmp_path / "reaction.html", report)
    assert html_path.read_text(encoding="utf-8") == html
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "synthaudit.reaction-report/1"
    assert payload["novelty"] is None and payload["evidence"] == []


def test_route_report_exposes_independent_summaries_and_review_queue(tmp_path: Path) -> None:
    report = _route_report()
    html = render_route_report_html(report)
    assert SCIENTIFIC_NOTICE in html
    assert "Strategy and dependency graph" in html
    assert "Dependency, continuity, and condition checks" in html
    assert "Per-step alerts" in html
    assert "Expert-review queue" in html
    assert "No route success probability is reported" in html
    assert "route_success_probability" not in html
    assert "<svg" in html and "<script src=" not in html

    html_path, sidecar = write_route_report(tmp_path / "route.html", report)
    assert html_path.exists()
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "synthaudit.route-report/1"
    assert payload["audit"]["exploratory_naive_independence_score"] is None


def test_route_svg_escapes_labels_and_is_accessible() -> None:
    route = demo_route()
    hostile = route.steps[0].model_copy(update={"step_id": "step<script>"})
    dependent = route.steps[1].model_copy(update={"depends_on": ("step<script>",)})
    route = route.model_copy(update={"steps": (hostile, dependent)})
    svg = route_svg(route)
    assert "<title" in svg and "<desc" in svg
    assert "step&lt;script&gt;" in svg
    assert "step<script>" not in svg


def test_report_evidence_rejects_numbers_without_provenance() -> None:
    with pytest.raises(ValidationError, match="provenance"):
        EvidenceReportItemV1(
            stage="reaction_centre",
            availability="available",
            calibrated_evidence_support_score=0.7,
            uncertainty=0.2,
            abstained=False,
        )
    unavailable = EvidenceReportItemV1(
        stage="reaction_centre",
        availability="unavailable",
        abstained=True,
        abstention_reasons=("no selected model",),
    )
    assert unavailable.calibrated_evidence_support_score is None
