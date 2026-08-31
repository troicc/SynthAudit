"""Fail-closed validation for complete counterfactual benchmark artifacts."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from synthaudit.counterfactuals.dataset import load_dataset
from synthaudit.counterfactuals.models import (
    BenchmarkLabel,
    BenchmarkSplitManifestV1,
    CounterfactualBenchmarkValidationV1,
    CounterfactualCategory,
    DatasetPartition,
    DifficultyLevel,
    EvaluationSlice,
    GenerationMethod,
)

REVIEW_COLUMNS = (
    "record_id",
    "parent_reaction_id",
    "category",
    "generation_method",
    "difficulty",
    "structurally_valid",
    "reviewer_id",
    "chemistry_support_judgement",
    "ambiguity_reason",
    "review_notes",
)


def _load_splits(path: str | Path) -> BenchmarkSplitManifestV1:
    payload: Any = json.loads(Path(path).read_text(encoding="utf-8"))
    return BenchmarkSplitManifestV1.model_validate(payload)


def _review_rows(path: str | Path, records_by_id: dict[str, Any]) -> int:
    with Path(path).open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != REVIEW_COLUMNS:
            raise ValueError("human-review sheet columns do not match the versioned template")
        rows = list(reader)
    if not rows:
        raise ValueError("human-review sheet must include at least one hard valid candidate")
    if len({row["record_id"] for row in rows}) != len(rows):
        raise ValueError("human-review sheet contains duplicate record IDs")
    for row in rows:
        record = records_by_id.get(row["record_id"])
        if record is None:
            raise ValueError(f"human-review row references unknown record {row['record_id']}")
        if (
            record.label != BenchmarkLabel.GENERATED_COUNTERFACTUAL
            or record.difficulty != DifficultyLevel.HARD
            or not record.structural_validity.structurally_valid
        ):
            raise ValueError(
                f"human-review row is not a hard structurally valid counterfactual: "
                f"{row['record_id']}"
            )
    return len(rows)


def validate_benchmark_artifacts(
    *,
    records_path: str | Path,
    manifest_path: str | Path,
    splits_path: str | Path,
    human_review_path: str | Path,
) -> CounterfactualBenchmarkValidationV1:
    dataset = load_dataset(records_path=records_path, manifest_path=manifest_path)
    splits = _load_splits(splits_path)
    if (
        splits.dataset_id != dataset.manifest.dataset_id
        or splits.dataset_version != dataset.manifest.dataset_version
        or splits.records_sha256 != dataset.manifest.records_sha256
    ):
        raise ValueError("split manifest does not identify the loaded dataset artifact")
    record_ids = {record.record_id for record in dataset.records}
    assignment_ids = {assignment.record_id for assignment in splits.assignments}
    if record_ids != assignment_ids:
        raise ValueError("split assignments must cover every dataset record exactly once")
    methods = {
        record.generation_method
        for record in dataset.records
        if record.generation_method is not None
    }
    missing_methods = sorted(method.value for method in set(GenerationMethod) - methods)
    if missing_methods:
        raise ValueError(f"benchmark does not cover generation methods: {missing_methods}")
    missing_categories = [
        category.value
        for category in CounterfactualCategory
        if dataset.manifest.category_counts[category] == 0
    ]
    if missing_categories:
        raise ValueError(
            f"benchmark does not cover counterfactual categories: {missing_categories}"
        )
    missing_slices = [
        slice_name.value
        for slice_name in EvaluationSlice
        if not any(slice_name in item.evaluation_slices for item in splits.assignments)
    ]
    if missing_slices:
        raise ValueError(f"benchmark does not populate evaluation slices: {missing_slices}")
    records_by_id = {record.record_id: record for record in dataset.records}
    human_review_count = _review_rows(human_review_path, records_by_id)
    split_fields = ("in_distribution", "scaffold_holdout", "reaction_class_holdout")
    partition_counts = {
        field: {
            partition: sum(getattr(item, field) == partition for item in splits.assignments)
            for partition in DatasetPartition
        }
        for field in split_fields
    }
    slice_counts = {
        slice_name: sum(
            slice_name in assignment.evaluation_slices for assignment in splits.assignments
        )
        for slice_name in EvaluationSlice
    }
    return CounterfactualBenchmarkValidationV1(
        dataset_id=dataset.manifest.dataset_id,
        dataset_version=dataset.manifest.dataset_version,
        record_count=dataset.manifest.record_count,
        records_sha256=dataset.manifest.records_sha256,
        label_counts=dict(dataset.manifest.label_counts),
        category_counts=dict(dataset.manifest.category_counts),
        method_count=len(methods),
        split_partition_counts=partition_counts,
        evaluation_slice_counts=slice_counts,
        human_review_row_count=human_review_count,
    )
