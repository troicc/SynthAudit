"""Adapter for the inspected Synthelite nested ReactionTree export."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, cast

from pydantic import JsonValue
from rdkit import Chem

from synthaudit import __version__
from synthaudit.adapters.errors import AtomMappingRequired
from synthaudit.adapters.mapped_reaction_smiles import (
    MappedReactionSmilesAdapter,
    MappedReactionSmilesInput,
)
from synthaudit.adapters.models import AdapterWarningV1, RouteAdapterResultV1
from synthaudit.schema.common import MoleculeRecord, MoleculeRole, ProvenanceRecord, StrictModel
from synthaudit.schema.route_ir import RouteIRV1, RouteStepIRV1

SYNTHELITE_COMMIT = "45168f8a5846c2fd15a833eddc88bac843b5bbee"
SYNTHELITE_REPOSITORY = "https://github.com/schwallergroup/synthelite"


class SyntheliteRouteInput(StrictModel):
    payload: JsonValue
    route_id: str | None = None


@dataclass
class _TreeState:
    steps: list[RouteStepIRV1]
    starting_materials: list[MoleculeRecord]
    intermediates: list[MoleculeRecord]
    warnings: list[AdapterWarningV1]
    unsupported_fields: list[str]


def _node(value: object, *, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"Synthelite node {path} must be an object")
    return {str(key): item for key, item in value.items()}


def _children(node: dict[str, Any], *, path: str) -> list[dict[str, Any]]:
    value = node.get("children", [])
    if not isinstance(value, list):
        raise ValueError(f"Synthelite node {path}.children must be an array")
    return [_node(child, path=f"{path}.children[{index}]") for index, child in enumerate(value)]


def _canonical_unmapped(smiles: str) -> str:
    molecule = cast(Chem.Mol | None, Chem.MolFromSmiles(smiles))
    if molecule is None:
        raise ValueError(f"Synthelite molecule is not valid SMILES: {smiles!r}")
    for atom in molecule.GetAtoms():
        atom.SetAtomMapNum(0)
    return Chem.MolToSmiles(molecule, canonical=True, isomericSmiles=True)


class SyntheliteRouteAdapter:
    """Normalize one fixed route tree; never run Synthelite or map atoms implicitly."""

    adapter_id = f"synthaudit.synthelite-reaction-tree/{SYNTHELITE_COMMIT}"

    def normalize(self, source: SyntheliteRouteInput) -> RouteAdapterResultV1:
        root = _node(source.payload, path="root")
        if root.get("type") != "mol" or not isinstance(root.get("smiles"), str):
            raise ValueError("Synthelite route root must be a molecule node with SMILES")
        state = _TreeState([], [], [], [], [])
        root_record, root_step_id = self._visit_molecule(root, "0", state, is_root=True)
        if root_step_id is None or root_record is None:
            raise AtomMappingRequired(
                "a zero-step or unmapped Synthelite tree cannot form ReactionIR without "
                "an explicit mapped_reaction_smiles artifact"
            )
        serialized = json.dumps(source.payload, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(serialized.encode()).hexdigest()
        route_metadata = root.get("route_metadata", {})
        lmdata = root.get("lmdata", {})
        strategy_text = None
        if isinstance(lmdata, dict):
            for key in ("strategy", "strategy_text", "user_constraint"):
                if isinstance(lmdata.get(key), str):
                    strategy_text = str(lmdata[key])
                    break
        route = RouteIRV1(
            route_id=source.route_id or f"synthelite-{digest[:16]}",
            target=root_record.model_copy(update={"role": MoleculeRole.PRODUCT}),
            starting_materials=tuple(
                sorted(
                    state.starting_materials,
                    key=lambda item: _canonical_unmapped(item.mapped_smiles),
                )
            ),
            intermediates=tuple(
                sorted(
                    state.intermediates,
                    key=lambda item: _canonical_unmapped(item.mapped_smiles),
                )
            ),
            steps=tuple(state.steps),
            strategy_text=strategy_text,
            provenance=(
                ProvenanceRecord(
                    source=SYNTHELITE_REPOSITORY,
                    source_commit=SYNTHELITE_COMMIT,
                    adapter=self.adapter_id,
                    adapter_version=__version__,
                    license="MIT",
                ),
            ),
            metadata={
                "source_sha256": digest,
                "source_route_metadata": route_metadata if isinstance(route_metadata, dict) else {},
                "source_lmdata": lmdata if isinstance(lmdata, dict) else {},
                "unsupported_fields": sorted(state.unsupported_fields),
                "score_semantics": "preserved_upstream_metadata_not_calibrated_probability",
            },
        )
        return RouteAdapterResultV1(
            adapter_id=self.adapter_id,
            route_ir=route,
            warnings=tuple(state.warnings),
            unsupported_fields=tuple(sorted(state.unsupported_fields)),
            source_payload=source.payload,
        )

    def _visit_molecule(
        self,
        molecule_node: dict[str, Any],
        path: str,
        state: _TreeState,
        *,
        is_root: bool,
    ) -> tuple[MoleculeRecord | None, str | None]:
        if molecule_node.get("type") != "mol" or not isinstance(molecule_node.get("smiles"), str):
            raise ValueError(f"Synthelite node {path} is not a molecule")
        known_molecule_fields = {
            "type",
            "hide",
            "smiles",
            "is_chemical",
            "in_stock",
            "children",
            "lmdata",
            "route_metadata",
            "reactionmetrics",
            "conditions",
        }
        state.unsupported_fields.extend(
            f"{path}.{key}" for key in molecule_node if key not in known_molecule_fields
        )
        reaction_children = _children(molecule_node, path=path)
        if not reaction_children:
            return None, None
        if len(reaction_children) != 1 or reaction_children[0].get("type") != "reaction":
            raise ValueError(
                f"Synthelite fixed route molecule {path} must have at most one reaction child"
            )
        reaction_node = reaction_children[0]
        reaction_path = f"{path}.r"
        known_reaction_fields = {
            "type",
            "hide",
            "smiles",
            "is_reaction",
            "metadata",
            "children",
        }
        state.unsupported_fields.extend(
            f"{reaction_path}.{key}" for key in reaction_node if key not in known_reaction_fields
        )
        metadata = reaction_node.get("metadata", {})
        if not isinstance(metadata, dict):
            raise ValueError(f"Synthelite reaction {reaction_path}.metadata must be an object")
        mapped_reaction = metadata.get("mapped_reaction_smiles")
        if not isinstance(mapped_reaction, str) or ":" not in mapped_reaction:
            fallback = reaction_node.get("smiles")
            if isinstance(fallback, str) and ":" in fallback:
                mapped_reaction = fallback
            else:
                raise AtomMappingRequired(
                    f"Synthelite reaction {reaction_path} has no explicit mapped_reaction_smiles"
                )
        step_id = f"step-{path.replace('.', '-')}"
        normalized = MappedReactionSmilesAdapter().normalize(
            MappedReactionSmilesInput(
                reaction_smiles=mapped_reaction,
                reaction_id=f"synthelite:{step_id}",
            )
        )
        state.warnings.extend(normalized.warnings)
        product_record = normalized.reaction_ir.product
        source_product = str(molecule_node["smiles"])
        if _canonical_unmapped(product_record.mapped_smiles) != _canonical_unmapped(source_product):
            raise ValueError(
                f"Synthelite reaction {reaction_path} product disagrees with its molecule node"
            )

        molecule_children = _children(reaction_node, path=reaction_path)
        dependency_ids: list[str] = []
        precursor_by_unmapped: dict[str, list[MoleculeRecord]] = {}
        for precursor in normalized.reaction_ir.expected_precursors:
            precursor_by_unmapped.setdefault(
                _canonical_unmapped(precursor.mapped_smiles), []
            ).append(precursor)
        for child_index, child in enumerate(molecule_children):
            child_path = f"{path}.{child_index}"
            child_smiles = child.get("smiles")
            if child.get("type") != "mol" or not isinstance(child_smiles, str):
                raise ValueError(f"Synthelite reaction child {child_path} must be a molecule")
            key = _canonical_unmapped(child_smiles)
            matches = precursor_by_unmapped.get(key, [])
            mapped_child = matches.pop(0) if matches else None
            child_record, child_step_id = self._visit_molecule(
                child, child_path, state, is_root=False
            )
            if child_step_id is not None:
                dependency_ids.append(child_step_id)
                if child_record is not None:
                    state.intermediates.append(
                        child_record.model_copy(update={"role": MoleculeRole.INTERMEDIATE})
                    )
            elif mapped_child is not None:
                state.starting_materials.append(
                    mapped_child.model_copy(update={"role": MoleculeRole.STARTING_MATERIAL})
                )
            else:
                state.warnings.append(
                    AdapterWarningV1(
                        code="unmatched_route_leaf",
                        message=(
                            f"Synthelite leaf {child_path} is absent from the mapped reaction "
                            "precursor set"
                        ),
                        details={"smiles": child_smiles},
                    )
                )

        unmatched_precursors = tuple(
            precursor.mapped_smiles
            for values in precursor_by_unmapped.values()
            for precursor in values
        )
        if unmatched_precursors:
            state.warnings.append(
                AdapterWarningV1(
                    code="mapped_precursor_absent_from_tree",
                    message=(
                        f"Synthelite reaction {reaction_path} has mapped precursors "
                        "that are absent from its molecule children"
                    ),
                    details={"mapped_precursors": list(unmatched_precursors)},
                )
            )

        state.steps.append(
            RouteStepIRV1(
                step_id=step_id,
                reaction=normalized.reaction_ir,
                depends_on=tuple(sorted(dependency_ids)),
                consumes=tuple(str(child["smiles"]) for child in molecule_children),
                produces=(source_product,),
                strategy_text=(
                    str(metadata["classification"])
                    if isinstance(metadata.get("classification"), str)
                    else None
                ),
                metadata={
                    "synthelite_path": path,
                    "source_reaction_metadata": metadata,
                    "is_root_step": is_root,
                },
            )
        )
        return product_record, step_id

    def to_route_ir(self, source: SyntheliteRouteInput) -> RouteIRV1:
        return self.normalize(source).route_ir
