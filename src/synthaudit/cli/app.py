"""Complete, provenance-preserving SynthAudit command-line application."""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any, TypeVar, cast

import typer
from pydantic import BaseModel, JsonValue
from rich.console import Console
from rich.panel import Panel

from synthaudit import SCIENTIFIC_NOTICE, __version__
from synthaudit.application.models import CommandEnvelopeV1, ReactionSourceKind
from synthaudit.application.workflows import (
    load_reaction_ir,
    load_route_ir,
    normalize_reaction_source,
    prepare_reference_index,
    read_json,
)
from synthaudit.audit import ReactionAuditor, RouteAuditor
from synthaudit.counterfactuals import validate_benchmark_artifacts
from synthaudit.data import download_from_manifest
from synthaudit.evaluation import (
    compare_representations,
    run_evidence_model_contract_smoke,
    run_reactseq_conformance,
    run_route_prompt_contract_smoke,
)
from synthaudit.graph.executor import ReactionExecutor
from synthaudit.graph.sanitize import SanitationMode
from synthaudit.models.artifacts import load_evidence_model, save_evidence_model
from synthaudit.models.evaluation import evaluate_evidence_scores
from synthaudit.models.evidence import (
    CalibrationMethod,
    EstimatorFamily,
    EvidenceExampleSplit,
    EvidenceExampleV1,
    EvidenceModelRole,
    EvidenceStage,
)
from synthaudit.models.training import fit_evidence_model
from synthaudit.novelty.engine import MultiViewNoveltyEngine
from synthaudit.precedent.index import ReferenceIndex
from synthaudit.precedent.retrieval import PrecedentRetriever
from synthaudit.prompting import validate_prompt_benchmark_artifacts
from synthaudit.reports import (
    EvidenceReportItemV1,
    ReactionReportV1,
    RouteReportV1,
    write_reaction_report,
    write_route_report,
)
from synthaudit.reports.standalone import report_provenance
from synthaudit.schema.route_audit import RouteStepEvidenceV1

app = typer.Typer(
    name="synthaudit",
    help="Representation-agnostic auditing for reaction-edit retrosynthesis.",
    no_args_is_help=True,
)
console = Console()
benchmark_app = typer.Typer(help="Build, validate, and run controlled benchmark suites.")
precedent_app = typer.Typer(help="Search a declared, versioned local precedent index.")
novelty_app = typer.Typer(help="Score independent corpus-relative novelty views.")
data_app = typer.Typer(help="Acquire and prepare data through explicit manifests.")
app.add_typer(benchmark_app, name="benchmark")
app.add_typer(precedent_app, name="precedent")
app.add_typer(novelty_app, name="novelty")
app.add_typer(data_app, name="data")

JsonPath = Annotated[
    Path | None,
    typer.Option(
        "--json",
        help="Write structured JSON to this path; use '-' for standard output.",
        dir_okay=False,
    ),
]
T = TypeVar("T")


def _json_value(value: object) -> JsonValue:
    if isinstance(value, BaseModel):
        return cast(JsonValue, value.model_dump(mode="json"))
    serialized = json.dumps(value, default=str)
    return cast(JsonValue, json.loads(serialized))


def _emit_payload(value: object, destination: Path | None) -> None:
    payload = _json_value(value)
    serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if destination is not None:
        if str(destination) == "-":
            typer.echo(serialized, nl=False)
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(serialized, encoding="utf-8")
            console.print(f"Structured JSON: [bold]{destination}[/bold]")
    else:
        console.print_json(data=payload)


def _run(command: str, destination: Path | None, action: Callable[[], T]) -> T:
    try:
        result = action()
    except Exception as exc:
        envelope = CommandEnvelopeV1.failure(command, exc)
        serialized = envelope.model_dump_json(indent=2)
        if destination is not None and str(destination) != "-":
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(serialized + "\n", encoding="utf-8")
        typer.echo(serialized, err=True)
        raise typer.Exit(code=2) from exc
    _emit_payload(result, destination)
    return result


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def _optional_product(product: Path | None, product_smiles: str | None) -> str | None:
    if product is not None and product_smiles is not None:
        raise ValueError("use either --product or --product-smiles, not both")
    return _text(product) if product is not None else product_smiles


