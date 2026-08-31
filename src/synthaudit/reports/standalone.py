"""Accessible standalone HTML renderers with embedded CSS, SVG, and JSON sidecars."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, cast

from jinja2 import Environment, select_autoescape
from rdkit import Chem
from rdkit.Chem import Draw

from synthaudit import __version__
from synthaudit.novelty.models import MultiViewNoveltyResultV1, NoveltyMetricV1
from synthaudit.reports.models import ReactionReportV1, RouteReportV1
from synthaudit.schema.common import ProvenanceRecord
from synthaudit.schema.results import CheckResultV1, StageAuditResultV1
from synthaudit.schema.route_ir import RouteIRV1

_DEFAULT_LIMITATIONS = (
    "The report audits representation consistency and declared evidence, not laboratory feasibility.",
    "Unavailable evidence remains unavailable and is not converted into a favourable result.",
    "Novelty is corpus-relative and is not the inverse of plausibility.",
)

_CSS = """
:root { color-scheme:light; --primary:#1e3a5f; --secondary:#2563eb; --accent:#16803c;
  --background:#f8fafc; --surface:#ffffff; --foreground:#0f172a; --muted:#475569;
  --border:#cbd5e1; --danger:#b91c1c; --warning:#9a5800; --pass:#14733d;
  --space-1:.25rem; --space-2:.5rem; --space-3:1rem; --space-4:1.5rem;
  --space-5:2rem; --radius:.75rem; }
* { box-sizing:border-box; }
html { scroll-behavior:smooth; }
body { margin:0; background:var(--background); color:var(--foreground);
  font:16px/1.55 Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
main { width:min(1180px,calc(100% - 2rem)); margin:var(--space-4) auto; }
header,.panel { background:var(--surface); border:1px solid var(--border); border-radius:var(--radius);
  box-shadow:0 1px 2px rgba(15,23,42,.05); padding:var(--space-4); margin-bottom:var(--space-3); }
h1,h2,h3 { color:var(--primary); line-height:1.25; letter-spacing:-.02em; }
h1 { font-size:clamp(1.75rem,4vw,2.75rem); margin:.25rem 0; }
h2 { font-size:1.35rem; border-bottom:2px solid var(--border); padding-bottom:.5rem; }
h3 { font-size:1.05rem; }
.eyebrow { color:var(--secondary); font:600 .78rem/1.3 ui-monospace,SFMono-Regular,Menlo,monospace;
  letter-spacing:.08em; text-transform:uppercase; }
.notice { border-left:.35rem solid var(--primary); background:#eaf0f7; padding:.9rem 1rem;
  font-weight:650; margin:1rem 0 0; }
.grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(190px,1fr)); gap:var(--space-3); }
.metric { min-height:7rem; border:1px solid var(--border); border-radius:.55rem; padding:var(--space-3); }
.metric strong { display:block; color:var(--muted); font-size:.78rem; text-transform:uppercase;
  letter-spacing:.05em; }
.metric span { display:block; font-size:1.25rem; font-weight:750; margin-top:.35rem; }
.badge { display:inline-block; border:1px solid currentColor; border-radius:999px; padding:.15rem .55rem;
  font-size:.75rem; font-weight:750; text-transform:uppercase; letter-spacing:.04em; }
