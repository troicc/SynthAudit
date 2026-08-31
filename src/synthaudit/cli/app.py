"""SynthAudit command-line application."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from synthaudit import SCIENTIFIC_NOTICE, __version__
from synthaudit.evaluation import run_reactseq_conformance

app = typer.Typer(
    name="synthaudit",
    help="Representation-agnostic auditing for reaction-edit retrosynthesis.",
    no_args_is_help=True,
)
console = Console()
benchmark_app = typer.Typer(help="Build and run controlled benchmark suites.")
app.add_typer(benchmark_app, name="benchmark")


@app.command()
def version(
    json_output: Annotated[
        bool, typer.Option("--json", help="Emit machine-readable JSON.")
    ] = False,
) -> None:
    """Print package and scientific-claim information."""
    payload = {"name": "synthaudit", "version": __version__, "notice": SCIENTIFIC_NOTICE}
    if json_output:
        typer.echo(json.dumps(payload, sort_keys=True))
    else:
        console.print(f"SynthAudit {__version__}")
        console.print(SCIENTIFIC_NOTICE, style="yellow")


@benchmark_app.command("run")
def benchmark_run(
    fixture: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Validate a small offline benchmark manifest without inventing metrics."""
    records = [json.loads(line) for line in fixture.read_text().splitlines() if line.strip()]
    payload = {
        "fixture": str(fixture),
        "records": len(records),
        "labels": sorted({str(record["label"]) for record in records}),
        "metrics": "not_run",
    }
    if json_output:
        typer.echo(json.dumps(payload, sort_keys=True))
    else:
        console.print(payload)


@benchmark_app.command("reactseq-conformance")
def reactseq_conformance(
    fixture: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Run measured conformance on an explicitly supplied offline fixture set."""
    result = run_reactseq_conformance(fixture)
    if json_output:
        typer.echo(result.model_dump_json())
    else:
        console.print(result.model_dump(mode="json"))
    if result.parse_success_count != result.fixture_count:
        raise typer.Exit(code=2)
    if result.execution_success_count != result.fixture_count:
        raise typer.Exit(code=3)
    if result.exact_reconstruction_count != result.fixture_count:
        raise typer.Exit(code=4)


def main() -> None:
    """Invoke the Typer application."""
    app()