def _load_step_evidence(path: Path | None) -> tuple[RouteStepEvidenceV1, ...]:
    if path is None:
        return ()
    payload = read_json(path)
    if not isinstance(payload, list):
        raise ValueError("route step evidence must be a JSON array")
    return tuple(RouteStepEvidenceV1.model_validate(item) for item in payload)


def _load_report_evidence(path: Path | None) -> tuple[EvidenceReportItemV1, ...]:
    if path is None:
        return ()
    payload = read_json(path)
    if not isinstance(payload, list):
        raise ValueError("report evidence must be a JSON array")
    return tuple(EvidenceReportItemV1.model_validate(item) for item in payload)


def _load_examples(path: Path) -> tuple[EvidenceExampleV1, ...]:
    values: list[EvidenceExampleV1] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            values.append(EvidenceExampleV1.model_validate_json(line))
        except Exception as exc:
            raise ValueError(f"invalid evidence example at line {line_number}: {exc}") from exc
    if not values:
        raise ValueError("evidence example file is empty")
    return tuple(values)


def _safe_report_sidecar(html_path: Path, *inputs: Path | None) -> Path | None:
    default = html_path.with_suffix(".json")
    resolved_inputs = {item.resolve() for item in inputs if item is not None}
    return html_path.with_suffix(".report.json") if default.resolve() in resolved_inputs else None


def _role_for_stage(stage: EvidenceStage) -> EvidenceModelRole:
    return {
        EvidenceStage.REACTION_CENTRE: EvidenceModelRole.REACTION_CENTRE_MODEL,
        EvidenceStage.COMPLETION_GIVEN_CENTRE: EvidenceModelRole.COMPLETION_MODEL,
        EvidenceStage.STEREO: EvidenceModelRole.STEREO_MODEL,
        EvidenceStage.ROUTE_CONTEXT: EvidenceModelRole.FULL_EVIDENCE_ENSEMBLE,
    }[stage]


def _ui_application_paths() -> tuple[Path, Path]:
    source_root = Path(__file__).resolve().parents[3]
    source_home = source_root / "app" / "Home.py"
    if source_home.exists():
        return source_root, source_home
    package_root = Path(__file__).resolve().parents[1]
    return package_root, package_root / "ui_app" / "Home.py"


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


@app.command("parse-reactseq")
def parse_reactseq(
    input_path: Annotated[Path, typer.Option("--input", exists=True, dir_okay=False)],
    product: Annotated[Path, typer.Option("--product", exists=True, dir_okay=False)],
    json_path: JsonPath = None,
    reaction_id: Annotated[str | None, typer.Option("--reaction-id")] = None,
) -> None:
    """Parse the pinned source-inspected ReactSeq subset into canonical ReactionIR."""
    normalized = _run(
        "parse-reactseq",
        None,
        lambda: normalize_reaction_source(
            ReactionSourceKind.REACTSEQ,
            _text(input_path),
            mapped_product_smiles=_text(product),
            reaction_id=reaction_id,
        ),
    )
    _emit_payload(normalized.reaction_ir, json_path)
    if json_path is None:
        console.print(Panel("Token-to-atom traversal mapping preserved in parser details."))


@app.command("normalize-reaction")
def normalize_reaction(
    input_path: Annotated[Path, typer.Option("--input", exists=True, dir_okay=False)],
    source_kind: Annotated[ReactionSourceKind, typer.Option("--representation")],
    product: Annotated[Path | None, typer.Option("--product", exists=True, dir_okay=False)] = None,
    product_smiles: Annotated[str | None, typer.Option("--product-smiles")] = None,
    reaction_id: Annotated[str | None, typer.Option("--reaction-id")] = None,
    json_path: JsonPath = None,
) -> None:
    """Normalize an explicitly named source representation without hidden mapping."""
    normalized = _run(
        "normalize-reaction",
        None,
        lambda: normalize_reaction_source(
            source_kind,
            input_path.read_text(encoding="utf-8"),
            mapped_product_smiles=_optional_product(product, product_smiles),
            reaction_id=reaction_id,
        ),
    )
    _emit_payload(normalized.reaction_ir, json_path)


