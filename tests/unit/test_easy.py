from __future__ import annotations

import csv
import json
from pathlib import Path

from synthaudit.easy import (
    _record_iterator,
    audit_reaction_smiles,
    doctor_report,
    normalize_reaction,
)


def _example_reaction() -> str:
    payload = json.loads(Path("examples/reaction-ir.json").read_text(encoding="utf-8"))
    left = ".".join(item["mapped_smiles"] for item in payload["expected_precursors"])
    return f"{left}>>{payload['product']['mapped_smiles']}"


def test_doctor_reports_core_environment() -> None:
    report = doctor_report()
    assert report["core_ready"] is True
    assert report["python_supported"] is True
    assert report["synthaudit_version"]
    assert "mapper" in report["optional_integrations"]


def test_direct_normalization_and_audit() -> None:
    reaction, normalized, mapping = normalize_reaction(_example_reaction())
    assert reaction.reaction_id
    assert normalized.count(">") == 2
    assert mapping is None
    _, audit, _, _ = audit_reaction_smiles(_example_reaction())
    assert audit.structurally_valid is True
    assert audit.blocking is False


def test_csv_and_jsonl_batch_readers(tmp_path: Path) -> None:
    csv_path = tmp_path / "records.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["reaction_id", "reaction_smiles"])
        writer.writeheader()
        writer.writerow({"reaction_id": "a", "reaction_smiles": _example_reaction()})
    assert next(
        _record_iterator(csv_path, reaction_column="reaction_smiles", id_column="reaction_id")
    )[0] == "a"

    jsonl_path = tmp_path / "records.jsonl"
    jsonl_path.write_text(
        json.dumps({"reaction_id": "b", "reaction_smiles": _example_reaction()}) + "\n",
        encoding="utf-8",
    )
    assert next(
        _record_iterator(jsonl_path, reaction_column="reaction_smiles", id_column="reaction_id")
    )[0] == "b"
