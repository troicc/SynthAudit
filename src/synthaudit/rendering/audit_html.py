"""Offline, print-friendly stage-specific reaction audit report."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from jinja2 import Environment, select_autoescape
from rdkit import Chem
from rdkit.Chem import Draw

from synthaudit.schema.reaction_ir import ReactionIRV1
from synthaudit.schema.results import ReactionAuditResultV1, StageAuditResultV1

_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>SynthAudit — {{ reaction_id }}</title>
  <style>
    :root { color-scheme: light; --ink:#17211f; --muted:#5f6d69; --line:#d5dfdb;
      --paper:#fbfcfa; --accent:#125f55; --pass:#176b4d; --warn:#9a6200; --fail:#a52a2a; }
    * { box-sizing:border-box; }
    body { margin:0; background:#edf2ef; color:var(--ink); font:15px/1.5 system-ui,sans-serif; }
    main { width:min(1100px,calc(100% - 32px)); margin:24px auto; background:var(--paper);
      padding:36px; box-shadow:0 12px 40px #1c332a1a; }
    h1,h2 { letter-spacing:-.02em; } h2 { border-bottom:2px solid var(--accent); padding-bottom:6px; }
    .notice { border:2px solid var(--accent); padding:14px 16px; font-weight:650; background:#eef8f5; }
    .summary,.stage-grid { display:grid; gap:12px; grid-template-columns:repeat(auto-fit,minmax(190px,1fr)); }
    .card { border:1px solid var(--line); border-radius:8px; padding:14px; background:white; }
    .status { text-transform:uppercase; font-weight:750; letter-spacing:.04em; }
    .pass { color:var(--pass); } .warning,.indeterminate,.unavailable,.unsupported { color:var(--warn); }
    .fail { color:var(--fail); } table { width:100%; border-collapse:collapse; margin:12px 0 24px; }
    th,td { text-align:left; vertical-align:top; border-bottom:1px solid var(--line); padding:9px 7px; }
    th { color:var(--muted); font-size:12px; text-transform:uppercase; }
    code,pre { white-space:pre-wrap; overflow-wrap:anywhere; font:12px/1.45 ui-monospace,monospace; }
    .molecule svg { width:100%; height:auto; max-height:300px; }
    footer { border-top:1px solid var(--line); margin-top:28px; padding-top:16px; color:var(--muted); }
    @media print { body { background:white; } main { width:100%; margin:0; box-shadow:none; padding:12mm; }
      h2 { break-before:page; } h2:first-of-type { break-before:auto; } }
  </style>
</head>
<body><main>
  <header><p>SynthAudit stage-specific reaction audit</p><h1>{{ reaction_id }}</h1></header>
  <p class="notice">{{ notice }}</p>
  <section class="summary">
    <div class="card"><strong>Execution</strong><div class="status {{ execution_status }}">{{ execution_status }}</div></div>
    <div class="card"><strong>Structurally valid</strong><div>{{ structurally_valid }}</div></div>
    <div class="card"><strong>Blocking checks</strong><div>{{ blocking }}</div></div>
    <div class="card"><strong>Source representation</strong><div>{{ source_representation }}</div></div>
  </section>
  <section><h2>Input and product</h2><code>{{ product_smiles }}</code><div class="molecule">{{ product_svg | safe }}</div></section>
  <section><h2>Product → synthons</h2><code>{{ synthons }}</code><div class="molecule">{{ synthon_svg | safe }}</div></section>
  <section><h2>Synthons → completed precursors</h2><code>{{ completed }}</code><div class="molecule">{{ completion_svg | safe }}</div></section>
  <section><h2>Stereo result</h2><code>{{ final_structures }}</code><div class="molecule">{{ final_svg | safe }}</div></section>
  {% for stage in stages %}
  <section id="{{ stage.stage }}"><h2>{{ stage.title }}</h2>
    <p class="status {{ stage.status }}">{{ stage.status }}</p>
    <table><thead><tr><th>Check</th><th>Status</th><th>Severity</th><th>Message</th><th>Atom maps</th><th>Evidence</th></tr></thead>
    <tbody>{% for item in stage.checks %}<tr>
      <td><code>{{ item.check_id }}</code></td><td class="status {{ item.status }}">{{ item.status }}</td>
      <td>{{ item.severity }}</td><td>{{ item.message }}</td><td>{{ item.atom_maps }}</td><td><pre>{{ item.evidence }}</pre></td>
    </tr>{% endfor %}</tbody></table>
  </section>{% endfor %}
  <section><h2>Execution diagnostics</h2><pre>{{ execution_json }}</pre></section>
  <section><h2>Provenance and limitations</h2><pre>{{ provenance_json }}</pre>
    <p>This report audits representation and graph consistency. Unavailable checks remain visible;
    no missing evidence is converted into a favourable result.</p></section>
  <footer>{{ notice }}</footer>
</main></body></html>
"""


