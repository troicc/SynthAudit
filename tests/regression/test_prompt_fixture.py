from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from synthaudit.prompting import (
    PromptVariantKind,
    load_prompt_dataset,
    validate_prompt_benchmark_artifacts,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "benchmarks" / "prompt-robustness-v1"


def test_committed_prompt_fixture_is_content_addressed_and_complete() -> None:
    result = validate_prompt_benchmark_artifacts(
        cases_path=FIXTURE / "cases.jsonl",
        manifest_path=FIXTURE / "manifest.json",
    )
    assert result.valid
    assert result.case_count == 8
    assert result.variant_count == 40
    assert result.variant_kind_counts == {kind: 8 for kind in PromptVariantKind}
    assert result.parent_group_atomicity == "passed"
    assert result.metrics_status == "not_run"


def test_committed_prompt_fixture_regenerates_byte_for_byte(tmp_path: Path) -> None:
    output = tmp_path / "prompt-robustness-v1"
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "build_prompt_fixture.py"),
            "--output-dir",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert completed.returncode == 0, completed.stderr
    for filename in ("cases.jsonl", "manifest.json"):
        assert (output / filename).read_bytes() == (FIXTURE / filename).read_bytes()


def test_prompt_fixture_digest_rejects_tampering(tmp_path: Path) -> None:
    cases = tmp_path / "cases.jsonl"
    manifest = tmp_path / "manifest.json"
    cases.write_bytes((FIXTURE / "cases.jsonl").read_bytes())
    manifest.write_bytes((FIXTURE / "manifest.json").read_bytes())
    lines = cases.read_text().splitlines()
    payload = json.loads(lines[0])
    payload["case_id"] = "tampered-case"
    lines[0] = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    cases.write_text("\n".join(lines) + "\n")
    with pytest.raises(ValueError, match="SHA-256"):
        load_prompt_dataset(cases_path=cases, manifest_path=manifest)
