from __future__ import annotations

from pathlib import Path

from synthaudit.evaluation import run_reactseq_conformance

FIXTURE = Path(__file__).parents[1] / "fixtures" / "reactseq" / "golden.json"


def test_pinned_official_repository_demo_fixtures_reconstruct_exactly() -> None:
    result = run_reactseq_conformance(FIXTURE)
    assert result.fixture_count == 3
    assert result.parse_success_count == 3
    assert result.execution_success_count == 3
    assert result.exact_reconstruction_count == 3
    assert all(case.atom_map_preservation for case in result.cases)
    assert all(case.leaving_group_exact_match for case in result.cases)
    assert all(case.ring_change_consistency for case in result.cases)


def test_fixture_metrics_are_scoped_not_claimed_as_population_results() -> None:
    result = run_reactseq_conformance(FIXTURE)
    assert "committed pinned fixtures only" in result.interpretation
    assert "experimental feasibility" in result.interpretation
