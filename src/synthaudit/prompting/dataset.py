"""Content-addressed storage and validation for prompt-robustness cases."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from synthaudit import __version__
from synthaudit.prompting.models import (
    PromptBenchmarkCaseV1,
    PromptBenchmarkDatasetManifestV1,
    PromptBenchmarkDatasetV1,
    PromptBenchmarkValidationV1,
    PromptVariantKind,
    canonical_prompt_cases_text,
    prompt_cases_sha256,
)
from synthaudit.schema.common import ProvenanceRecord


def build_prompt_dataset(
    cases: Sequence[PromptBenchmarkCaseV1],
    *,
    dataset_id: str,
    dataset_version: str,
    purpose: str,
    source_dataset_id: str,
    source_dataset_version: str,
    source_records_sha256: str,
    source_license_status: str,
) -> PromptBenchmarkDatasetV1:
    values = tuple(sorted(cases, key=lambda item: item.case_id))
    if not values:
        raise ValueError("prompt benchmark dataset requires at least one eligible case")
    counts = {
        kind: sum(variant.kind == kind for case in values for variant in case.variants)
        for kind in PromptVariantKind
    }
    digest = prompt_cases_sha256(values)
    manifest = PromptBenchmarkDatasetManifestV1(
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        purpose=purpose,
        source_dataset_id=source_dataset_id,
        source_dataset_version=source_dataset_version,
        source_records_sha256=source_records_sha256,
        source_license_status=source_license_status,
        case_count=len(values),
        variant_count=sum(counts.values()),
        variant_kind_counts=counts,
        cases_sha256=digest,
        provenance=(
            ProvenanceRecord(
                source="synthaudit",
                source_version=__version__,
                adapter="build_prompt_dataset",
                adapter_version="1",
                artifact_sha256=digest,
                license="Apache-2.0",
            ),
        ),
    )
    return PromptBenchmarkDatasetV1(manifest=manifest, cases=values)


def write_prompt_dataset(
    dataset: PromptBenchmarkDatasetV1,
    *,
    cases_path: str | Path,
    manifest_path: str | Path,
) -> tuple[Path, Path]:
    cases_target = Path(cases_path)
    manifest_target = Path(manifest_path)
    cases_target.parent.mkdir(parents=True, exist_ok=True)
    manifest_target.parent.mkdir(parents=True, exist_ok=True)
    text = canonical_prompt_cases_text(dataset.cases)
    if prompt_cases_sha256(dataset.cases) != dataset.manifest.cases_sha256:
        raise ValueError("prompt cases no longer match the manifest SHA-256")
    cases_target.write_text(text, encoding="utf-8")
    manifest_target.write_text(
        json.dumps(dataset.manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return cases_target, manifest_target


def load_prompt_dataset(
    *,
    cases_path: str | Path,
    manifest_path: str | Path,
) -> PromptBenchmarkDatasetV1:
    manifest_payload: Any = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    manifest = PromptBenchmarkDatasetManifestV1.model_validate(manifest_payload)
    cases = tuple(
        PromptBenchmarkCaseV1.model_validate(json.loads(line))
        for line in Path(cases_path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    )
    return PromptBenchmarkDatasetV1(manifest=manifest, cases=cases)


def validate_prompt_benchmark_artifacts(
    *,
    cases_path: str | Path,
    manifest_path: str | Path,
) -> PromptBenchmarkValidationV1:
    dataset = load_prompt_dataset(cases_path=cases_path, manifest_path=manifest_path)
    groups_by_case = {item.case_id: item.parent_group_id for item in dataset.cases}
    if len(groups_by_case) != len(dataset.cases):
        raise ValueError("prompt case identity or parent grouping is not atomic")
    return PromptBenchmarkValidationV1(
        dataset_id=dataset.manifest.dataset_id,
        dataset_version=dataset.manifest.dataset_version,
        case_count=dataset.manifest.case_count,
        variant_count=dataset.manifest.variant_count,
        variant_kind_counts=dataset.manifest.variant_kind_counts,
        cases_sha256=dataset.manifest.cases_sha256,
    )
