from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NOTICE = (
    "SynthAudit estimates representation validity, corpus novelty and evidence-based plausibility. "
    "It does not establish experimental feasibility, yield, selectivity, safety or scalability."
)


def test_committed_product_examples_regenerate_byte_for_byte(tmp_path: Path) -> None:
    (tmp_path / "docs" / "diagrams").mkdir(parents=True)
    source_diagram = ROOT / "docs" / "diagrams" / "system-architecture.svg"
    (tmp_path / "docs" / "diagrams" / "system-architecture.svg").write_bytes(
        source_diagram.read_bytes()
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "build_product_examples.py"),
            "--root",
            str(tmp_path),
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert completed.returncode == 0, completed.stderr

    for relative_path in (
        "examples/reaction-ir.json",
        "examples/route-ir.json",
        "reports/examples/reaction-audit.html",
        "reports/examples/reaction-audit.json",
        "reports/examples/route-audit.html",
        "reports/examples/route-audit.json",
        "reports/examples/system-architecture.svg",
    ):
        assert (tmp_path / relative_path).read_bytes() == (ROOT / relative_path).read_bytes()


def test_committed_reports_display_the_required_boundary_notice() -> None:
    for filename in ("reaction-audit.html", "route-audit.html"):
        assert NOTICE in (ROOT / "reports" / "examples" / filename).read_text()
