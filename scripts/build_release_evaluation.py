"""Generate the deterministic v1.0 offline evaluation evidence package."""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import io
import json
from pathlib import Path

from synthaudit import SCIENTIFIC_NOTICE
from synthaudit.evaluation import (
    EvaluationAvailability,
    ReleaseEvaluationManifestV1,
    run_release_evaluation,
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _csv(fieldnames: tuple[str, ...], rows: list[dict[str, object]]) -> str:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def _rq_status_svg(manifest: ReleaseEvaluationManifestV1) -> str:
    questions = manifest.research_questions
    rows = []
    for index, item in enumerate(questions):
        y = 108 + index * 58
        fixture = item.status == EvaluationAvailability.FIXTURE_OBSERVATION
        fill = "#2563eb" if fixture else "#475569"
        status = "FIXTURE-ONLY EVIDENCE" if fixture else "RESEARCH NOT RUN"
        rows.append(
            f'<g><rect x="178" y="{y - 25}" width="380" height="40" rx="8" fill="{fill}"/>'
            f'<text x="30" y="{y}" class="rq">{html.escape(item.question_id)}</text>'
            f'<text x="368" y="{y}" text-anchor="middle" class="status">{status}</text></g>'
        )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="620" height="570" viewBox="0 0 620 570" role="img" aria-labelledby="title desc">
<title id="title">Research-question evidence availability for SynthAudit v1.0</title>
<desc id="desc">RQ1 and RQ6 have authored fixture-only software evidence. RQ2, RQ3, RQ4, RQ5, and RQ7 research evaluations were not run.</desc>
<style>text{{font-family:system-ui,-apple-system,sans-serif;fill:#e2e8f0}}.title{{font-size:22px;font-weight:700}}.sub{{font-size:13px;fill:#cbd5e1}}.rq{{font-size:16px;font-weight:700}}.status{{font-size:12px;font-weight:700;letter-spacing:.04em}}</style>
<rect width="620" height="570" rx="16" fill="#0f172a"/>
<text x="30" y="40" class="title">RQ evidence availability · v1.0</text>
<text x="30" y="66" class="sub">Status map only — not scientific performance or feasibility evidence</text>
{"".join(rows)}
<text x="30" y="542" class="sub">Blue = fixture-only software observation · Slate = required research inputs unavailable</text>
</svg>
"""


def _fixture_scope_svg(manifest: ReleaseEvaluationManifestV1) -> str:
    observations = (
        (
            "Counterfactual contract",
            str(manifest.counterfactual_validation.record_count),
            "records",
        ),
        ("Prompt contract", str(manifest.prompt_validation.variant_count), "variants"),
        ("ReactSeq conformance", str(manifest.reactseq_conformance.fixture_count), "pinned cases"),
        (
            "Route perturbations",
            str(manifest.route_prompt_contract.route_perturbation_count),
            "authored classes",
        ),
    )
    cards = []
    for index, (label, value, unit) in enumerate(observations):
        x = 30 + (index % 2) * 300
        y = 105 + (index // 2) * 145
        cards.append(
            f'<g><rect x="{x}" y="{y}" width="270" height="112" rx="12" fill="#111827" stroke="#334155"/>'
            f'<text x="{x + 18}" y="{y + 30}" class="label">{html.escape(label)}</text>'
            f'<text x="{x + 18}" y="{y + 72}" class="value">{html.escape(value)}</text>'
            f'<text x="{x + 90}" y="{y + 72}" class="unit">{html.escape(unit)}</text></g>'
        )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="630" height="430" viewBox="0 0 630 430" role="img" aria-labelledby="title desc">
<title id="title">Scope of committed SynthAudit software-verification fixtures</title>
<desc id="desc">The release validates 200 counterfactual records, 40 prompt variants, three pinned ReactSeq cases, and five authored route perturbation classes. Counts describe software fixtures, not chemistry performance.</desc>
<style>text{{font-family:system-ui,-apple-system,sans-serif;fill:#e2e8f0}}.title{{font-size:21px;font-weight:700}}.sub,.unit{{font-size:13px;fill:#cbd5e1}}.label{{font-size:14px;font-weight:650;fill:#93c5fd}}.value{{font-size:34px;font-weight:750;fill:#f8fafc}}.unit{{font-weight:600}}</style>
<rect width="630" height="430" rx="16" fill="#0b1220"/>
<text x="30" y="40" class="title">Committed offline fixture scope</text>
<text x="30" y="66" class="sub">Observed artifact counts — not population metrics or experimental outcomes</text>
{"".join(cards)}
<text x="30" y="408" class="sub">All inputs are authored or pinned, content-addressed, and reproducible without a provider.</text>
</svg>
"""


def _readme(manifest: ReleaseEvaluationManifestV1) -> str:
    return f"""# SynthAudit v1.0 offline evaluation evidence

> {SCIENTIFIC_NOTICE}

This directory is generated by `make release-evaluation`. It records everything the locked,
offline repository can actually observe and keeps unavailable research studies as `not_run`.

## What ran

- {manifest.counterfactual_validation.record_count} content-addressed counterfactual records were
  validated as an authored software fixture.
- {manifest.prompt_validation.variant_count} deterministic prompt variants were validated; no
  prompt model was invoked.
- {manifest.reactseq_conformance.fixture_count} pinned ReactSeq demo cases were parsed and executed.
- {manifest.route_prompt_contract.route_perturbation_count} authored route perturbation classes
  were checked by the route contract.
- Four evidence-model stage contracts were exercised on authored numeric data; their scientific
  metrics remain non-reportable.

## Files

- `manifest.json`: typed source hashes, complete RQ1-RQ7 status, and required-metric status;
- `tables/research-question-status.csv`: evidence availability and blockers by question;
- `tables/required-metric-status.csv`: observed fixture values or explicit `not_run` entries;
- `tables/software-fixture-observations.csv`: artifact and contract counts only;
- `figures/*.svg`: accessible status/scope figures generated from the manifest;
- `SHA256SUMS`: digests for every generated file except the checksum list itself.

Fixture observations do not answer population research questions, establish experimental
feasibility, or justify model selection.

See the [v1.0 technical report](../../docs/TECHNICAL_REPORT.md) for the complete RQ1-RQ7
interpretation and threats to validity.
"""


def build(source_root: Path, output_dir: Path) -> tuple[Path, ...]:
    manifest = run_release_evaluation(source_root)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "manifest.json"
    _write(
        manifest_path,
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
    )

    rq_rows = [
        {
            "research_question": item.question_id,
            "status": item.status.value,
            "evidence_summary": item.evidence_summary,
            "blocking_requirements": " | ".join(item.blocking_requirements),
            "reproduction_command": item.reproduction_command,
        }
        for item in manifest.research_questions
    ]
    rq_path = output_dir / "tables" / "research-question-status.csv"
    _write(
        rq_path,
        _csv(
            (
                "research_question",
                "status",
                "evidence_summary",
                "blocking_requirements",
                "reproduction_command",
            ),
            rq_rows,
        ),
    )

    metric_rows = [
        {
            "metric": item.metric_id,
            "status": item.status.value,
            "value": "" if item.value is None else f"{item.value:.12g}",
            "numerator": "" if item.numerator is None else item.numerator,
            "denominator": "" if item.denominator is None else item.denominator,
            "sample_count": "" if item.sample_count is None else item.sample_count,
            "unit": item.unit or "",
            "scope": item.scope,
            "confidence_interval_95": "",
            "bootstrap_unit": item.bootstrap_unit,
            "bootstrap_status": item.bootstrap_status,
            "reason": item.reason,
            "reproduction_command": item.reproduction_command,
        }
        for item in manifest.required_metrics
    ]
    metrics_path = output_dir / "tables" / "required-metric-status.csv"
    _write(
        metrics_path,
        _csv(
            (
                "metric",
                "status",
                "value",
                "numerator",
                "denominator",
                "sample_count",
                "unit",
                "scope",
                "confidence_interval_95",
                "bootstrap_unit",
                "bootstrap_status",
                "reason",
                "reproduction_command",
            ),
            metric_rows,
        ),
    )

    fixture_rows = [
        {
            "observation": "counterfactual_records_validated",
            "value": manifest.counterfactual_validation.record_count,
            "unit": "authored_records",
            "scope": "software_verification_fixture",
            "interpretation": "Artifact/schema/split validation only; not observed chemistry errors.",
        },
        {
            "observation": "counterfactual_generation_methods_covered",
            "value": manifest.counterfactual_validation.method_count,
            "unit": "declared_methods",
            "scope": "software_verification_fixture",
            "interpretation": "Designed method coverage; not measured error prevalence.",
        },
        {
            "observation": "prompt_variants_validated",
            "value": manifest.prompt_validation.variant_count,
            "unit": "authored_variants",
            "scope": "software_verification_fixture",
            "interpretation": "No prompt-capable model was invoked.",
        },
        {
            "observation": "reactseq_pinned_cases",
            "value": manifest.reactseq_conformance.fixture_count,
            "unit": "pinned_demo_cases",
            "scope": "software_verification_fixture",
            "interpretation": manifest.reactseq_conformance.interpretation,
        },
        {
            "observation": "alternate_traversal_pairs_checked",
            "value": 1,
            "unit": "authored_pair",
            "scope": "software_verification_fixture",
            "interpretation": "Semantic-hash invariance for one pair; not a population rate.",
        },
        {
            "observation": "route_perturbation_classes_detected",
            "value": manifest.route_prompt_contract.route_perturbation_count,
            "unit": "authored_classes",
            "scope": "software_verification_fixture",
            "interpretation": "Contract detection only; not route feasibility validation.",
        },
        {
            "observation": "evidence_stage_contracts_exercised",
            "value": manifest.evidence_model_contract.stage_model_count,
            "unit": "stage_contracts",
            "scope": "software_verification_fixture",
            "interpretation": "Authored numeric plumbing; no reportable model performance.",
        },
    ]
    fixture_path = output_dir / "tables" / "software-fixture-observations.csv"
    _write(
        fixture_path,
        _csv(("observation", "value", "unit", "scope", "interpretation"), fixture_rows),
    )

    rq_figure = output_dir / "figures" / "research-question-status.svg"
    scope_figure = output_dir / "figures" / "software-fixture-scope.svg"
    _write(rq_figure, _rq_status_svg(manifest))
    _write(scope_figure, _fixture_scope_svg(manifest))
    readme = output_dir / "README.md"
    _write(readme, _readme(manifest))

    generated = (
        readme,
        manifest_path,
        rq_path,
        metrics_path,
        fixture_path,
        rq_figure,
        scope_figure,
    )
    checksum_path = output_dir / "SHA256SUMS"
    checksum_lines = [
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(output_dir)}"
        for path in sorted(generated)
    ]
    _write(checksum_path, "\n".join(checksum_lines) + "\n")
    return (*generated, checksum_path)


def _parser() -> argparse.ArgumentParser:
    repository = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=repository)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=repository / "reports" / "research-evaluation-v1",
    )
    return parser


def main() -> None:
    arguments = _parser().parse_args()
    generated = build(arguments.source_root.resolve(), arguments.output_dir.resolve())
    print(
        json.dumps(
            {
                "generated_files": len(generated),
                "output_dir": str(arguments.output_dir.resolve()),
                "research_metrics_status": "not_run",
                "notice": SCIENTIFIC_NOTICE,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
