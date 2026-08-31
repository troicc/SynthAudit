"""Beginner-friendly, direct-use command line interface.

This module composes the existing canonical adapter, executor and audit APIs.
It does not duplicate chemistry logic or silently repair inputs.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import platform
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from importlib import metadata
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console

from synthaudit import __version__
from synthaudit.adapters.errors import AtomMappingRequired
from synthaudit.adapters.mapped_reaction_smiles import (
    MappedReactionSmilesAdapter,
    MappedReactionSmilesInput,
)
from synthaudit.audit.reaction import ReactionAuditor
from synthaudit.integrations.reactionclassifier import (
    ReactionClassifierUnavailableError,
    classify_reaction_ir,
)
from synthaudit.integrations.rxnmapper import MapperUnavailableError, map_reaction_smiles
from synthaudit.schema.reaction_ir import ReactionIRV1

NOTICE = (
    "SynthAudit checks representation consistency and evidence. It does not prove "
    "experimental feasibility, yield, selectivity, safety or scalability."
)

app = typer.Typer(
    name="synthaudit-easy",
    help="Direct-use workflows for mapped reaction SMILES, files and batches.",
    no_args_is_help=True,
)
console = Console()


def _package_version(name: str) -> str | None:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def doctor_report() -> dict[str, Any]:
    """Return an environment report without importing heavy optional models."""

    core_packages = ("synthaudit", "rdkit", "pydantic", "typer", "scikit-learn")
    optional_modules = {
        "streamlit": "ui",
        "reactionclassifier": "classifier",
        "rxnmapper": "mapper",
    }
    core = {name: _package_version(name) for name in core_packages}
    optional = {
        extra: {
            "module": module,
            "installed": importlib.util.find_spec(module) is not None,
            "version": _package_version(module),
        }
        for module, extra in optional_modules.items()
    }
    python_ok = sys.version_info[:2] == (3, 11)
    core_ok = python_ok and all(value is not None for value in core.values())
    return {
        "synthaudit_version": __version__,
        "python": platform.python_version(),
        "python_supported": python_ok,
        "platform": platform.platform(),
        "core_ready": core_ok,
        "core_packages": core,
        "optional_integrations": optional,
        "notice": NOTICE,
    }


def normalize_reaction(
    reaction_smiles: str,
    *,
    reaction_id: str | None = None,
    map_if_needed: bool = False,
) -> tuple[ReactionIRV1, str, dict[str, Any] | None]:
    """Normalize one reaction, optionally invoking a mapper only when requested."""

    text = reaction_smiles.strip()
    mapping: dict[str, Any] | None = None
    try:
        normalized = MappedReactionSmilesAdapter().normalize(
            MappedReactionSmilesInput(reaction_smiles=text, reaction_id=reaction_id)
        )
    except AtomMappingRequired:
        if not map_if_needed:
            raise
        mapped = map_reaction_smiles(text)
        mapping = mapped.to_dict()
        text = mapped.mapped_reaction_smiles
        normalized = MappedReactionSmilesAdapter().normalize(
            MappedReactionSmilesInput(reaction_smiles=text, reaction_id=reaction_id)
        )
    return normalized.reaction_ir, text, mapping


def audit_reaction_smiles(
    reaction_smiles: str,
    *,
    reaction_id: str | None = None,
    map_if_needed: bool = False,
) -> tuple[ReactionIRV1, Any, str, dict[str, Any] | None]:
    reaction, mapped_text, mapping = normalize_reaction(
        reaction_smiles,
        reaction_id=reaction_id,
        map_if_needed=map_if_needed,
    )
    audit = ReactionAuditor().audit(reaction)
    return reaction, audit, mapped_text, mapping


def _read_single_input(reaction: str | None, input_path: Path | None) -> str:
    if bool(reaction) == bool(input_path):
        raise typer.BadParameter("provide exactly one of --reaction or --input")
    if input_path is not None:
        return input_path.read_text(encoding="utf-8").strip()
    assert reaction is not None
    return reaction.strip()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    value = payload.model_dump(mode="json") if hasattr(payload, "model_dump") else payload
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _render_existing_report(reaction: ReactionIRV1, html_path: Path, json_path: Path) -> int:
    html_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="synthaudit-easy-") as directory:
        ir_path = Path(directory) / "reaction-ir.json"
        _write_json(ir_path, reaction)
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "synthaudit",
                "audit-reaction",
                "--input",
                str(ir_path),
                "--html",
                str(html_path),
                "--json",
                str(json_path),
            ],
            check=False,
        )
    return completed.returncode


def _failure_checks(audit: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for stage_name in (
        "structural_audit",
        "reaction_centre_audit",
        "completion_audit",
        "stereo_audit",
    ):
        stage = getattr(audit, stage_name)
        for item in stage.checks:
            status = getattr(item.status, "value", str(item.status))
            if status in {"fail", "warning", "indeterminate", "unsupported"}:
                result.append(
                    {
                        "stage": stage_name,
                        "check_id": item.check_id,
                        "status": status,
                        "severity": getattr(item.severity, "value", str(item.severity)),
                        "message": item.message,
                        "affected_atom_maps": list(item.affected_atom_maps),
                    }
                )
    return result


def _record_iterator(
    path: Path,
    *,
    reaction_column: str,
    id_column: str,
) -> Iterator[tuple[str, str]]:
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            payload = json.loads(line)
            if not isinstance(payload, dict) or reaction_column not in payload:
                raise ValueError(
                    f"JSONL line {line_number} lacks object field {reaction_column!r}"
                )
            identifier = str(payload.get(id_column) or f"row-{line_number}")
            yield identifier, str(payload[reaction_column])
        return
    if suffix not in {".csv", ".tsv"}:
        raise ValueError("batch input must be .csv, .tsv or .jsonl")
    delimiter = "\t" if suffix == ".tsv" else ","
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        if reader.fieldnames is None or reaction_column not in reader.fieldnames:
            raise ValueError(f"table lacks reaction column {reaction_column!r}")
        for row_number, row in enumerate(reader, 2):
            identifier = row.get(id_column) or f"row-{row_number}"
            reaction_value = row.get(reaction_column)
            if not reaction_value:
                raise ValueError(f"row {row_number} has an empty reaction")
            yield identifier, reaction_value


@app.command("doctor")
def doctor(
    json_output: Annotated[bool, typer.Option("--json", help="Emit JSON.")] = False,
) -> None:
    """Check the core environment and optional integrations."""

    report = doctor_report()
    if json_output:
        typer.echo(json.dumps(report, sort_keys=True))
    else:
        console.print("[bold]SynthAudit environment doctor[/bold]")
        console.print(report)
    if not report["core_ready"]:
        raise typer.Exit(code=2)


@app.command("map")
def map_command(
    reaction: Annotated[str | None, typer.Option("--reaction")] = None,
    input_path: Annotated[
        Path | None, typer.Option("--input", exists=True, dir_okay=False)
    ] = None,
    output: Annotated[Path | None, typer.Option("--output", dir_okay=False)] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Explicitly atom-map one reaction with the optional RXNMapper integration."""

    text = _read_single_input(reaction, input_path)
    try:
        result = map_reaction_smiles(text)
    except MapperUnavailableError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(result.mapped_reaction_smiles + "\n", encoding="utf-8")
    if json_output:
        typer.echo(json.dumps(result.to_dict(), sort_keys=True))
    else:
        console.print(result.mapped_reaction_smiles)
        console.print(f"[dim]{result.notice}[/dim]")