@app.command("execute-reaction")
def execute_reaction(
    input_path: Annotated[Path, typer.Option("--input", exists=True, dir_okay=False)],
    mode: Annotated[SanitationMode, typer.Option("--mode")] = SanitationMode.STRICT,
    html_path: Annotated[Path | None, typer.Option("--html", dir_okay=False)] = None,
    json_path: JsonPath = None,
) -> None:
    """Execute a ReactionIR transaction through centre, completion, and stereo stages."""

    def action() -> object:
        reaction = load_reaction_ir(input_path)
        execution = ReactionExecutor().execute(reaction, mode=mode)
        if html_path is not None:
            reaction_audit = ReactionAuditor().audit(reaction)
            report = ReactionReportV1(
                reaction=reaction,
                audit=reaction_audit,
                limitations=(
                    "This report was requested from execute-reaction; model evidence was not run.",
                ),
                provenance=report_provenance("execute-reaction-report"),
            )
            write_reaction_report(
                html_path,
                report,
                json_path=_safe_report_sidecar(html_path, input_path),
            )
        return execution

    result = _run("execute-reaction", json_path, action)
    if not cast(Any, result).success:
        raise typer.Exit(code=3)


@app.command("compare-representations")
def compare_representations_command(
    reactseq: Annotated[Path, typer.Option("--reactseq", exists=True, dir_okay=False)],
    reactionjson: Annotated[Path, typer.Option("--reactionjson", exists=True, dir_okay=False)],
    product: Annotated[Path, typer.Option("--product", exists=True, dir_okay=False)],
    json_path: JsonPath = None,
) -> None:
    """Compare ReactSeq with ReactionIR or an explicitly namespaced paper-draft payload."""

    def action() -> object:
        mapped_product = _text(product)
        left = normalize_reaction_source(
            ReactionSourceKind.REACTSEQ,
            reactseq.read_text(encoding="utf-8"),
            mapped_product_smiles=mapped_product,
        )
        right_payload = read_json(reactionjson)
        if not isinstance(right_payload, dict):
            raise ValueError("reactionjson input must be a JSON object")
        schema_version = right_payload.get("schema_version")
        if schema_version == "synthaudit.reaction-ir/1":
            right = normalize_reaction_source(
                ReactionSourceKind.REACTION_IR,
                reactionjson.read_text(encoding="utf-8"),
            )
            right_name = "reaction_ir"
        elif schema_version == ReactionSourceKind.SYNTHEX_PAPER_DRAFT.value:
            right = normalize_reaction_source(
                ReactionSourceKind.SYNTHEX_PAPER_DRAFT,
                reactionjson.read_text(encoding="utf-8"),
                mapped_product_smiles=mapped_product,
            )
            right_name = ReactionSourceKind.SYNTHEX_PAPER_DRAFT.value
        else:
            raise ValueError(
                "official SynthEx ReactionJSON is unavailable; input must be ReactionIR or "
                "explicitly declare synthaudit.synthex-paper-draft/0.1"
            )
        return compare_representations(
            left.reaction_ir,
            right.reaction_ir,
            left_representation="reactseq",
            right_representation=right_name,
            unsupported_cases=right.unsupported_fields,
        )

    result = _run("compare-representations", json_path, action)
    if cast(Any, result).classification in {"different", "unsupported", "indeterminate"}:
        raise typer.Exit(code=3)


