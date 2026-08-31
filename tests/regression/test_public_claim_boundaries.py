from __future__ import annotations

from pathlib import Path

from synthaudit import SCIENTIFIC_NOTICE

ROOT = Path(__file__).resolve().parents[2]


def test_public_markdown_reports_and_methodology_display_scientific_notice() -> None:
    documents = [
        ROOT / "README.md",
        ROOT / "CHANGELOG.md",
        ROOT / "examples" / "README.md",
        ROOT / "reports" / "research-evaluation-v1" / "README.md",
        *(ROOT / "docs").rglob("*.md"),
        *(ROOT / "benchmarks").glob("*/DATA_CARD.md"),
    ]
    missing = [
        str(path.relative_to(ROOT))
        for path in documents
        if SCIENTIFIC_NOTICE not in path.read_text(encoding="utf-8")
    ]
    assert missing == []
