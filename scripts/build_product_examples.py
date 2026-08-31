"""Regenerate committed Phase 11 reaction/route inputs and standalone reports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from shutil import copyfile

from synthaudit.audit import ReactionAuditor, RouteAuditor
from synthaudit.reports import (
    ReactionReportV1,
    RouteReportV1,
    write_reaction_report,
    write_route_report,
)
from synthaudit.reports.standalone import report_provenance
from synthaudit.ui.workspace import demo_reaction, demo_route


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    value = payload.model_dump(mode="json") if hasattr(payload, "model_dump") else payload
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build(root: Path) -> None:
    examples = root / "examples"
    reports = root / "reports" / "examples"
    reaction = demo_reaction()
    route = demo_route()
    _write(examples / "reaction-ir.json", reaction)
    _write(examples / "route-ir.json", route)

    reaction_report = ReactionReportV1(
        reaction=reaction,
        audit=ReactionAuditor().audit(reaction),
        limitations=(
            "Authored software example only; no external corpus or calibrated model was run.",
        ),
        provenance=report_provenance("build-product-examples/reaction"),
    )
    route_report = RouteReportV1(
        route=route,
        audit=RouteAuditor().audit(route),
        limitations=("Authored software example only; no external route evidence was supplied.",),
        provenance=report_provenance("build-product-examples/route"),
    )
    write_reaction_report(reports / "reaction-audit.html", reaction_report)
    write_route_report(reports / "route-audit.html", route_report)
    copyfile(
        root / "docs" / "diagrams" / "system-architecture.svg", reports / "system-architecture.svg"
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository-shaped output root (defaults to the current repository).",
    )
    return parser


def main() -> None:
    build(_parser().parse_args().root.resolve())


if __name__ == "__main__":
    main()
