from __future__ import annotations

import hashlib
import json
from pathlib import Path

from typer.testing import CliRunner

from synthaudit.cli.app import app
from synthaudit.data import DataDownloadManifestV1
from synthaudit.models.evidence import (
    EvidenceExampleSplit,
    EvidenceExampleV1,
    EvidenceFeatureV1,
    EvidenceStage,
    FeatureGroup,
)
from synthaudit.precedent.models import ReferenceReactionV1
from synthaudit.schema.common import ProvenanceRecord
from synthaudit.schema.evidence import EvidenceAvailability
from synthaudit.ui.workspace import DEMO_REACTION_SMILES, demo_reaction

runner = CliRunner()
PROVENANCE = (
    ProvenanceRecord(
        source="authored-cli-test",
        source_version="1",
        license="Apache-2.0 fixture; not experimental evidence",
    ),
)


def test_top_level_and_nested_help_expose_complete_product_commands() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for name in (
        "parse-reactseq",
        "normalize-reaction",
        "execute-reaction",
        "compare-representations",
        "audit-reaction",
        "audit-route",
        "precedent",
        "novelty",
        "data",
        "benchmark",
        "train",
        "evaluate",
        "report",
        "ui",
    ):
        assert name in result.stdout
    for group, command in (
        ("precedent", "search"),
        ("novelty", "score"),
        ("data", "download"),
        ("data", "prepare"),
        ("benchmark", "build"),
        ("benchmark", "run"),
    ):
        nested = runner.invoke(app, [group, "--help"])
        assert nested.exit_code == 0
        assert command in nested.stdout


def test_normalize_execute_audit_and_report_workflow(tmp_path: Path) -> None:
    source = tmp_path / "reaction.smi"
    source.write_text(DEMO_REACTION_SMILES, encoding="utf-8")
    reaction_ir = tmp_path / "reaction.json"
    normalized = runner.invoke(
        app,
        [
            "normalize-reaction",
            "--input",
            str(source),
            "--representation",
            "mapped_reaction_smiles",
            "--reaction-id",
            "cli-workflow",
            "--json",
            str(reaction_ir),
        ],
    )
    assert normalized.exit_code == 0, normalized.output
    assert json.loads(reaction_ir.read_text())["schema_version"] == "synthaudit.reaction-ir/1"

    execution_path = tmp_path / "execution.json"
    executed = runner.invoke(
        app,
        ["execute-reaction", "--input", str(reaction_ir), "--json", str(execution_path)],
    )
    assert executed.exit_code == 0, executed.output
    assert json.loads(execution_path.read_text())["success"] is True

    audit_path = tmp_path / "audit.json"
    html_path = tmp_path / "reaction.html"
    audited = runner.invoke(
        app,
        [
            "audit-reaction",
            "--input",
            str(reaction_ir),
            "--html",
            str(html_path),
            "--json",
            str(audit_path),
        ],
    )
    assert audited.exit_code == 0, audited.output
    assert html_path.exists() and html_path.with_suffix(".report.json").exists()
    assert json.loads(audit_path.read_text())["blocking"] is False

    report_result = tmp_path / "report-result.json"
    report_html = tmp_path / "complete.html"
    rendered = runner.invoke(
        app,
        [
            "report",
            "--reaction",
            str(reaction_ir),
            "--output",
            str(report_html),
            "--json",
            str(report_result),
        ],
    )
    assert rendered.exit_code == 0, rendered.output
    assert json.loads(report_result.read_text())["standalone"] is True
    assert "Multi-view novelty" in report_html.read_text(encoding="utf-8")


