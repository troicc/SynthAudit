from __future__ import annotations

from pathlib import Path

from synthaudit.ui.workspace import (
    build_benchmark_workspace,
    demo_reaction,
    demo_route,
    edit_rows,
    reaction_report_workspace,
    route_report_workspace,
)


def test_ui_view_models_are_core_backed_and_do_not_invent_missing_evidence() -> None:
    reaction = demo_reaction()
    reaction_report = reaction_report_workspace(reaction)
    assert reaction_report.audit.execution.success
    assert reaction_report.novelty is None
    assert reaction_report.precedents is None
    assert reaction_report.evidence == ()
    assert edit_rows(reaction)

    route_report = route_report_workspace(demo_route())
    assert not route_report.audit.blocking
    assert route_report.audit.minimum_step_support is None
    assert route_report.audit.exploratory_naive_independence_score is None


def test_benchmark_workspace_reports_fixture_observations_not_prefilled_research_metrics() -> None:
    result = build_benchmark_workspace(Path.cwd())
    assert result.counterfactual_record_count == 200
    assert result.prompt_case_count == 8
    assert result.prompt_variant_count == 40
    assert result.counterfactual_metrics_status == "not_run"
    assert result.prompt_metrics_status == "not_run"
    assert result.reactseq.fixture_count == 3
    assert not result.research_calibration_results_available
    assert not result.high_novelty_false_rejection_available
    assert "not population performance" in result.interpretation


def test_exactly_five_streamlit_pages_display_scientific_notice() -> None:
    root = Path("app")
    pages = (root / "Home.py", *sorted((root / "pages").glob("*.py")))
    assert len(pages) == 5
    assert all(path.exists() for path in pages)
    methodology = (root / "pages/5_Methodology_and_Limitations.py").read_text(encoding="utf-8")
    assert "Novelty is not plausibility" in methodology
    assert "SCIENTIFIC_NOTICE" in Path("src/synthaudit/ui/components.py").read_text(
        encoding="utf-8"
    )