@app.command("audit-reaction")
def audit_reaction(
    input_path: Annotated[Path, typer.Option("--input", exists=True, dir_okay=False)],
    html_path: Annotated[Path | None, typer.Option("--html", dir_okay=False)] = None,
    index_path: Annotated[
        Path | None, typer.Option("--reference-index", exists=True, dir_okay=False)
    ] = None,
    evidence_path: Annotated[
        Path | None, typer.Option("--evidence", exists=True, dir_okay=False)
    ] = None,
    json_path: JsonPath = None,
) -> None:
    """Audit one ReactionIR and optionally render a full standalone report."""

    def action() -> object:
        reaction = load_reaction_ir(input_path)
        audit = ReactionAuditor().audit(reaction)
        if html_path is not None:
            novelty = None
            precedents = None
            corpus_versions: tuple[str, ...] = ()
            if index_path is not None:
                index = ReferenceIndex.load(index_path)
                novelty = MultiViewNoveltyEngine(index).score(reaction)
                precedents = PrecedentRetriever(index).search(reaction)
                corpus_versions = (f"{index.manifest.corpus_id}@{index.manifest.corpus_version}",)
            evidence = _load_report_evidence(evidence_path)
            report = ReactionReportV1(
                reaction=reaction,
                audit=audit,
                novelty=novelty,
                precedents=precedents,
                evidence=evidence,
                model_versions=tuple(
                    sorted({item.model_id for item in evidence if item.model_id is not None})
                ),
                corpus_versions=corpus_versions,
                provenance=report_provenance("audit-reaction-report"),
            )
            write_reaction_report(
                html_path,
                report,
                json_path=_safe_report_sidecar(html_path, input_path, index_path, evidence_path),
            )
        return audit

    result = _run("audit-reaction", json_path, action)
    if cast(Any, result).blocking:
        raise typer.Exit(code=3)


@app.command("audit-route")
def audit_route(
    input_path: Annotated[Path, typer.Option("--input", exists=True, dir_okay=False)],
    step_evidence_path: Annotated[
        Path | None, typer.Option("--step-evidence", exists=True, dir_okay=False)
    ] = None,
    html_path: Annotated[Path | None, typer.Option("--html", dir_okay=False)] = None,
    high_novelty_threshold: Annotated[float, typer.Option("--high-novelty-threshold")] = 0.7,
    high_uncertainty_threshold: Annotated[
        float | None, typer.Option("--high-uncertainty-threshold")
    ] = None,
    exploratory_naive_independence: Annotated[
        bool, typer.Option("--exploratory-naive-independence")
    ] = False,
    json_path: JsonPath = None,
) -> None:
    """Audit dependency, continuity, conditions, and independent per-step evidence."""

    def action() -> object:
        route = load_route_ir(input_path)
        evidence = _load_step_evidence(step_evidence_path)
        audit = RouteAuditor().audit(
            route,
            step_evidence=evidence,
            high_novelty_threshold=high_novelty_threshold,
            high_uncertainty_threshold=high_uncertainty_threshold,
            compute_exploratory_naive_independence_score=exploratory_naive_independence,
        )
        if html_path is not None:
            report = RouteReportV1(
                route=route,
                audit=audit,
                step_evidence=evidence,
                provenance=report_provenance("audit-route-report"),
            )
            write_route_report(
                html_path,
                report,
                json_path=_safe_report_sidecar(html_path, input_path, step_evidence_path),
            )
        return audit

    result = _run("audit-route", json_path, action)
    if cast(Any, result).blocking:
        raise typer.Exit(code=3)


@precedent_app.command("search")
def precedent_search(
    input_path: Annotated[Path, typer.Option("--input", exists=True, dir_okay=False)],
    index_path: Annotated[Path, typer.Option("--index", exists=True, dir_okay=False)],
    top_k: Annotated[int, typer.Option("--top-k", min=1)] = 10,
    json_path: JsonPath = None,
) -> None:
    """Search six separate precedent axes in a local content-addressed index."""
    _run(
        "precedent search",
        json_path,
        lambda: PrecedentRetriever(ReferenceIndex.load(index_path)).search(
            load_reaction_ir(input_path), top_k=top_k
        ),
    )