@app.command("classify")
def classify_command(
    reaction_ir: Annotated[Path, typer.Option("--reaction-ir", exists=True, dir_okay=False)],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Classify a ReactionIR through the optional ReactionClassifier integration."""

    parsed = ReactionIRV1.model_validate_json(reaction_ir.read_text(encoding="utf-8"))
    try:
        result = classify_reaction_ir(parsed)
    except ReactionClassifierUnavailableError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if json_output:
        typer.echo(json.dumps(result.to_dict(), sort_keys=True))
    else:
        console.print(result.to_dict())


@app.command("audit")
def audit_command(
    reaction: Annotated[str | None, typer.Option("--reaction")] = None,
    input_path: Annotated[
        Path | None, typer.Option("--input", exists=True, dir_okay=False)
    ] = None,
    reaction_id: Annotated[str | None, typer.Option("--reaction-id")] = None,
    map_if_needed: Annotated[
        bool,
        typer.Option(
            "--map-if-needed",
            help="Explicitly use optional RXNMapper when the input is unmapped.",
        ),
    ] = False,
    output_dir: Annotated[
        Path, typer.Option("--output-dir", file_okay=False)
    ] = Path("synthaudit-output"),
    no_html: Annotated[bool, typer.Option("--no-html")] = False,
    with_classifier: Annotated[bool, typer.Option("--with-classifier")] = False,
) -> None:
    """Normalize and audit one reaction without manually authoring ReactionIR."""

    text = _read_single_input(reaction, input_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        ir, audit, mapped_text, mapping = audit_reaction_smiles(
            text,
            reaction_id=reaction_id,
            map_if_needed=map_if_needed,
        )
    except (AtomMappingRequired, MapperUnavailableError) as exc:
        raise typer.BadParameter(str(exc)) from exc

    ir_path = output_dir / "reaction-ir.json"
    audit_path = output_dir / "audit.json"
    _write_json(ir_path, ir)
    _write_json(audit_path, audit)
    (output_dir / "mapped-reaction.smi").write_text(mapped_text + "\n", encoding="utf-8")
    if mapping is not None:
        _write_json(output_dir / "mapping.json", mapping)

    html_path: Path | None = None
    report_return_code: int | None = None
    if not no_html:
        html_path = output_dir / "audit.html"
        report_return_code = _render_existing_report(ir, html_path, audit_path)
        if report_return_code not in {0, 3}:
            raise RuntimeError(
                f"the existing report command failed with exit code {report_return_code}"
            )

    classification: dict[str, Any] | None = None
    if with_classifier:
        try:
            classification = classify_reaction_ir(ir).to_dict()
        except ReactionClassifierUnavailableError as exc:
            raise typer.BadParameter(str(exc)) from exc
        _write_json(output_dir / "classification.json", classification)

    summary = {
        "reaction_id": ir.reaction_id,
        "structurally_valid": audit.structurally_valid,
        "blocking": audit.blocking,
        "failure_and_review_checks": _failure_checks(audit),
        "reaction_ir": str(ir_path),
        "audit_json": str(audit_path),
        "audit_html": str(html_path) if html_path else None,
        "mapping_used": mapping is not None,
        "classification": classification,
        "report_exit_code": report_return_code,
        "notice": NOTICE,
    }
    _write_json(output_dir / "summary.json", summary)
    console.print(summary)
    if audit.blocking:
        raise typer.Exit(code=3)


@app.command("batch")
def batch_command(
    input_path: Annotated[Path, typer.Option("--input", exists=True, dir_okay=False)],
    output_dir: Annotated[
        Path, typer.Option("--output-dir", file_okay=False)
    ] = Path("synthaudit-batch-output"),
    reaction_column: Annotated[str, typer.Option("--reaction-column")] = "reaction_smiles",
    id_column: Annotated[str, typer.Option("--id-column")] = "reaction_id",
    map_if_needed: Annotated[bool, typer.Option("--map-if-needed")] = False,
    reports: Annotated[bool, typer.Option("--reports/--no-reports")] = False,
) -> None:
    """Audit a CSV, TSV or JSONL file and keep per-record errors visible."""

    output_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for identifier, reaction_smiles in _record_iterator(
        input_path, reaction_column=reaction_column, id_column=id_column
    ):
        record_dir = output_dir / "records" / identifier
        try:
            ir, audit, mapped_text, mapping = audit_reaction_smiles(
                reaction_smiles,
                reaction_id=identifier,
                map_if_needed=map_if_needed,
            )
            record_dir.mkdir(parents=True, exist_ok=True)
            _write_json(record_dir / "reaction-ir.json", ir)
            _write_json(record_dir / "audit.json", audit)
            (record_dir / "mapped-reaction.smi").write_text(
                mapped_text + "\n", encoding="utf-8"
            )
            if mapping is not None:
                _write_json(record_dir / "mapping.json", mapping)
            if reports:
                _render_existing_report(ir, record_dir / "audit.html", record_dir / "audit.json")
            rows.append(
                {
                    "reaction_id": identifier,
                    "status": "audited",
                    "structurally_valid": audit.structurally_valid,
                    "blocking": audit.blocking,
                    "mapping_used": mapping is not None,
                    "review_check_count": len(_failure_checks(audit)),
                    "record_dir": str(record_dir),
                }
            )
        except Exception as exc:
            rows.append(
                {
                    "reaction_id": identifier,
                    "status": "error",
                    "structurally_valid": None,
                    "blocking": None,
                    "mapping_used": False,
                    "review_check_count": None,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )

    results_path = output_dir / "results.jsonl"
    results_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    summary = {
        "input": str(input_path),
        "record_count": len(rows),
        "audited_count": sum(row["status"] == "audited" for row in rows),
        "error_count": sum(row["status"] == "error" for row in rows),
        "blocking_count": sum(row.get("blocking") is True for row in rows),
        "results": str(results_path),
        "notice": NOTICE,
    }
    _write_json(output_dir / "summary.json", summary)
    console.print(summary)
    if summary["error_count"]:
        raise typer.Exit(code=2)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
