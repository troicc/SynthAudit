from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from synthaudit.counterfactuals import validate_benchmark_artifacts

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "benchmarks" / "counterfactual-v1"


def test_committed_counterfactual_fixture_is_complete_and_leakage_checked() -> None:
    result = validate_benchmark_artifacts(
        records_path=FIXTURE / "records.jsonl",
        manifest_path=FIXTURE / "manifest.json",
        splits_path=FIXTURE / "splits.json",
        human_review_path=FIXTURE / "human-review.csv",
    )
    assert result.valid
    assert result.record_count == 200
    assert result.label_counts["recorded_reaction"] == 20
    assert result.label_counts["generated_counterfactual"] == 180
    assert result.method_count == 29
    assert all(result.category_counts.values())
    assert all(result.evaluation_slice_counts.values())
    assert result.human_review_row_count == 9
    assert result.leakage_checks == "passed"
    assert result.metrics_status == "not_run"


def test_committed_counterfactual_fixture_regenerates_byte_for_byte(tmp_path: Path) -> None:
    output = tmp_path / "counterfactual-v1"
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "build_counterfactual_fixture.py"),
            "--output-dir",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert completed.returncode == 0, completed.stderr
    for filename in ("records.jsonl", "manifest.json", "splits.json", "human-review.csv"):
        assert (output / filename).read_bytes() == (FIXTURE / filename).read_bytes()
