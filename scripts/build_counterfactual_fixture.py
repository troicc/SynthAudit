"""Build the committed 200-record software-verification counterfactual fixture."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from itertools import cycle, islice
from pathlib import Path

from synthaudit.adapters.mapped_reaction_smiles import (
    MappedReactionSmilesAdapter,
    MappedReactionSmilesInput,
)
from synthaudit.counterfactuals import (
    BenchmarkLabel,
    CounterfactualGenerator,
    EvaluationSlice,
    GenerationMethod,
    NoveltySliceDefinitionV1,
    build_dataset,
    build_grouped_splits,
    write_dataset,
)
from synthaudit.novelty.fingerprints import morgan_fingerprint, tanimoto
from synthaudit.schema import (
    AttachFragmentEdit,
    FragmentConnection,
    MoleculeRecord,
    MoleculeRole,
    ReactionIRV1,
    RouteIRV1,
    RouteStepIRV1,
)

GLOBAL_SEED = 20260831
DATASET_ID = "synthaudit-authored-counterfactual-fixture"
DATASET_VERSION = "1"
SOURCE_DATASET = "synthaudit-authored-software-verification-fixture"
SOURCE_VERSION = "1"
SOURCE_LICENSE = "Apache-2.0 fixture; not experimental reaction evidence"
NOVELTY_THRESHOLD = 0.70


def _mapped(value: str, reaction_id: str) -> ReactionIRV1:
    reaction = MappedReactionSmilesAdapter().to_reaction_ir(
        MappedReactionSmilesInput(reaction_smiles=value)
    )
    return reaction.model_copy(update={"reaction_id": reaction_id})


def _reaction_parents() -> list[tuple[ReactionIRV1, str, tuple[str, ...], str]]:
    substitution_sources = (
        "[CH3:1][CH2:2][Br:3].[OH-:4]>>[CH3:1][CH2:2][OH:4]",
        "[CH3:1][CH2:2][CH2:3][Br:4].[OH-:5]>>[CH3:1][CH2:2][CH2:3][OH:5]",
        "[CH3:1][CH:2]([Br:3])[CH3:4].[OH-:5]>>[CH3:1][CH:2]([OH:5])[CH3:4]",
        "[cH:1]1[cH:2][cH:3][cH:4][cH:5][c:6]1[CH2:7][Br:8].[OH-:9]>>"
        "[cH:1]1[cH:2][cH:3][cH:4][cH:5][c:6]1[CH2:7][OH:9]",
    )
    ring_sources = tuple(
        f"[CH2:1]=[CH:2]{''.join(f'[CH2:{item}]' for item in range(3, size))}"
        f"[CH3:{size}]>>[CH2:1]1"
        f"{''.join(f'[CH2:{item}]' for item in range(2, size + 1))}1"
        for size in (3, 4, 5, 6)
    )
    tetrahedral_source = "[CH3:1][CH:2]([OH:3])[Cl:4]>>[CH3:1][C@@H:2]([OH:3])[Cl:4]"
    alkene_source = "[CH3:1][CH:2]=[CH:3][CH3:4]>>[CH3:1]/[CH:2]=[CH:3]/[CH3:4]"
    values: list[tuple[ReactionIRV1, str, tuple[str, ...], str]] = []
    for index, source in enumerate(substitution_sources, start=1):
        values.append(
            (_mapped(source, f"fixture-substitution-{index}"), "substitution", (), "substitution")
        )
    for index, source in enumerate(ring_sources, start=1):
        values.append(
            (
                _mapped(source, f"fixture-ring-{index}"),
                "ring-formation",
                ("ring_forming",),
                "ring",
            )
        )
    for index in range(1, 5):
        values.append(
            (
                _mapped(tetrahedral_source, f"fixture-tetrahedral-{index}"),
                "tetrahedral-stereo",
                ("stereo_sensitive",),
                "tetrahedral",
            )
        )
    for index in range(1, 5):
        values.append(
            (
                _mapped(alkene_source, f"fixture-alkene-{index}"),
                "alkene-stereo",
                ("stereo_sensitive",),
                "alkene",
            )
        )
    for index in range(1, 3):
        reaction = ReactionIRV1(
            reaction_id=f"fixture-multi-attachment-{index}",
            product=MoleculeRecord(
                mapped_smiles="[CH2:1][CH3:3].[CH2:2][CH3:4]",
                role=MoleculeRole.PRODUCT,
            ),
            attachment_edits=(
                AttachFragmentEdit(
                    fragment_smiles="[O:5]",
                    connections=(
                        FragmentConnection(product_atom_map=1, fragment_atom_map=5),
                        FragmentConnection(product_atom_map=2, fragment_atom_map=5),
                    ),
                ),
            ),
        )
        values.append((reaction, "multi-attachment", (), "multi"))
    return values


def _route(index: int) -> RouteIRV1:
    products = (
        "[CH4:1]",
        "[CH4:2]",
        (
            "[cH:1]1[cH:2][cH:3][cH:4][cH:5][cH:6]1"
            if index == 1
            else "[nH:1]1[cH:2][cH:3][cH:4][cH:5]1"
        ),
    )
    reactions = tuple(
        ReactionIRV1(
            reaction_id=f"fixture-route-{index}-reaction-{step}",
            product=MoleculeRecord(mapped_smiles=product, role=MoleculeRole.PRODUCT),
        )
        for step, product in enumerate(products, start=1)
    )
    return RouteIRV1(
        route_id=f"fixture-route-{index}",
        target=reactions[-1].product,
        starting_materials=(
            MoleculeRecord(
                mapped_smiles="[CH4:10]",
                role=MoleculeRole.STARTING_MATERIAL,
                name=f"route-{index}-start",
                identifiers={"route_node_id": f"route-{index}-start"},
            ),
        ),
        steps=(
            RouteStepIRV1(
                step_id=f"route-{index}-step-1",
                reaction=reactions[0],
                consumes=(f"route-{index}-start",),
                produces=(f"route-{index}-protected",),
                strategy_text="protection",
            ),
            RouteStepIRV1(
                step_id=f"route-{index}-step-2",
                reaction=reactions[1],
                depends_on=(f"route-{index}-step-1",),
                consumes=(f"route-{index}-protected",),
                produces=(f"route-{index}-fragile",),
                strategy_text="coupling",
            ),
            RouteStepIRV1(
                step_id=f"route-{index}-step-3",
                reaction=reactions[2],
                depends_on=(f"route-{index}-step-2",),
                consumes=(f"route-{index}-fragile",),
                produces=(f"route-{index}-target",),
                strategy_text="deprotection",
            ),
        ),
    )


SUBSTITUTION_METHODS = tuple(
    method
    for method in GenerationMethod
    if method
    in {
        GenerationMethod.DUPLICATE_ATOM_MAPS,
        GenerationMethod.DANGLING_ATOM_MAPS,
        GenerationMethod.MALFORMED_EDIT,
        GenerationMethod.MISSING_ATTACHMENT_REFERENCE,
        GenerationMethod.IMPOSSIBLE_OPERATION_ORDERING,
        GenerationMethod.INVALID_LEAVING_GROUP_SYNTAX,
        GenerationMethod.WRONG_BOND_BREAK,
        GenerationMethod.WRONG_BOND_ORDER_CHANGE,
        GenerationMethod.ALTERNATIVE_SITE_SWAP,
        GenerationMethod.CLASS_PRESERVING_CENTRE_DECOY,
        GenerationMethod.UNEXPLAINED_GRAPH_CHANGE,
        GenerationMethod.WRONG_LEAVING_GROUP,
        GenerationMethod.WRONG_ATTACHMENT_ATOM,
        GenerationMethod.MISSING_LEAVING_GROUP,
        GenerationMethod.DUPLICATE_LEAVING_GROUP,
        GenerationMethod.PRECURSOR_ANALOG_MISSING_HANDLE,
        GenerationMethod.CHARGE_ONLY_COMPLETION_ERROR,
        GenerationMethod.INVALID_CHIRAL_CENTRE_OPERATION,
    }
)
RING_METHODS = (
    GenerationMethod.DUPLICATE_ATOM_MAPS,
    GenerationMethod.DANGLING_ATOM_MAPS,
    GenerationMethod.MALFORMED_EDIT,
    GenerationMethod.IMPOSSIBLE_OPERATION_ORDERING,
    GenerationMethod.WRONG_BOND_BREAK,
    GenerationMethod.WRONG_BOND_ORDER_CHANGE,
    GenerationMethod.ALTERNATIVE_SITE_SWAP,
    GenerationMethod.WRONG_RING_CLOSURE_ATOM,
    GenerationMethod.CLASS_PRESERVING_CENTRE_DECOY,
    GenerationMethod.UNEXPLAINED_GRAPH_CHANGE,
    GenerationMethod.CYCLIC_STEREOCHEMISTRY_CORRUPTION,
    GenerationMethod.INVALID_CHIRAL_CENTRE_OPERATION,
)
TETRAHEDRAL_METHODS = (
    GenerationMethod.DUPLICATE_ATOM_MAPS,
    GenerationMethod.DANGLING_ATOM_MAPS,
    GenerationMethod.MALFORMED_EDIT,
    GenerationMethod.UNINTENDED_INVERSION,
    GenerationMethod.OMITTED_STEREOCHEMISTRY,
    GenerationMethod.INVALID_CHIRAL_CENTRE_OPERATION,
)
ALKENE_METHODS = (
    GenerationMethod.DUPLICATE_ATOM_MAPS,
    GenerationMethod.DANGLING_ATOM_MAPS,
    GenerationMethod.MALFORMED_EDIT,
    GenerationMethod.OMITTED_STEREOCHEMISTRY,
    GenerationMethod.INCORRECT_E_Z,
    GenerationMethod.INVALID_CHIRAL_CENTRE_OPERATION,
)
MULTI_METHODS = (
    GenerationMethod.DUPLICATE_ATOM_MAPS,
    GenerationMethod.DANGLING_ATOM_MAPS,
    GenerationMethod.MALFORMED_EDIT,
    GenerationMethod.MISSING_ATTACHMENT_REFERENCE,
    GenerationMethod.INVALID_LEAVING_GROUP_SYNTAX,
    GenerationMethod.WRONG_LEAVING_GROUP,
    GenerationMethod.WRONG_ATTACHMENT_ATOM,
    GenerationMethod.MISSING_LEAVING_GROUP,
    GenerationMethod.DUPLICATE_LEAVING_GROUP,
    GenerationMethod.CHARGE_ONLY_COMPLETION_ERROR,
    GenerationMethod.MULTI_ATTACHMENT_TOPOLOGY_ERROR,
)
ROUTE_METHODS = (
    GenerationMethod.DEPENDENCY_VIOLATING_STEP_SWAP,
    GenerationMethod.DEPROTECTION_TOO_EARLY,
    GenerationMethod.PROTECTION_TOO_LATE,
    GenerationMethod.FRAGILE_INTERMEDIATE_INCOMPATIBLE_CONDITIONS,
    GenerationMethod.PRECURSOR_NOT_PRODUCED,
)


def _method_schedule(kind: str, offset: int) -> tuple[GenerationMethod, ...]:
    source = {
        "substitution": SUBSTITUTION_METHODS,
        "ring": RING_METHODS,
        "tetrahedral": TETRAHEDRAL_METHODS,
        "alkene": ALKENE_METHODS,
        "multi": MULTI_METHODS,
        "route": ROUTE_METHODS,
    }[kind]
    rotated = source[offset % len(source) :] + source[: offset % len(source)]
    return tuple(islice(cycle(rotated), 9))


def _parent_smiles(record: object) -> str:
    reaction = record.reaction
    if reaction is not None:
        return str(reaction.product.mapped_smiles)
    return str(record.route.target.mapped_smiles)


def _novelty_scores(dataset: object, preliminary_splits: object) -> tuple[dict[str, float], str]:
    records = dataset.records
    parents = {
        record.grouping_parent_reaction_id: record
        for record in records
        if record.label == BenchmarkLabel.RECORDED_REACTION
    }
    assignments = preliminary_splits.assignments
    training_ids = sorted(
        {
            item.parent_reaction_group
            for item in assignments
            if item.in_distribution.value == "train"
        }
    )
    reference_payload = [
        {"parent_reaction_id": identifier, "product": _parent_smiles(parents[identifier])}
        for identifier in training_ids
    ]
    reference_sha = hashlib.sha256(
        json.dumps(reference_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    reference_fingerprints = {
        identifier: morgan_fingerprint(_parent_smiles(parents[identifier]))
        for identifier in training_ids
    }
    scores: dict[str, float] = {}
    for identifier, parent in parents.items():
        query = morgan_fingerprint(_parent_smiles(parent))
        similarities = [
            tanimoto(query, fingerprint)
            for reference_id, fingerprint in reference_fingerprints.items()
            if reference_id != identifier
        ]
        if not similarities:
            raise RuntimeError(
                "fixture training reference set is too small for leave-parent-out novelty"
            )
        scores[identifier] = 1.0 - max(similarities)
    return scores, reference_sha


def build_fixture(output_dir: Path) -> None:
    generator = CounterfactualGenerator()
    parents = []
    parent_kinds: list[str] = []
    for index, (reaction, reaction_class, tags, kind) in enumerate(_reaction_parents(), start=1):
        parents.append(
            generator.recorded_reaction(
                reaction,
                record_id=f"recorded-{index:03d}",
                source_dataset=SOURCE_DATASET,
                source_version=SOURCE_VERSION,
                data_license_status=SOURCE_LICENSE,
                reaction_class=reaction_class,
                tags=tags,
            )
        )
        parent_kinds.append(kind)
    for route_index in range(1, 3):
        parents.append(
            generator.recorded_route(
                _route(route_index),
                record_id=f"recorded-{len(parents) + 1:03d}",
                source_dataset=SOURCE_DATASET,
                source_version=SOURCE_VERSION,
                data_license_status=SOURCE_LICENSE,
                reaction_class="route-sequence",
            )
        )
        parent_kinds.append("route")
    if len(parents) != 20:
        raise RuntimeError(f"fixture must have 20 parent records, got {len(parents)}")

    counterfactuals = []
    for parent_index, (parent, kind) in enumerate(zip(parents, parent_kinds, strict=True)):
        for method_index, method in enumerate(_method_schedule(kind, parent_index * 9)):
            seed = GLOBAL_SEED + parent_index * 100 + method_index
            if kind == "route":
                child = generator.generate_route(parent, method=method, seed=seed)
            else:
                child = generator.generate_reaction(parent, method=method, seed=seed)
            counterfactuals.append(child)
    records = tuple((*parents, *counterfactuals))
    if len(records) != 200:
        raise RuntimeError(f"fixture must contain exactly 200 records, got {len(records)}")
    if set(GenerationMethod) - {record.generation_method for record in counterfactuals}:
        raise RuntimeError("fixture does not cover every declared generation method")

    dataset = build_dataset(
        records,
        dataset_id=DATASET_ID,
        dataset_version=DATASET_VERSION,
        purpose="software_verification_fixture",
        global_seed=GLOBAL_SEED,
        generator_version=generator.generator_version,
    )
    preliminary = build_grouped_splits(dataset, split_seed=GLOBAL_SEED)
    novelty_scores, reference_sha = _novelty_scores(dataset, preliminary)
    novelty_definition = NoveltySliceDefinitionV1(
        threshold=NOVELTY_THRESHOLD,
        training_reference_sha256=reference_sha,
        fingerprint_method=(
            "RDKit Morgan radius=2 bits=2048 includeChirality=true; "
            "one_minus_maximum_training_product_morgan_tanimoto"
        ),
    )
    splits = build_grouped_splits(
        dataset,
        split_seed=GLOBAL_SEED,
        product_novelty_by_parent=novelty_scores,
        novelty_slice=novelty_definition,
    )
    slice_counts = {
        slice_name.value: sum(
            slice_name in assignment.evaluation_slices for assignment in splits.assignments
        )
        for slice_name in EvaluationSlice
    }
    if any(count == 0 for count in slice_counts.values()):
        raise RuntimeError(f"every required evaluation slice must be populated: {slice_counts}")

    output_dir.mkdir(parents=True, exist_ok=True)
    write_dataset(
        dataset,
        records_path=output_dir / "records.jsonl",
        manifest_path=output_dir / "manifest.json",
    )
    (output_dir / "splits.json").write_text(
        json.dumps(splits.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    review_records = [
        record
        for record in counterfactuals
        if record.difficulty.value == "hard" and record.structural_validity.structurally_valid
    ]
    with (output_dir / "human-review.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(
            (
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
        )
        for record in review_records:
            writer.writerow(
                (
                    record.record_id,
                    record.parent_reaction_id,
                    record.category.value,
                    record.generation_method.value,
                    record.difficulty.value,
                    record.structural_validity.structurally_valid,
                    "",
                    "",
                    "",
                    "",
                )
            )
    summary = {
        "records": dataset.manifest.record_count,
        "labels": {key.value: value for key, value in dataset.manifest.label_counts.items()},
        "categories": {key.value: value for key, value in dataset.manifest.category_counts.items()},
        "difficulty": {
            key.value: value for key, value in dataset.manifest.difficulty_counts.items()
        },
        "hard_structurally_valid_review_rows": len(review_records),
        "evaluation_slices": slice_counts,
        "metrics": dataset.manifest.metrics_status,
        "records_sha256": dataset.manifest.records_sha256,
    }
    print(json.dumps(summary, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("benchmarks/counterfactual-v1"),
    )
    args = parser.parse_args()
    build_fixture(args.output_dir)


if __name__ == "__main__":
    main()
