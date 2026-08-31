"""Content-addressed JSONL storage for counterfactual benchmark records."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from synthaudit import __version__
from synthaudit.counterfactuals.models import (
    BenchmarkLabel,
    CounterfactualCategory,
    CounterfactualDatasetManifestV1,
    CounterfactualDatasetV1,
    CounterfactualRecordV1,
    DifficultyLevel,
)
from synthaudit.schema.common import ProvenanceRecord


def serialize_records(records: Sequence[CounterfactualRecordV1]) -> str:
    return "".join(
        json.dumps(record.model_dump(mode="json"), sort_keys=True, separators=(",", ":")) + "\n"
        for record in records
    )


def records_sha256(records_text: str) -> str:
    return hashlib.sha256(records_text.encode()).hexdigest()


def build_dataset(
    records: Sequence[CounterfactualRecordV1],
    *,
    dataset_id: str,
    dataset_version: str,
    purpose: str,
    global_seed: int,
    generator_version: str,
) -> CounterfactualDatasetV1:
    values = tuple(records)
    serialized = serialize_records(values)
    label_counter = Counter(record.label for record in values)
    category_counter = Counter(record.category for record in values if record.category is not None)
    difficulty_counter = Counter(
        record.difficulty for record in values if record.difficulty is not None
    )
    manifest = CounterfactualDatasetManifestV1(
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        purpose=purpose,
        record_count=len(values),
        records_sha256=records_sha256(serialized),
        label_counts={label: label_counter[label] for label in BenchmarkLabel},
        category_counts={
            category: category_counter[category] for category in CounterfactualCategory
        },
        difficulty_counts={
            difficulty: difficulty_counter[difficulty] for difficulty in DifficultyLevel
        },
        generator_version=generator_version,
        global_seed=global_seed,
        source_licenses=tuple(sorted({record.data_license_status for record in values})),
        provenance=(
            ProvenanceRecord(
                source="synthaudit",
                source_version=__version__,
                adapter="build_dataset",
                adapter_version="1",
                artifact_sha256=records_sha256(serialized),
                license="Apache-2.0",
            ),
        ),
    )
    return CounterfactualDatasetV1(manifest=manifest, records=values)


def write_dataset(
    dataset: CounterfactualDatasetV1,
    *,
    records_path: str | Path,
    manifest_path: str | Path,
) -> tuple[Path, Path]:
    records_target = Path(records_path)
    manifest_target = Path(manifest_path)
    records_target.parent.mkdir(parents=True, exist_ok=True)
    manifest_target.parent.mkdir(parents=True, exist_ok=True)
    serialized = serialize_records(dataset.records)
    digest = records_sha256(serialized)
    if digest != dataset.manifest.records_sha256:
        raise ValueError("dataset records no longer match the manifest SHA-256")
    records_target.write_text(serialized, encoding="utf-8")
    manifest_target.write_text(
        json.dumps(dataset.manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return records_target, manifest_target


def load_dataset(
    *,
    records_path: str | Path,
    manifest_path: str | Path,
) -> CounterfactualDatasetV1:
    records_text = Path(records_path).read_text(encoding="utf-8")
    manifest_payload: Any = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    manifest = CounterfactualDatasetManifestV1.model_validate(manifest_payload)
    if records_sha256(records_text) != manifest.records_sha256:
        raise ValueError("counterfactual record SHA-256 mismatch")
    records = tuple(
        CounterfactualRecordV1.model_validate(json.loads(line))
        for line in records_text.splitlines()
        if line.strip()
    )
    return CounterfactualDatasetV1(manifest=manifest, records=records)