def _svg(structures: tuple[str, ...]) -> str:
    molecules: list[Chem.Mol] = []
    legends: list[str] = []
    for structure in structures:
        molecule = cast(Chem.Mol | None, Chem.MolFromSmiles(structure))
        if molecule is not None:
            molecules.append(molecule)
            legends.append(structure)
    if not molecules:
        return '<p class="warning">No parseable structure available for drawing.</p>'
    drawing = Draw.MolsToGridImage(  # type: ignore[no-untyped-call]
        molecules,
        legends=legends,
        molsPerRow=min(3, len(molecules)),
        subImgSize=(300, 220),
        useSVG=True,
    )
    return str(drawing)


def _stage_payload(title: str, stage: StageAuditResultV1) -> dict[str, object]:
    return {
        "title": title,
        "stage": stage.stage,
        "status": stage.status.value,
        "checks": [
            {
                "check_id": item.check_id,
                "status": item.status.value,
                "severity": item.severity.value,
                "message": item.message,
                "atom_maps": ", ".join(map(str, item.affected_atom_maps)) or "—",
                "evidence": json.dumps(item.evidence, indent=2, sort_keys=True),
            }
            for item in stage.checks
        ],
    }


def render_reaction_audit_html(
    reaction: ReactionIRV1,
    audit: ReactionAuditResultV1,
) -> str:
    """Render a deterministic standalone report with embedded SVG and CSS."""
    core = audit.execution.core_result
    synthons = core.mapped_structures if core.success else core.diagnostic_mapped_structures
    completion_result = audit.execution.completion_result
    completed = (
        completion_result.mapped_structures
        if completion_result and completion_result.success
        else (completion_result.diagnostic_mapped_structures if completion_result else ())
    )
    final = (
        audit.execution.mapped_structures
        if audit.execution.success
        else audit.execution.diagnostic_mapped_structures
    )
    source_representation = (
        reaction.source_payload_reference.representation
        if reaction.source_payload_reference
        else "canonical ReactionIR"
    )
    environment = Environment(autoescape=select_autoescape(default=True))
    template = environment.from_string(_TEMPLATE)
    return template.render(
        reaction_id=reaction.reaction_id,
        notice=audit.notice,
        execution_status="pass" if audit.execution.success else "fail",
        structurally_valid=str(audit.structurally_valid).lower(),
        blocking=str(audit.blocking).lower(),
        source_representation=source_representation,
        product_smiles=reaction.product.mapped_smiles,
        product_svg=_svg((reaction.product.mapped_smiles,)),
        synthons="\n".join(synthons) or "unavailable",
        synthon_svg=_svg(synthons),
        completed="\n".join(completed) or "unavailable",
        completion_svg=_svg(completed),
        final_structures="\n".join(final) or "unavailable",
        final_svg=_svg(final),
        stages=(
            _stage_payload("Structural audit", audit.structural_audit),
            _stage_payload("Reaction-centre audit", audit.reaction_centre_audit),
            _stage_payload("Synthon-completion audit", audit.completion_audit),
            _stage_payload("Stereo audit", audit.stereo_audit),
        ),
        execution_json=json.dumps(
            audit.execution.model_dump(mode="json"), indent=2, sort_keys=True
        ),
        provenance_json=json.dumps(
            [item.model_dump(mode="json") for item in audit.provenance],
            indent=2,
            sort_keys=True,
        ),
    )


def write_reaction_audit_report(
    path: str | Path,
    reaction: ReactionIRV1,
    audit: ReactionAuditResultV1,
    *,
    json_path: str | Path | None = None,
) -> tuple[Path, Path]:
    """Write standalone HTML plus a deterministic JSON sidecar."""
    html_target = Path(path)
    sidecar_target = Path(json_path) if json_path is not None else html_target.with_suffix(".json")
    html_target.parent.mkdir(parents=True, exist_ok=True)
    sidecar_target.parent.mkdir(parents=True, exist_ok=True)
    html_target.write_text(render_reaction_audit_html(reaction, audit), encoding="utf-8")
    sidecar_target.write_text(
        json.dumps(audit.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return html_target, sidecar_target
