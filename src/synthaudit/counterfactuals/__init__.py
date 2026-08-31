"""Controlled stage-aware counterfactual generation and grouped benchmark splits."""

from synthaudit.counterfactuals.dataset import (
    build_dataset,
    load_dataset,
    records_sha256,
    serialize_records,
    write_dataset,
)
from synthaudit.counterfactuals.generator import (
    CounterfactualGenerator,
    CounterfactualNotApplicable,
    canonical_payload_sha256,
    product_scaffold_group,
)
from synthaudit.counterfactuals.models import (
    BenchmarkLabel,
    BenchmarkSplitManifestV1,
    CounterfactualBenchmarkValidationV1,
    CounterfactualCategory,
    CounterfactualDatasetManifestV1,
    CounterfactualDatasetV1,
    CounterfactualRecordV1,
    DatasetPartition,
    DifficultyLevel,
    EvaluationSlice,
    FieldChangeV1,
    GenerationMethod,
    NoveltySliceDefinitionV1,
    SplitAssignmentV1,
    StepStructuralValidityV1,
    StructuralValidityResultV1,
)
from synthaudit.counterfactuals.splits import build_grouped_splits
from synthaudit.counterfactuals.validation import validate_benchmark_artifacts

__all__ = [
    "BenchmarkLabel",
    "BenchmarkSplitManifestV1",
    "CounterfactualBenchmarkValidationV1",
    "CounterfactualCategory",
    "CounterfactualDatasetManifestV1",
    "CounterfactualDatasetV1",
    "CounterfactualGenerator",
    "CounterfactualNotApplicable",
    "CounterfactualRecordV1",
    "DatasetPartition",
    "DifficultyLevel",
    "EvaluationSlice",
    "FieldChangeV1",
    "GenerationMethod",
    "NoveltySliceDefinitionV1",
    "SplitAssignmentV1",
    "StepStructuralValidityV1",
    "StructuralValidityResultV1",
    "build_dataset",
    "build_grouped_splits",
    "canonical_payload_sha256",
    "load_dataset",
    "product_scaffold_group",
    "records_sha256",
    "serialize_records",
    "validate_benchmark_artifacts",
    "write_dataset",
]