.pass { color:var(--pass); } .fail { color:var(--danger); }
.warning,.indeterminate,.unavailable,.unsupported { color:var(--warning); }
.table-wrap { max-width:100%; overflow-x:auto; }
table { width:100%; border-collapse:collapse; min-width:680px; }
th,td { border-bottom:1px solid var(--border); padding:.7rem .55rem; text-align:left; vertical-align:top; }
th { color:var(--muted); font-size:.75rem; letter-spacing:.05em; text-transform:uppercase; }
tbody tr:hover { background:#f1f5f9; }
code,pre { font:12px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace; overflow-wrap:anywhere; }
pre { white-space:pre-wrap; background:#f1f5f9; border:1px solid var(--border); border-radius:.5rem;
  padding:.8rem; max-height:32rem; overflow:auto; }
.molecule svg,.route-graph svg { display:block; width:100%; height:auto; max-height:360px; }
.empty { border:1px dashed var(--border); border-radius:.5rem; color:var(--muted); padding:1rem; }
.skip-link { position:absolute; left:-9999px; } .skip-link:focus { left:1rem; top:1rem; z-index:10;
  background:var(--surface); border:2px solid var(--primary); padding:.75rem; }
a { color:var(--secondary); } a:focus-visible { outline:3px solid var(--primary); outline-offset:3px; }
footer { color:var(--muted); border-top:1px solid var(--border); margin-top:2rem; padding:1rem 0 2rem; }
@media (max-width:600px) { main { width:min(100% - 1rem,1180px); margin:.5rem auto; }
  header,.panel { padding:1rem; border-radius:.5rem; } }
@media (prefers-reduced-motion:reduce) { html { scroll-behavior:auto; } *,*::before,*::after {
  animation-duration:.01ms!important; animation-iteration-count:1!important; transition-duration:.01ms!important; } }
@media print { body { background:#fff; font-size:11pt; } main { width:100%; margin:0; }
  header,.panel { box-shadow:none; break-inside:avoid; } .panel { border-color:#94a3b8; }
  a { color:inherit; text-decoration:none; } h2 { break-after:avoid; } }
"""


def _environment() -> Environment:
    return Environment(autoescape=select_autoescape(default=True))


def molecule_svg(structures: tuple[str, ...]) -> str:
    molecules: list[Chem.Mol] = []
    legends: list[str] = []
    for structure in structures:
        molecule = cast(Chem.Mol | None, Chem.MolFromSmiles(structure))
        if molecule is not None:
            molecules.append(molecule)
            legends.append(structure)
    if not molecules:
        return '<p class="empty">No parseable structure is available for drawing.</p>'
    drawing = Draw.MolsToGridImage(  # type: ignore[no-untyped-call]
        molecules,
        legends=legends,
        molsPerRow=min(3, len(molecules)),
        subImgSize=(320, 230),
        useSVG=True,
    )
    value = str(drawing)
    return value.replace("<svg ", '<svg role="img" aria-label="Molecular structures" ', 1)


def _stage_payload(title: str, stage: StageAuditResultV1) -> dict[str, Any]:
    return {
        "title": title,
        "stage": stage.stage,
        "status": stage.status.value,
        "checks": [_check_payload(item) for item in stage.checks],
    }


def _check_payload(item: CheckResultV1) -> dict[str, Any]:
    return {
        "check_id": item.check_id,
        "status": item.status.value,
        "severity": item.severity.value,
        "message": item.message,
        "atom_maps": ", ".join(map(str, item.affected_atom_maps)) or "—",
        "evidence": json.dumps(item.evidence, indent=2, sort_keys=True),
        "deterministic": "yes" if item.deterministic else "no",
    }


def _metric_payload(metric: NoveltyMetricV1) -> dict[str, Any]:
    return {
        "metric_id": metric.metric_id,
        "availability": metric.availability.value,
        "novelty": "—" if metric.novelty is None else f"{metric.novelty:.4f}",
        "maximum_similarity": (
            "—" if metric.maximum_similarity is None else f"{metric.maximum_similarity:.4f}"
        ),
        "nearest": ", ".join(metric.nearest_reference_ids) or "—",
        "interpretation": metric.interpretation,
        "missing": "; ".join(metric.missing_reasons) or "—",
    }


def _novelty_metrics(result: MultiViewNoveltyResultV1 | None) -> tuple[dict[str, Any], ...]:
    if result is None:
        return ()
    return tuple(
        _metric_payload(metric)
        for metric in (
            result.structure_novelty.product_morgan,
            result.structure_novelty.precursor_morgan,
            result.structure_novelty.product_scaffold,
            result.structure_novelty.precursor_scaffold,
            result.reaction_difference_novelty.reaction_difference,
            result.reaction_difference_novelty.changed_bond_and_atom,
            result.reaction_difference_novelty.drfp,
            result.edit_semantic_novelty.normalized_edit_signature,
            result.edit_semantic_novelty.reaction_centre_neighbourhood,
            result.edit_semantic_novelty.ring_change_profile,
            result.edit_semantic_novelty.fragmentation_profile,
            result.edit_semantic_novelty.attachment_profile,
            result.learned_transformation_novelty.reactseq_meo,
        )
    )


def route_svg(route: RouteIRV1) -> str:
    """Render a deterministic dependency graph as accessible inline SVG."""
    width = 900
    row_height = 105
    height = max(160, 70 + len(route.steps) * row_height)
    index_by_id = {step.step_id: index for index, step in enumerate(route.steps)}
    pieces = [
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-labelledby="route-title route-desc" xmlns="http://www.w3.org/2000/svg">',
        '<title id="route-title">Route dependency graph</title>',
        '<desc id="route-desc">Ordered route steps and declared dependency arrows.</desc>',
        '<defs><marker id="arrow" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto"><path d="M0,0 L10,3.5 L0,7 Z" fill="#64748b"/></marker></defs>',
    ]
    for step in route.steps:
        target_index = index_by_id[step.step_id]
        target_y = 45 + target_index * row_height
        for dependency in step.depends_on:
            source_index = index_by_id.get(dependency)
            if source_index is None:
                continue
            source_y = 45 + source_index * row_height
            pieces.append(
                f'<path d="M450 {source_y + 34} C650 {source_y + 34},650 {target_y},450 {target_y}" fill="none" stroke="#64748b" stroke-width="2" marker-end="url(#arrow)"/>'
            )
    for index, step in enumerate(route.steps):
        y = 25 + index * row_height
        status_label = "key step" if step.key_step else "route step"
        pieces.extend(
            (
                f'<g><rect x="55" y="{y}" width="395" height="72" rx="10" fill="#ffffff" stroke="#1e3a5f" stroke-width="2"/>',
                f'<text x="75" y="{y + 29}" fill="#0f172a" font-family="system-ui,sans-serif" font-size="17" font-weight="700">{html.escape(step.step_id)}</text>',
                f'<text x="75" y="{y + 53}" fill="#475569" font-family="system-ui,sans-serif" font-size="13">{html.escape(status_label)} · {len(step.reaction.core_edits)} centre edit(s)</text></g>',
            )
        )
    pieces.append("</svg>")
    return "".join(pieces)


_REACTION_TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SynthAudit reaction report — {{ report.reaction.reaction_id }}</title><style>{{ css | safe }}</style></head>
<body><a class="skip-link" href="#content">Skip to report content</a><main id="content">
<header><div class="eyebrow">SynthAudit · reaction report · schema v1</div><h1>{{ report.reaction.reaction_id }}</h1>
<p>A stage-separated audit of a declared retrosynthetic representation.</p><p class="notice">{{ report.notice }}</p></header>
<section class="panel"><h2>1. Input and source</h2><div class="grid">
<div class="metric"><strong>Source representation</strong><span>{{ source_representation }}</span></div>
<div class="metric"><strong>Execution</strong><span class="{{ execution_status }}">{{ execution_status }}</span></div>
<div class="metric"><strong>Structurally valid</strong><span>{{ report.audit.structurally_valid }}</span></div>
<div class="metric"><strong>Blocking</strong><span>{{ report.audit.blocking }}</span></div></div>
<pre>{{ source_json }}</pre></section>
<section class="panel"><h2>2. Representation normalization</h2><p>Canonical direction: mapped product → reaction-centre edits → completion → stereo.</p>
<pre>{{ normalization_json }}</pre></section>
<section class="panel"><h2>3. Product-to-synthon stage</h2><code>{{ product_smiles }}</code><div class="molecule">{{ product_svg | safe }}</div>
<p><code>{{ synthons }}</code></p><div class="molecule">{{ synthon_svg | safe }}</div></section>
<section class="panel"><h2>4. Synthon-to-precursor stage</h2><code>{{ completed }}</code><div class="molecule">{{ completion_svg | safe }}</div></section>
<section class="panel"><h2>5. Stereo analysis</h2><code>{{ final_structures }}</code><div class="molecule">{{ final_svg | safe }}</div></section>
<section class="panel"><h2>6. Structural alerts and stage checks</h2>
{% for stage in stages %}<div id="{{ stage.stage }}"><h3>{{ stage.title }}</h3>
<p><span class="badge {{ stage.status }}">{{ stage.status }}</span></p><div class="table-wrap"><table><thead><tr><th>Check</th><th>Status</th><th>Severity</th><th>Message</th><th>Atom maps</th><th>Deterministic</th><th>Evidence</th></tr></thead><tbody>
{% for item in stage.checks %}<tr><td><code>{{ item.check_id }}</code></td><td class="{{ item.status }}">{{ item.status }}</td><td>{{ item.severity }}</td><td>{{ item.message }}</td><td>{{ item.atom_maps }}</td><td>{{ item.deterministic }}</td><td><pre>{{ item.evidence }}</pre></td></tr>{% endfor %}
</tbody></table></div></div>{% endfor %}</section>
<section class="panel"><h2>7. Multi-view novelty</h2><p>Novelty views remain independent from plausibility.</p>
{% if novelty_metrics %}<div class="table-wrap"><table><thead><tr><th>View</th><th>Availability</th><th>Novelty</th><th>Maximum similarity</th><th>Nearest references</th><th>Interpretation / missing</th></tr></thead><tbody>
{% for item in novelty_metrics %}<tr><td><code>{{ item.metric_id }}</code></td><td>{{ item.availability }}</td><td>{{ item.novelty }}</td><td>{{ item.maximum_similarity }}</td><td>{{ item.nearest }}</td><td>{{ item.interpretation }}<br>{{ item.missing }}</td></tr>{% endfor %}</tbody></table></div>
{% else %}<p class="empty">Unavailable: no declared, versioned reference corpus was supplied.</p>{% endif %}</section>
<section class="panel"><h2>8. Precedents</h2>{% if precedent_hits %}<div class="table-wrap"><table><thead><tr><th>Source</th><th>Reaction</th><th>Transformation</th><th>Centre</th><th>Substrate</th><th>Missing evidence</th></tr></thead><tbody>
{% for item in precedent_hits %}<tr><td>{{ item.source_dataset }}</td><td>{{ item.source_reaction_id }}</td><td>{{ item.transformation_similarity }}</td><td>{{ item.reaction_centre_similarity }}</td><td>{{ item.substrate_similarity }}</td><td>{{ item.missing_evidence | join('; ') }}</td></tr>{% endfor %}</tbody></table></div>
{% else %}<p class="empty">Unavailable: no precedent index was supplied. Absence of retrieval is not negative evidence.</p>{% endif %}</section>
<section class="panel"><h2>9. Evidence-based plausibility</h2>{% if report.evidence %}<div class="table-wrap"><table><thead><tr><th>Stage</th><th>Availability</th><th>Calibrated support</th><th>Model</th><th>Interpretation</th></tr></thead><tbody>
{% for item in report.evidence %}<tr><td>{{ item.stage }}</td><td>{{ item.availability }}</td><td>{{ item.calibrated_evidence_support_score if item.calibrated_evidence_support_score is not none else '—' }}</td><td>{{ item.model_id or '—' }}</td><td>{{ item.interpretation }}</td></tr>{% endfor %}</tbody></table></div>
{% else %}<p class="empty">Unavailable: no calibrated evidence model output was supplied.</p>{% endif %}</section>
<section class="panel"><h2>10. Uncertainty and abstention</h2>{% if report.evidence %}<div class="table-wrap"><table><thead><tr><th>Stage</th><th>Uncertainty</th><th>Abstained</th><th>Reasons</th></tr></thead><tbody>
{% for item in report.evidence %}<tr><td>{{ item.stage }}</td><td>{{ item.uncertainty if item.uncertainty is not none else '—' }}</td><td>{{ item.abstained }}</td><td>{{ item.abstention_reasons | join('; ') or '—' }}</td></tr>{% endfor %}</tbody></table></div>
{% else %}<p class="empty">Unavailable: missing model evidence is retained as missing.</p>{% endif %}</section>
<section class="panel"><h2>11. Limitations</h2><ul>{% for item in limitations %}<li>{{ item }}</li>{% endfor %}</ul>
<h3>Model and corpus versions</h3><p>Models: {{ report.model_versions | join(', ') or 'unavailable' }}</p><p>Corpora: {{ report.corpus_versions | join(', ') or 'unavailable' }}</p>
<h3>Provenance</h3><pre>{{ provenance_json }}</pre></section>
<footer>{{ report.notice }} · Generated by SynthAudit {{ version }}.</footer></main></body></html>"""


_ROUTE_TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SynthAudit route report — {{ report.route.route_id }}</title><style>{{ css | safe }}</style></head>
<body><a class="skip-link" href="#content">Skip to report content</a><main id="content">
<header><div class="eyebrow">SynthAudit · route report · schema v1</div><h1>{{ report.route.route_id }}</h1>
<p>{{ report.route.strategy_text or 'No route strategy text was declared.' }}</p><p class="notice">{{ report.notice }}</p></header>
<section class="panel"><h2>Route summary</h2><div class="grid">
<div class="metric"><strong>Status</strong><span class="{{ report.audit.status.value }}">{{ report.audit.status.value }}</span></div>
<div class="metric"><strong>Steps</strong><span>{{ report.route.steps | length }}</span></div>
<div class="metric"><strong>Blocking</strong><span>{{ report.audit.blocking }}</span></div>
<div class="metric"><strong>Minimum step support</strong><span>{{ report.audit.minimum_step_support if report.audit.minimum_step_support is not none else 'unavailable' }}</span></div>
<div class="metric"><strong>Maximum uncertainty</strong><span>{{ report.audit.maximum_uncertainty if report.audit.maximum_uncertainty is not none else 'unavailable' }}</span></div></div></section>
<section class="panel"><h2>Strategy and dependency graph</h2><div class="route-graph">{{ route_svg | safe }}</div></section>
<section class="panel"><h2>Dependency, continuity, and condition checks</h2><div class="table-wrap"><table><thead><tr><th>Check</th><th>Status</th><th>Severity</th><th>Message</th><th>Evidence</th></tr></thead><tbody>
{% for item in checks %}<tr><td><code>{{ item.check_id }}</code></td><td class="{{ item.status }}">{{ item.status }}</td><td>{{ item.severity }}</td><td>{{ item.message }}</td><td><pre>{{ item.evidence }}</pre></td></tr>{% endfor %}</tbody></table></div></section>
<section class="panel"><h2>Per-step alerts</h2><div class="table-wrap"><table><thead><tr><th>Step</th><th>Structural</th><th>Centre</th><th>Completion</th><th>Stereo</th><th>Blocking</th></tr></thead><tbody>
{% for item in step_rows %}<tr><td>{{ item.step_id }}</td><td>{{ item.structural }}</td><td>{{ item.centre }}</td><td>{{ item.completion }}</td><td>{{ item.stereo }}</td><td>{{ item.blocking }}</td></tr>{% endfor %}</tbody></table></div></section>
<section class="panel"><h2>Key-step novelty and uncertainty</h2><p>High-novelty key steps: {{ report.audit.high_novelty_key_steps | join(', ') or 'none identified / evidence unavailable' }}</p>
<p>Maximum-uncertainty steps: {{ report.audit.maximum_uncertainty_steps | join(', ') or 'unavailable' }}</p><p>Novelty is not interpreted as implausibility.</p></section>
<section class="panel"><h2>Critical condition conflicts</h2>{% if report.audit.critical_condition_conflicts %}<ul>{% for item in report.audit.critical_condition_conflicts %}<li>{{ item }}</li>{% endfor %}</ul>{% else %}<p class="empty">No declared conflict was detected; undeclared chemistry remains outside this check.</p>{% endif %}</section>
<section class="panel"><h2>Expert-review queue</h2>{% if report.audit.expert_review_queue %}<div class="table-wrap"><table><thead><tr><th>Priority</th><th>Category</th><th>Steps</th><th>Reason</th><th>Deterministic</th></tr></thead><tbody>{% for item in report.audit.expert_review_queue %}<tr><td>{{ item.priority }}</td><td>{{ item.category }}</td><td>{{ item.step_ids | join(', ') }}</td><td>{{ item.reason }}</td><td>{{ item.deterministic }}</td></tr>{% endfor %}</tbody></table></div>{% else %}<p class="empty">The current declared evidence produced no review item.</p>{% endif %}</section>
<section class="panel"><h2>Limitations, versions, and provenance</h2><ul>{% for item in limitations %}<li>{{ item }}</li>{% endfor %}</ul>
<p>Models: {{ report.model_versions | join(', ') or 'unavailable' }}</p><p>Corpora: {{ report.corpus_versions | join(', ') or 'unavailable' }}</p><p>No route success probability is reported.</p><pre>{{ provenance_json }}</pre></section>
<footer>{{ report.notice }} · Generated by SynthAudit {{ version }}.</footer></main></body></html>"""


def render_reaction_report_html(report: ReactionReportV1) -> str:
    audit = report.audit
    core = audit.execution.core_result
    synthons = core.mapped_structures if core.success else core.diagnostic_mapped_structures
    completion = audit.execution.completion_result
    completed = (
        completion.mapped_structures
        if completion is not None and completion.success
        else completion.diagnostic_mapped_structures
        if completion is not None
        else ()
    )
    final = (
        audit.execution.mapped_structures
        if audit.execution.success
        else audit.execution.diagnostic_mapped_structures
    )
    source = report.reaction.source_payload_reference
    template = _environment().from_string(_REACTION_TEMPLATE)
    return template.render(
        report=report,
        css=_CSS,
        version=__version__,
        source_representation=source.representation
        if source is not None
        else "canonical ReactionIR",
        execution_status="pass" if audit.execution.success else "fail",
        source_json=json.dumps(
            source.model_dump(mode="json")
            if source is not None
            else {"representation": "ReactionIR"},
            indent=2,
            sort_keys=True,
        ),
        normalization_json=json.dumps(
            {
                "direction": report.reaction.direction,
                "core_edits": [item.model_dump(mode="json") for item in report.reaction.core_edits],
                "attachment_edits": [
                    item.model_dump(mode="json") for item in report.reaction.attachment_edits
                ],
                "atom_state_edits": [
                    item.model_dump(mode="json") for item in report.reaction.atom_state_edits
                ],
                "stereo_edits": [
                    item.model_dump(mode="json") for item in report.reaction.stereo_edits
                ],
            },
            indent=2,
            sort_keys=True,
        ),
        product_smiles=report.reaction.product.mapped_smiles,
        product_svg=molecule_svg((report.reaction.product.mapped_smiles,)),
        synthons="\n".join(synthons) or "unavailable",
        synthon_svg=molecule_svg(synthons),
        completed="\n".join(completed) or "unavailable",
        completion_svg=molecule_svg(completed),
        final_structures="\n".join(final) or "unavailable",
        final_svg=molecule_svg(final),
        stages=(
            _stage_payload("Structural alerts", audit.structural_audit),
            _stage_payload("Reaction-centre audit", audit.reaction_centre_audit),
            _stage_payload("Synthon-completion audit", audit.completion_audit),
            _stage_payload("Stereo audit", audit.stereo_audit),
        ),
        novelty_metrics=_novelty_metrics(report.novelty),
        precedent_hits=report.precedents.hits if report.precedents is not None else (),
        limitations=(*_DEFAULT_LIMITATIONS, *report.limitations),
        provenance_json=json.dumps(
            [item.model_dump(mode="json") for item in report.provenance],
            indent=2,
            sort_keys=True,
        ),
    )


def render_route_report_html(report: RouteReportV1) -> str:
    template = _environment().from_string(_ROUTE_TEMPLATE)
    return template.render(
        report=report,
        css=_CSS,
        version=__version__,
        route_svg=route_svg(report.route),
        checks=tuple(_check_payload(item) for item in report.audit.checks),
        step_rows=tuple(
            {
                "step_id": item.step_id,
                "structural": item.reaction_audit.structural_audit.status.value,
                "centre": item.reaction_audit.reaction_centre_audit.status.value,
                "completion": item.reaction_audit.completion_audit.status.value,
                "stereo": item.reaction_audit.stereo_audit.status.value,
                "blocking": item.reaction_audit.blocking,
            }
            for item in report.audit.step_audits
        ),
        limitations=(*_DEFAULT_LIMITATIONS, *report.limitations),
        provenance_json=json.dumps(
            [item.model_dump(mode="json") for item in report.provenance],
            indent=2,
            sort_keys=True,
        ),
    )


def _write_report(
    path: str | Path,
    html_text: str,
    payload: dict[str, Any],
    *,
    json_path: str | Path | None = None,
) -> tuple[Path, Path]:
    html_target = Path(path)
    sidecar = Path(json_path) if json_path is not None else html_target.with_suffix(".json")
    html_target.parent.mkdir(parents=True, exist_ok=True)
    html_target.write_text(html_text, encoding="utf-8")
    sidecar.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return html_target, sidecar


def write_reaction_report(
    path: str | Path,
    report: ReactionReportV1,
    *,
    json_path: str | Path | None = None,
) -> tuple[Path, Path]:
    return _write_report(
        path,
        render_reaction_report_html(report),
        report.model_dump(mode="json"),
        json_path=json_path,
    )


def write_route_report(
    path: str | Path,
    report: RouteReportV1,
    *,
    json_path: str | Path | None = None,
) -> tuple[Path, Path]:
    return _write_report(
        path,
        render_route_report_html(report),
        report.model_dump(mode="json"),
        json_path=json_path,
    )


def report_provenance(component: str) -> tuple[ProvenanceRecord, ...]:
    return (
        ProvenanceRecord(
            source="synthaudit",
            source_version=__version__,
            adapter=component,
            adapter_version="1",
            license="Apache-2.0",
        ),
    )