@novelty_app.command("score")
def novelty_score(
    input_path: Annotated[Path, typer.Option("--input", exists=True, dir_okay=False)],
    index_path: Annotated[Path, typer.Option("--index", exists=True, dir_okay=False)],
    top_k_precedents: Annotated[int, typer.Option("--top-k-precedents", min=1)] = 5,
    json_path: JsonPath = None,
) -> None:
    """Score independent novelty views; never compute plausibility as one minus novelty."""
    _run(
        "novelty score",
        json_path,
        lambda: MultiViewNoveltyEngine(ReferenceIndex.load(index_path)).score(
            load_reaction_ir(input_path), top_k_precedents=top_k_precedents
        ),
    )


@data_app.command("download")
def data_download(
    manifest: Annotated[Path, typer.Option("--manifest", exists=True, dir_okay=False)],
    output_dir: Annotated[Path, typer.Option("--output-dir", file_okay=False)],
    allow_network: Annotated[bool, typer.Option("--allow-network")] = False,
    overwrite: Annotated[bool, typer.Option("--overwrite")] = False,
    json_path: JsonPath = None,
) -> None:
    """Fetch only explicitly declared, licensed, checksum-pinned artifacts."""
    _run(
        "data download",
        json_path,
        lambda: download_from_manifest(
            manifest,
            output_dir,
            allow_network=allow_network,
            overwrite=overwrite,
        ),
    )


@data_app.command("prepare")
def data_prepare(
    records: Annotated[Path, typer.Option("--records", exists=True, dir_okay=False)],
    output: Annotated[Path, typer.Option("--output", dir_okay=False)],
    corpus_id: Annotated[str, typer.Option("--corpus-id")],
    corpus_version: Annotated[str, typer.Option("--corpus-version")],
    json_path: JsonPath = None,
) -> None:
    """Build a deterministic local precedent index from strict reference JSONL."""

    def action() -> object:
        index = prepare_reference_index(
            records,
            output,
            corpus_id=corpus_id,
            corpus_version=corpus_version,
        )
        return index.artifact

    _run("data prepare", json_path, action)


@benchmark_app.command("build")
def benchmark_build(
    kind: Annotated[str, typer.Option("--kind", help="counterfactual or prompt")],
    output_dir: Annotated[Path, typer.Option("--output-dir", file_okay=False)],
    json_path: JsonPath = None,
) -> None:
    """Regenerate a deterministic authored software fixture from the source checkout."""

    def action() -> object:
        if kind not in {"counterfactual", "prompt"}:
            raise ValueError("benchmark kind must be 'counterfactual' or 'prompt'")
        root = Path(__file__).resolve().parents[3]
        script = root / "scripts" / f"build_{kind}_fixture.py"
        if not script.exists():
            raise FileNotFoundError(
                "fixture builder is available only in a SynthAudit source checkout"
            )
        completed = subprocess.run(
            [sys.executable, str(script), "--output-dir", str(output_dir.resolve())],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or "benchmark builder failed")
        summary: JsonValue = {"metrics_status": "not_run"}
        if completed.stdout.strip():
            last_line = completed.stdout.strip().splitlines()[-1]
            try:
                summary = cast(JsonValue, json.loads(last_line))
            except json.JSONDecodeError:
                summary = {"builder_output": completed.stdout.strip(), "metrics_status": "not_run"}
        return {
            "kind": kind,
            "output_dir": str(output_dir.resolve()),
            "summary": summary,
            "interpretation": "Authored software-verification fixture; not experimental evidence.",
        }

    _run("benchmark build", json_path, action)


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


