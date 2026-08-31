from __future__ import annotations

import tomllib
from pathlib import Path

from synthaudit import __version__

ROOT = Path(__file__).resolve().parents[2]


def test_v1_release_metadata_is_consistent_and_has_no_placeholder_remote() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    citation = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
    lock = (ROOT / "uv.lock").read_text(encoding="utf-8")

    assert __version__ == "1.0.0"
    assert project["project"]["version"] == __version__
    assert "version: 1.0.0\n" in citation
    assert 'name = "synthaudit"\nversion = "1.0.0"' in lock
    assert "github.com/example" not in (ROOT / "README.md").read_text(encoding="utf-8")
    assert "github.com/example" not in citation
    assert "urls" not in project["project"]
    force_include = project["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]
    assert force_include == {
        "app": "synthaudit/ui_app",
        ".streamlit": "synthaudit/.streamlit",
    }


def test_release_materials_and_container_context_are_complete() -> None:
    required_phd_files = {
        "PROJECT_SUMMARY.md",
        "CV_BULLETS.md",
        "TWO_PAGE_RESEARCH_NOTE.md",
        "RESEARCH_STATEMENT_PARAGRAPH.md",
        "EMAIL_PARAGRAPH.md",
    }
    assert {path.name for path in (ROOT / "docs" / "phd").glob("*.md")} == required_phd_files
    for relative in (
        "docs/TECHNICAL_REPORT.md",
        "docs/MODEL_CARD.md",
        "docs/DATASET_CARD.md",
        "docs/RELEASE_NOTES_V1.0.0.md",
        "CHANGELOG.md",
    ):
        assert (ROOT / relative).is_file()

    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    for directory in (
        ".streamlit",
        "app",
        "benchmarks",
        "configs",
        "docs",
        "examples",
        "reports",
        "schemas",
        "scripts",
    ):
        assert f"COPY {directory} " in dockerfile
