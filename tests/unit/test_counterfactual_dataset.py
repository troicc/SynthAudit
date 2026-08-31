from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from synthaudit.adapters.mapped_reaction_smiles import (
    MappedReactionSmilesAdapter,
    MappedReactionSmilesInput,
)
from synthaudit.counterfactuals import (
    BenchmarkLabel,
    BenchmarkSplitManifestV1,
    CounterfactualGenerator,
    DatasetPartition,
    EvaluationSlice,
    GenerationMethod,
    NoveltySliceDefinitionV1,
    build_dataset,
    build_grouped_splits,
    load_dataset,
    write_dataset,
)


def _parent(index: int, reaction_smiles: str, reaction_class: str, tags: tuple[str, ...] = ()):
    reaction = (
        MappedReactionSmilesAdapter()
        .to_reaction_ir(MappedReactionSmilesInput(reaction_smiles=reaction_smiles))
        .model_copy(update={"reaction_id": f"parent-{index}"})
    )
    return CounterfactualGenerator().recorded_reaction(
        reaction,
        record_id=f"recorded-{index}",
        source_dataset="authored-test-fixture",
        source_version="v1",
        data_license_status="Apache-2.0 fixture",
        reaction_class=reaction_class,
        tags=tags,
    )


def _dataset():
    parents = (
        _parent(
            1,
            "[CH3:1][CH2:2][Br:3].[OH-:4]>>[CH3:1][CH2:2][OH:4]",
            "substitution",
        ),
        _parent(
            2,
            "[CH2:1]=[CH:2][CH2:3][CH2:4][CH2:5][CH3:6]>>"
            "[CH2:1]1[CH2:2][CH2:3][CH2:4][CH2:5][CH2:6]1",
            "ring-formation",
            ("ring_forming",),
        ),
        _parent(
            3,
            "[CH3:1][CH:2]=[CH:3][CH3:4]>>[CH3:1]/[CH:2]=[CH:3]/[CH3:4]",
            "stereo",
            ("stereo_sensitive",),
        ),
    )
    children = tuple(
        CounterfactualGenerator().generate_reaction(
            parent,
            method=GenerationMethod.INVALID_CHIRAL_CENTRE_OPERATION,
            seed=100 + index,
        )
        for index, parent in enumerate(parents)
    )
    return build_dataset(
        (*parents, *children),
        dataset_id="unit-counterfactuals",
        dataset_version="v1",
        purpose="software_verification_fixture",
        global_seed=12,
        generator_version=CounterfactualGenerator.generator_version,
    )


def test_dataset_round_trip_and_digest_rejects_tampering(tmp_path: Path) -> None:
    dataset = _dataset()
    records_path, manifest_path = write_dataset(
        dataset,
        records_path=tmp_path / "records.jsonl",
        manifest_path=tmp_path / "manifest.json",
    )
    loaded = load_dataset(records_path=records_path, manifest_path=manifest_path)
    assert loaded == dataset
    assert loaded.manifest.label_counts[BenchmarkLabel.RECORDED_REACTION] == 3
    records_path.write_text(records_path.read_text() + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="SHA-256"):
        load_dataset(records_path=records_path, manifest_path=manifest_path)


def test_grouped_splits_keep_all_derived_records_atomic() -> None:
    dataset = _dataset()
    novelty_definition = NoveltySliceDefinitionV1(
        threshold=0.7,
        training_reference_sha256="a" * 64,
        fingerprint_method="Morgan radius=2 bits=2048 chirality=true",
    )
    novelty = {f"parent-{index}": 0.8 if index == 2 else 0.2 for index in (1, 2, 3)}
    splits = build_grouped_splits(
        dataset,
        split_seed=99,
        product_novelty_by_parent=novelty,
        novelty_slice=novelty_definition,
    )
    by_parent: dict[str, set[DatasetPartition]] = {}
    for assignment in splits.assignments:
        by_parent.setdefault(assignment.parent_reaction_group, set()).add(
            assignment.in_distribution
        )
    assert all(len(partitions) == 1 for partitions in by_parent.values())
    high = [
        item
        for item in splits.assignments
        if EvaluationSlice.HIGH_NOVELTY in item.evaluation_slices
    ]
    assert high and all(item.product_novelty == 0.8 for item in high)
    assert any(
        EvaluationSlice.RING_FORMING in item.evaluation_slices for item in splits.assignments
    )
    assert any(
        EvaluationSlice.STEREO_SENSITIVE in item.evaluation_slices for item in splits.assignments
    )


def test_split_schema_rejects_parent_leakage() -> None:
    dataset = _dataset()
    splits = build_grouped_splits(dataset, split_seed=99)
    payload = splits.model_dump(mode="json")
    first_parent = payload["assignments"][0]["parent_reaction_group"]
    sibling = next(
        item for item in payload["assignments"][1:] if item["parent_reaction_group"] == first_parent
    )
    sibling["in_distribution"] = (
        "test" if payload["assignments"][0]["in_distribution"] != "test" else "train"
    )
    with pytest.raises(ValidationError, match="group leakage"):
        BenchmarkSplitManifestV1.model_validate(payload)


def test_manifest_count_contract_rejects_manual_edit() -> None:
    payload = _dataset().model_dump(mode="json")
    payload["manifest"]["record_count"] += 1
    with pytest.raises(ValidationError, match="record count"):
        type(_dataset()).model_validate(json.loads(json.dumps(payload)))
