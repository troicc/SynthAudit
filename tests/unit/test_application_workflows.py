from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from synthaudit.application.models import ReactionSourceKind
from synthaudit.application.workflows import (
    load_reaction_ir,
    normalize_reaction_source,
    prepare_reference_index,
)
from synthaudit.data import DataDownloadManifestV1, download_from_manifest
from synthaudit.precedent.models import ReferenceReactionV1
from synthaudit.schema.common import ProvenanceRecord
from synthaudit.ui.workspace import DEMO_REACTION_SMILES, demo_reaction

PROVENANCE = (
    ProvenanceRecord(
        source="authored-product-test",
        source_version="1",
        license="Apache-2.0 fixture; not experimental evidence",
    ),
)


def test_normalization_workflow_supports_explicit_mapped_and_ir_sources(tmp_path: Path) -> None:
    mapped = normalize_reaction_source(
        ReactionSourceKind.MAPPED_REACTION_SMILES,
        DEMO_REACTION_SMILES,
        reaction_id="workflow-mapped",
    )
    assert mapped.reaction_ir.reaction_id == "workflow-mapped"
    assert mapped.source_kind == ReactionSourceKind.MAPPED_REACTION_SMILES
    assert mapped.provenance

    ir = normalize_reaction_source(
        ReactionSourceKind.REACTION_IR,
        mapped.reaction_ir.model_dump_json(),
        reaction_id="workflow-round-trip",
    )
    assert ir.reaction_ir.reaction_id == "workflow-round-trip"
    path = tmp_path / "reaction.json"
    path.write_text(ir.reaction_ir.model_dump_json(), encoding="utf-8")
    assert load_reaction_ir(path) == ir.reaction_ir


def test_reactseq_requires_explicit_mapped_product() -> None:
    with pytest.raises(ValueError, match="mapped product"):
        normalize_reaction_source(ReactionSourceKind.REACTSEQ, "CC>>>CC")


def test_data_transfer_verifies_local_checksum_and_refuses_implicit_network(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"content-addressed fixture")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    manifest = DataDownloadManifestV1(
        dataset_id="fixture",
        dataset_version="1",
        artifacts=(
            {
                "artifact_id": "local",
                "source_uri": source.as_uri(),
                "destination": "data/local.bin",
                "sha256": digest,
                "license_status": "CC0 fixture",
            },
        ),
        provenance=PROVENANCE,
    )
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(manifest.model_dump_json(), encoding="utf-8")
    result = download_from_manifest(manifest_path, tmp_path / "download")
    assert not result.network_access_used
    assert (tmp_path / "download/data/local.bin").read_bytes() == source.read_bytes()

    remote_payload = manifest.model_dump(mode="json")
    remote_payload["artifacts"][0]["source_uri"] = "https://example.invalid/data"
    remote_path = tmp_path / "remote.json"
    remote_path.write_text(json.dumps(remote_payload), encoding="utf-8")
    with pytest.raises(PermissionError, match="disabled"):
        download_from_manifest(remote_path, tmp_path / "remote")


def test_prepare_reference_index_is_content_addressed(tmp_path: Path) -> None:
    record = ReferenceReactionV1(
        source_dataset="authored-product-test",
        source_reaction_id="ref-1",
        data_license_status="Apache-2.0 fixture",
        reaction=demo_reaction(),
    )
    records = tmp_path / "records.jsonl"
    records.write_text(record.model_dump_json() + "\n", encoding="utf-8")
    target = tmp_path / "index.json"
    index = prepare_reference_index(
        records,
        target,
        corpus_id="fixture-index",
        corpus_version="1",
    )
    assert target.exists()
    assert index.manifest.record_count == 1
    assert len(index.manifest.records_sha256) == 64


def test_data_manifest_rejects_path_traversal() -> None:
    with pytest.raises(ValueError, match="relative path"):
        DataDownloadManifestV1(
            dataset_id="fixture",
            dataset_version="1",
            artifacts=(
                {
                    "artifact_id": "unsafe",
                    "source_uri": "source.bin",
                    "destination": "../escape.bin",
                    "sha256": "0" * 64,
                    "license_status": "fixture",
                },
            ),
            provenance=PROVENANCE,
        )
