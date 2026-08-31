from __future__ import annotations

import json
from pathlib import Path

from synthaudit import SCIENTIFIC_NOTICE
from synthaudit.adapters.mapped_reaction_smiles import (
    MappedReactionSmilesAdapter,
    MappedReactionSmilesInput,
)
from synthaudit.audit import ReactionAuditor
from synthaudit.rendering import render_reaction_audit_html, write_reaction_audit_report


def test_stage_specific_html_is_standalone_and_contains_notice(tmp_path: Path) -> None:
    reaction = MappedReactionSmilesAdapter().to_reaction_ir(
        MappedReactionSmilesInput(
            reaction_smiles="[CH3:1][CH2:2][Br:3].[OH-:4]>>[CH3:1][CH2:2][OH:4]"
        )
    )
    audit = ReactionAuditor().audit(reaction)
    html = render_reaction_audit_html(reaction, audit)
    assert "<!doctype html>" in html
    assert "<style>" in html
    assert "<svg" in html
    assert SCIENTIFIC_NOTICE in html
    assert 'id="structural"' in html
    assert 'id="reaction_centre"' in html
    assert 'id="completion"' in html
    assert 'id="stereo"' in html
    assert "<script src=" not in html and "<link href=" not in html

    html_path, json_path = write_reaction_audit_report(tmp_path / "audit.html", reaction, audit)
    assert html_path.read_text(encoding="utf-8") == html
    sidecar = json.loads(json_path.read_text(encoding="utf-8"))
    assert sidecar["schema_version"] == "synthaudit.reaction-audit-result/1"
    assert sidecar["notice"] == SCIENTIFIC_NOTICE
