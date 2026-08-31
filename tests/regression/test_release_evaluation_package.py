from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMMITTED = ROOT / "reports" / "research-evaluation-v1"
GENERATED_FILES = (
    "README.md",
    "SHA256SUMS",
    "manifest.json",
    "figures/research-question-status.svg",
    "figures/software-fixture-scope.svg",
    "tables/required-metric-status.csv",
    "tables/research-question-status.csv",
    "tables/software-fixture-observations.csv",
)


def test_release_evaluation_package_regenerates_byte_for_byte(tmp_path: Path) -> None:
    output = tmp_path / "research-evaluation-v1"
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "build_release_evaluation.py"),
            "--source-root",
            str(ROOT),
            "--output-dir",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert completed.returncode == 0, completed.stderr
    for relative_path in GENERATED_FILES:
        assert (output / relative_path).read_bytes() == (COMMITTED / relative_path).read_bytes()


def test_release_evaluation_checksums_cover_generated_evidence() -> None:
    rows = [
        line.split("  ", maxsplit=1) for line in (COMMITTED / "SHA256SUMS").read_text().splitlines()
    ]
    assert {relative for _, relative in rows} == set(GENERATED_FILES) - {"SHA256SUMS"}
    for expected, relative in rows:
        assert hashlib.sha256((COMMITTED / relative).read_bytes()).hexdigest() == expected
