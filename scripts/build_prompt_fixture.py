"""Build the committed prompt-robustness software-verification fixture."""

from __future__ import annotations

import argparse
from pathlib import Path

from synthaudit.counterfactuals import BenchmarkLabel, load_dataset
from synthaudit.prompting import (
    PromptBenchmarkDatasetV1,
    PromptRobustnessCaseGenerator,
    build_prompt_dataset,
    write_prompt_dataset,
)

GLOBAL_SEED = 20261800
DATASET_ID = "synthaudit-authored-prompt-robustness-fixture"
DATASET_VERSION = "1"


def build_fixture_dataset(root: Path) -> PromptBenchmarkDatasetV1:
    source = load_dataset(
        records_path=root / "benchmarks/counterfactual-v1/records.jsonl",
        manifest_path=root / "benchmarks/counterfactual-v1/manifest.json",
    )
    eligible = sorted(
        (
            record
            for record in source.records
            if record.label == BenchmarkLabel.RECORDED_REACTION
            and record.reaction is not None
            and bool(record.reaction.core_edits)
            and record.reaction.edit_count >= 2
        ),
        key=lambda item: item.record_id,
    )
    generator = PromptRobustnessCaseGenerator()
    cases = tuple(
        generator.build_case(
            record.reaction,  # type: ignore[arg-type]
            parent_group_id=record.record_id,
            seed=GLOBAL_SEED + index,
        )
        for index, record in enumerate(eligible)
    )
    return build_prompt_dataset(
        cases,
        dataset_id=DATASET_ID,
        dataset_version=DATASET_VERSION,
        purpose="software_verification_fixture",
        source_dataset_id=source.manifest.dataset_id,
        source_dataset_version=source.manifest.dataset_version,
        source_records_sha256=source.manifest.records_sha256,
        source_license_status="; ".join(source.manifest.source_licenses),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("benchmarks/prompt-robustness-v1"),
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output_dir = args.output_dir
    if not output_dir.is_absolute():
        output_dir = root / output_dir
    dataset = build_fixture_dataset(root)
    write_prompt_dataset(
        dataset,
        cases_path=output_dir / "cases.jsonl",
        manifest_path=output_dir / "manifest.json",
    )


if __name__ == "__main__":
    main()