@benchmark_app.command("counterfactuals")
def counterfactual_benchmark(
    records: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    manifest: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    splits: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    human_review: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Validate content hashes, label contracts, grouped splits, and review rows."""
    result = validate_benchmark_artifacts(
        records_path=records,
        manifest_path=manifest,
        splits_path=splits,
        human_review_path=human_review,
    )
    if json_output:
        typer.echo(result.model_dump_json())
    else:
        console.print(result.model_dump(mode="json"))


@benchmark_app.command("evidence-model-contract")
def evidence_model_contract(
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Exercise model/calibration/uncertainty contracts on authored numeric fixtures."""
    result = run_evidence_model_contract_smoke()
    if json_output:
        typer.echo(result.model_dump_json())
    else:
        console.print(result.model_dump(mode="json"))


@benchmark_app.command("prompt-cases")
def prompt_cases(
    cases: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    manifest: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Validate content-addressed prompt cases without invoking a model provider."""
    result = validate_prompt_benchmark_artifacts(cases_path=cases, manifest_path=manifest)
    if json_output:
        typer.echo(result.model_dump_json())
    else:
        console.print(result.model_dump(mode="json"))


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


@benchmark_app.command("route-prompt-contract")
def route_prompt_contract(
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Exercise route and prompt contracts without running external model experiments."""
    result = run_route_prompt_contract_smoke()
    if json_output:
        typer.echo(result.model_dump_json())
    else:
        console.print(result.model_dump(mode="json"))


@app.command("train")
def train(
    examples_path: Annotated[Path, typer.Option("--examples", exists=True, dir_okay=False)],
    artifact_path: Annotated[Path, typer.Option("--artifact", dir_okay=False)],
    stage: Annotated[EvidenceStage, typer.Option("--stage")],
    estimator: Annotated[EstimatorFamily, typer.Option("--estimator")] = (
        EstimatorFamily.LOGISTIC_REGRESSION
    ),
    calibration: Annotated[CalibrationMethod, typer.Option("--calibration")] = (
        CalibrationMethod.PLATT
    ),
    random_seed: Annotated[int, typer.Option("--seed", min=0)] = 20260831,
    json_path: JsonPath = None,
) -> None:
    """Fit a stage evidence model using train and disjoint calibration groups only."""

    def action() -> object:
        examples = _load_examples(examples_path)
        train_examples = tuple(
            item
            for item in examples
            if item.stage == stage and item.split == EvidenceExampleSplit.TRAIN
        )
        calibration_examples = tuple(
            item
            for item in examples
            if item.stage == stage and item.split == EvidenceExampleSplit.CALIBRATION
        )
        fitted = fit_evidence_model(
            train_examples,
            calibration_examples if calibration != CalibrationMethod.NONE else (),
            stage=stage,
            role=_role_for_stage(stage),
            estimator_family=estimator,
            calibration_method=calibration,
            random_seed=random_seed,
        )
        return save_evidence_model(fitted, artifact_path)

    _run("train", json_path, action)


@app.command("evaluate")
def evaluate(
    examples_path: Annotated[Path, typer.Option("--examples", exists=True, dir_okay=False)],
    artifact_path: Annotated[Path, typer.Option("--artifact", exists=True, dir_okay=False)],
    manifest_path: Annotated[Path, typer.Option("--manifest", exists=True, dir_okay=False)],
    split: Annotated[EvidenceExampleSplit, typer.Option("--split")] = EvidenceExampleSplit.TEST,
    scope: Annotated[str, typer.Option("--scope")] = "software_verification_fixture",
    trust_model_artifact: Annotated[bool, typer.Option("--trust-model-artifact")] = False,
    json_path: JsonPath = None,
) -> None:
    """Evaluate calibrated evidence support on a held-out, explicitly selected split."""

    def action() -> object:
        model, descriptor = load_evidence_model(
            artifact_path,
            manifest_path,
            trust_artifact=trust_model_artifact,
        )
        examples = tuple(
            item
            for item in _load_examples(examples_path)
            if item.split == split and item.stage == model.manifest.stage
        )
        if not examples:
            raise ValueError("no examples match the model stage and requested evaluation split")
        scored = model.score(examples)
        if scored.calibrated_scores is None:
            raise ValueError("evaluation requires held-out calibrated evidence scores")
        return evaluate_evidence_scores(
            examples,
            scored.calibrated_scores.tolist(),
            [False] * len(examples),
            evaluation_id=f"cli-{descriptor.model_manifest.model_id}-{split.value}",
            model_id=descriptor.model_manifest.model_id,
            split=split,
            scope=scope,
        )

    _run("evaluate", json_path, action)


@app.command("report")
def report(
    output: Annotated[Path, typer.Option("--output", dir_okay=False)],
    reaction_path: Annotated[
        Path | None, typer.Option("--reaction", exists=True, dir_okay=False)
    ] = None,
    route_path: Annotated[Path | None, typer.Option("--route", exists=True, dir_okay=False)] = None,
    reference_index: Annotated[
        Path | None, typer.Option("--reference-index", exists=True, dir_okay=False)
    ] = None,
    evidence_path: Annotated[
        Path | None, typer.Option("--evidence", exists=True, dir_okay=False)
    ] = None,
    json_path: JsonPath = None,
) -> None:
    """Generate a complete reaction or route HTML report with a JSON sidecar."""

    def action() -> object:
        if (reaction_path is None) == (route_path is None):
            raise ValueError("provide exactly one of --reaction or --route")
        if reaction_path is not None:
            reaction = load_reaction_ir(reaction_path)
            audit = ReactionAuditor().audit(reaction)
            novelty = None
            precedents = None
            corpus_versions: tuple[str, ...] = ()
            if reference_index is not None:
                index = ReferenceIndex.load(reference_index)
                novelty = MultiViewNoveltyEngine(index).score(reaction)
                precedents = PrecedentRetriever(index).search(reaction)
                corpus_versions = (f"{index.manifest.corpus_id}@{index.manifest.corpus_version}",)
            evidence = _load_report_evidence(evidence_path)
            report_model = ReactionReportV1(
                reaction=reaction,
                audit=audit,
                novelty=novelty,
                precedents=precedents,
                evidence=evidence,
                model_versions=tuple(
                    sorted({item.model_id for item in evidence if item.model_id is not None})
                ),
                corpus_versions=corpus_versions,
                provenance=report_provenance("report-command/reaction"),
            )
            html_file, sidecar = write_reaction_report(
                output,
                report_model,
                json_path=_safe_report_sidecar(
                    output, reaction_path, reference_index, evidence_path
                ),
            )
        else:
            assert route_path is not None
            route = load_route_ir(route_path)
            route_evidence = _load_step_evidence(evidence_path)
            route_audit = RouteAuditor().audit(route, step_evidence=route_evidence)
            route_report = RouteReportV1(
                route=route,
                audit=route_audit,
                step_evidence=route_evidence,
                provenance=report_provenance("report-command/route"),
            )
            html_file, sidecar = write_route_report(
                output,
                route_report,
                json_path=_safe_report_sidecar(output, route_path, evidence_path),
            )
        return {
            "html": str(html_file),
            "json_sidecar": str(sidecar),
            "standalone": True,
            "external_assets": False,
            "notice": SCIENTIFIC_NOTICE,
        }

    _run("report", json_path, action)


@app.command("ui")
def ui(
    check: Annotated[
        bool, typer.Option("--check", help="Validate UI availability and exit.")
    ] = False,
    host: Annotated[str, typer.Option("--host")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port", min=1, max=65535)] = 8501,
    json_path: JsonPath = None,
) -> None:
    """Launch the five-page Streamlit workspace; use --check for an offline smoke test."""
    root, home = _ui_application_paths()
    pages = tuple(sorted((home.parent / "pages").glob("*.py")))
    payload = {
        "home": str(home),
        "page_count": 1 + len(pages),
        "pages": [home.name, *(item.name for item in pages)],
        "streamlit_importable": False,
        "notice": SCIENTIFIC_NOTICE,
    }
    try:
        import streamlit  # noqa: F401

        payload["streamlit_importable"] = True
    except ImportError:
        pass
    if check:
        if not home.exists() or payload["page_count"] != 5 or not payload["streamlit_importable"]:
            _run(
                "ui",
                json_path,
                lambda: (_ for _ in ()).throw(
                    RuntimeError("five-page Streamlit UI or optional dependency is unavailable")
                ),
            )
        _emit_payload(payload, json_path)
        return
    if not home.exists():
        raise typer.BadParameter("Streamlit app is unavailable outside the source checkout")
    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(home),
        "--server.address",
        host,
        "--server.port",
        str(port),
    ]
    raise typer.Exit(code=subprocess.run(command, cwd=root, check=False).returncode)


def main() -> None:
    """Invoke the Typer application."""
    app()
