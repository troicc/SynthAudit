"""Leakage-resistant parent, scaffold, and reaction-class split construction."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence

from synthaudit.counterfactuals.models import (
    BenchmarkLabel,
    BenchmarkSplitManifestV1,
    CounterfactualDatasetV1,
    CounterfactualRecordV1,
    DatasetPartition,
    EvaluationSlice,
    NoveltySliceDefinitionV1,
    SplitAssignmentV1,
)


def _stable_order(groups: Sequence[str], *, seed: int, namespace: str) -> list[str]:
    return sorted(
        set(groups),
        key=lambda group: hashlib.sha256(f"{seed}|{namespace}|{group}".encode()).hexdigest(),
    )


def _partition_groups(
    groups: Sequence[str], *, seed: int, namespace: str
) -> dict[str, DatasetPartition]:
    ordered = _stable_order(groups, seed=seed, namespace=namespace)
    if not ordered:
        return {}
    if len(ordered) == 1:
        return {ordered[0]: DatasetPartition.TRAIN}
    test_count = max(1, round(len(ordered) * 0.15))
    calibration_count = max(1, round(len(ordered) * 0.15)) if len(ordered) >= 3 else 0
    if test_count + calibration_count >= len(ordered):
        test_count = 1
        calibration_count = 1 if len(ordered) >= 3 else 0
    train_end = len(ordered) - test_count - calibration_count
    assignments: dict[str, DatasetPartition] = {}
    for index, group in enumerate(ordered):
        if index < train_end:
            assignments[group] = DatasetPartition.TRAIN
        elif index < train_end + calibration_count:
            assignments[group] = DatasetPartition.CALIBRATION
        else:
            assignments[group] = DatasetPartition.TEST
    return assignments


def _recorded_parents(
    records: Sequence[CounterfactualRecordV1],
) -> dict[str, CounterfactualRecordV1]:
    parents = {
        record.grouping_parent_reaction_id: record
        for record in records
        if record.label == BenchmarkLabel.RECORDED_REACTION
    }
    for record in records:
        group = record.grouping_parent_reaction_id
        if group not in parents:
            raise ValueError(f"counterfactual parent reaction is absent: {group}")
        parent = parents[group]
        if record.product_scaffold_group != parent.product_scaffold_group:
            raise ValueError(
                f"counterfactual scaffold group differs from its parent: {record.record_id}"
            )
        if record.reaction_class != parent.reaction_class:
            raise ValueError(
                f"counterfactual reaction class differs from its parent: {record.record_id}"
            )
    return parents


def build_grouped_splits(
    dataset: CounterfactualDatasetV1,
    *,
    split_seed: int,
    product_novelty_by_parent: Mapping[str, float] | None = None,
    novelty_slice: NoveltySliceDefinitionV1 | None = None,
) -> BenchmarkSplitManifestV1:
    parents = _recorded_parents(dataset.records)
    parent_partition = _partition_groups(
        tuple(parents), seed=split_seed, namespace="parent_reaction"
    )
    scaffold_partition = _partition_groups(
        tuple(parent.product_scaffold_group for parent in parents.values()),
        seed=split_seed,
        namespace="product_scaffold",
    )
    class_partition = _partition_groups(
        tuple(parent.reaction_class or "<unavailable>" for parent in parents.values()),
        seed=split_seed,
        namespace="reaction_class",
    )
    novelty = dict(product_novelty_by_parent or {})
    if bool(novelty) != bool(novelty_slice):
        raise ValueError("novelty scores and novelty-slice definition must be supplied together")
    unknown_novelty = sorted(set(novelty) - set(parents))
    if unknown_novelty:
        raise ValueError(f"novelty scores reference unknown parents: {unknown_novelty}")

    assignments: list[SplitAssignmentV1] = []
    for record in dataset.records:
        parent_group = record.grouping_parent_reaction_id
        parent = parents[parent_group]
        class_group = parent.reaction_class or "<unavailable>"
        slices: list[EvaluationSlice] = []
        product_novelty = novelty.get(parent_group)
        if (
            novelty_slice is not None
            and product_novelty is not None
            and product_novelty >= novelty_slice.threshold
        ):
            slices.append(EvaluationSlice.HIGH_NOVELTY)
        if "ring_forming" in parent.tags:
            slices.append(EvaluationSlice.RING_FORMING)
        if "stereo_sensitive" in parent.tags:
            slices.append(EvaluationSlice.STEREO_SENSITIVE)
        assignments.append(
            SplitAssignmentV1(
                record_id=record.record_id,
                parent_reaction_group=parent_group,
                product_scaffold_group=parent.product_scaffold_group,
                reaction_class_group=class_group,
                in_distribution=parent_partition[parent_group],
                scaffold_holdout=scaffold_partition[parent.product_scaffold_group],
                reaction_class_holdout=class_partition[class_group],
                evaluation_slices=tuple(slices),
                product_novelty=product_novelty,
            )
        )
    return BenchmarkSplitManifestV1(
        dataset_id=dataset.manifest.dataset_id,
        dataset_version=dataset.manifest.dataset_version,
        records_sha256=dataset.manifest.records_sha256,
        split_seed=split_seed,
        novelty_slice=novelty_slice,
        assignments=tuple(assignments),
    )