def test_parse_reactseq_and_failure_output_are_explicit(tmp_path: Path) -> None:
    fixture = json.loads(Path("tests/fixtures/reactseq/golden.json").read_text())[0]
    reactseq = tmp_path / "example.reactseq"
    product = tmp_path / "product.smi"
    output = tmp_path / "reaction-ir.json"
    reactseq.write_text(fixture["reactseq"], encoding="utf-8")
    product.write_text(fixture["mapped_product_smiles"], encoding="utf-8")
    result = runner.invoke(
        app,
        [
            "parse-reactseq",
            "--input",
            str(reactseq),
            "--product",
            str(product),
            "--json",
            str(output),
        ],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(output.read_text())["stage_metadata"]["source_representation"] == "ReactSeq"

    comparison = tmp_path / "comparison.json"
    compared = runner.invoke(
        app,
        [
            "compare-representations",
            "--reactseq",
            str(reactseq),
            "--reactionjson",
            str(output),
            "--product",
            str(product),
            "--json",
            str(comparison),
        ],
    )
    assert compared.exit_code == 0, compared.output
    assert json.loads(comparison.read_text())["classification"] == "semantically_equivalent"

    unmapped = tmp_path / "unmapped.smi"
    unmapped.write_text("CCBr.O>>CCO", encoding="utf-8")
    failed = runner.invoke(
        app,
        [
            "normalize-reaction",
            "--input",
            str(unmapped),
            "--representation",
            "mapped_reaction_smiles",
            "--json",
            str(tmp_path / "error.json"),
        ],
    )
    assert failed.exit_code == 2
    assert "AtomMappingRequired" in failed.output


def test_route_ui_and_benchmark_boundaries(tmp_path: Path) -> None:
    route_path = tmp_path / "route.json"
    route_path.write_text(
        Path("examples/route-ir.json").read_text(encoding="utf-8"), encoding="utf-8"
    )
    result_path = tmp_path / "route-audit.json"
    html_path = tmp_path / "route.html"
    result = runner.invoke(
        app,
        [
            "audit-route",
            "--input",
            str(route_path),
            "--html",
            str(html_path),
            "--json",
            str(result_path),
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result_path.read_text())
    assert payload["blocking"] is False
    assert "route_success_probability" not in payload

    rendered = runner.invoke(
        app,
        [
            "report",
            "--route",
            str(route_path),
            "--output",
            str(tmp_path / "route-report.html"),
            "--json",
            str(tmp_path / "route-report-result.json"),
        ],
    )
    assert rendered.exit_code == 0, rendered.output
    assert json.loads((tmp_path / "route-report-result.json").read_text())["standalone"]

    ui_result = runner.invoke(app, ["ui", "--check", "--json", str(tmp_path / "ui.json")])
    assert ui_result.exit_code == 0, ui_result.output
    assert json.loads((tmp_path / "ui.json").read_text())["page_count"] == 5

    invalid_build = runner.invoke(
        app,
        [
            "benchmark",
            "build",
            "--kind",
            "unknown",
            "--output-dir",
            str(tmp_path / "benchmark"),
            "--json",
            str(tmp_path / "build-error.json"),
        ],
    )
    assert invalid_build.exit_code == 2
    assert "benchmark kind" in invalid_build.output

    built = runner.invoke(
        app,
        [
            "benchmark",
            "build",
            "--kind",
            "prompt",
            "--output-dir",
            str(tmp_path / "prompt-benchmark"),
            "--json",
            str(tmp_path / "built.json"),
        ],
    )
    assert built.exit_code == 0, built.output
    assert (tmp_path / "prompt-benchmark/cases.jsonl").exists()
    assert (
        json.loads((tmp_path / "built.json").read_text())["summary"]["metrics_status"] == "not_run"
    )


def test_data_cli_download_prepare_precedent_and_novelty(tmp_path: Path) -> None:
    source = tmp_path / "artifact.bin"
    source.write_bytes(b"local-data")
    manifest = DataDownloadManifestV1(
        dataset_id="cli-data",
        dataset_version="1",
        artifacts=(
            {
                "artifact_id": "local",
                "source_uri": source.as_uri(),
                "destination": "artifact.bin",
                "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "license_status": "CC0 fixture",
            },
        ),
        provenance=PROVENANCE,
    )
    manifest_path = tmp_path / "download-manifest.json"
    manifest_path.write_text(manifest.model_dump_json(), encoding="utf-8")
    download_json = tmp_path / "download.json"
    downloaded = runner.invoke(
        app,
        [
            "data",
            "download",
            "--manifest",
            str(manifest_path),
            "--output-dir",
            str(tmp_path / "data"),
            "--json",
            str(download_json),
        ],
    )
    assert downloaded.exit_code == 0, downloaded.output
    assert json.loads(download_json.read_text())["network_access_used"] is False

    reference = ReferenceReactionV1(
        source_dataset="cli-fixture",
        source_reaction_id="ref-1",
        data_license_status="Apache-2.0 fixture",
        reaction=demo_reaction(),
    )
    records = tmp_path / "references.jsonl"
    records.write_text(reference.model_dump_json() + "\n", encoding="utf-8")
    index = tmp_path / "index.json"
    prepared = runner.invoke(
        app,
        [
            "data",
            "prepare",
            "--records",
            str(records),
            "--output",
            str(index),
            "--corpus-id",
            "cli-fixture",
            "--corpus-version",
            "1",
            "--json",
            str(tmp_path / "prepared.json"),
        ],
    )
    assert prepared.exit_code == 0, prepared.output

    reaction_path = tmp_path / "query.json"
    reaction_path.write_text(demo_reaction().model_dump_json(), encoding="utf-8")
    for command, output_name in (("precedent", "precedent.json"), ("novelty", "novelty.json")):
        invoked = runner.invoke(
            app,
            [
                command,
                "search" if command == "precedent" else "score",
                "--input",
                str(reaction_path),
                "--index",
                str(index),
                "--json",
                str(tmp_path / output_name),
            ],
        )
        assert invoked.exit_code == 0, invoked.output
    novelty = json.loads((tmp_path / "novelty.json").read_text())
    assert novelty["structure_novelty"]["product_morgan"]["novelty"] == 0.0
    assert "plausibility" not in novelty


def _examples() -> tuple[EvidenceExampleV1, ...]:
    values: list[EvidenceExampleV1] = []
    for split, count in (
        (EvidenceExampleSplit.TRAIN, 8),
        (EvidenceExampleSplit.CALIBRATION, 4),
        (EvidenceExampleSplit.TEST, 4),
    ):
        for index in range(count):
            label = index % 2
            support = 0.8 if label else 0.2
            features = (
                EvidenceFeatureV1(
                    feature_id="structural.valid",
                    group=FeatureGroup.STRUCTURAL,
                    availability=EvidenceAvailability.AVAILABLE,
                    value=support,
                    interpretation="Authored software-fixture feature.",
                    provenance=PROVENANCE,
                ),
                EvidenceFeatureV1(
                    feature_id="centre.consistent",
                    group=FeatureGroup.REACTION_CENTRE,
                    availability=EvidenceAvailability.AVAILABLE,
                    value=support + (index % 2) * 0.01,
                    interpretation="Authored software-fixture feature.",
                    provenance=PROVENANCE,
                ),
            )
            values.append(
                EvidenceExampleV1(
                    example_id=f"{split.value}-{index}",
                    parent_group_id=f"{split.value}-parent-{index}",
                    split=split,
                    stage=EvidenceStage.REACTION_CENTRE,
                    target_label=label,
                    target_source="authored evidence-support annotation fixture",
                    features=features,
                    provenance=PROVENANCE,
                )
            )
    return tuple(values)


def test_train_and_evaluate_cli_use_explicit_trusted_artifact_boundary(tmp_path: Path) -> None:
    examples = tmp_path / "examples.jsonl"
    examples.write_text(
        "".join(item.model_dump_json() + "\n" for item in _examples()), encoding="utf-8"
    )
    artifact = tmp_path / "model.pkl"
    train_result = runner.invoke(
        app,
        [
            "train",
            "--examples",
            str(examples),
            "--artifact",
            str(artifact),
            "--stage",
            "reaction_centre_supported",
            "--json",
            str(tmp_path / "train.json"),
        ],
    )
    assert train_result.exit_code == 0, train_result.output
    descriptor = artifact.with_suffix(".manifest.json")
    assert artifact.exists() and descriptor.exists()

    refused = runner.invoke(
        app,
        [
            "evaluate",
            "--examples",
            str(examples),
            "--artifact",
            str(artifact),
            "--manifest",
            str(descriptor),
            "--json",
            str(tmp_path / "refused.json"),
        ],
    )
    assert refused.exit_code == 2
    assert "can execute code" in refused.output

    evaluation = tmp_path / "evaluation.json"
    evaluated = runner.invoke(
        app,
        [
            "evaluate",
            "--examples",
            str(examples),
            "--artifact",
            str(artifact),
            "--manifest",
            str(descriptor),
            "--trust-model-artifact",
            "--json",
            str(evaluation),
        ],
    )
    assert evaluated.exit_code == 0, evaluated.output
    payload = json.loads(evaluation.read_text())
    assert payload["sample_count"] == 4
    assert "experimental outcomes" in " ".join(payload["limitations"])
