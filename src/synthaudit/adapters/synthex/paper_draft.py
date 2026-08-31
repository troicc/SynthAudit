"""Explicitly unofficial `synthaudit.synthex-paper-draft/0.1` normalization."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any, cast

from rdkit import Chem

from synthaudit import __version__
from synthaudit.adapters.models import AdapterWarningV1, ReactionAdapterResultV1
from synthaudit.adapters.synthex.errors import UnsupportedAdapterOperation
from synthaudit.adapters.synthex.models import SynthExPaperDraftInput
from synthaudit.graph._execution import bond_type
from synthaudit.graph.atom_maps import atom_map_index
from synthaudit.schema.common import (
    MoleculeRecord,
    MoleculeRole,
    ProvenanceRecord,
    ReactionConditions,
    SourcePayloadReference,
)
from synthaudit.schema.edits import (
    AddBondEdit,
    AttachFragmentEdit,
    BreakBondEdit,
    ChangeBondOrderEdit,
    ClearTetrahedralStereoEdit,
    DetachFragmentEdit,
    FragmentConnection,
    InvertTetrahedralStereoEdit,
    SetAtomStateEdit,
    SetBondStereoEdit,
    SetExplicitHydrogenEdit,
)
from synthaudit.schema.reaction_ir import ReactionIRV1

SYNTHEX_DRAFT_ID = "synthaudit.synthex-paper-draft/0.1"
SYNTHEX_UPSTREAM_COMMIT = "5f41a6b21e3906fde93e84c88bb91f9dc4d37e6f"
SYNTHEX_REPOSITORY = "https://github.com/schwallergroup/synthex"


def _object(value: object, *, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a JSON object")
    return {str(key): item for key, item in value.items()}


def _sequence(value: object, *, label: str) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError(f"{label} must be a JSON array")
    return list(value)


def _required_int(operation: Mapping[str, Any], key: str) -> int:
    value = operation.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{key} must be a positive integer atom map")
    return value


def _number(operation: Mapping[str, Any], key: str) -> float:
    value = operation.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} must be numeric")
    return float(value)


def _operation_metadata(index: int) -> dict[str, int | str]:
    return {"draft_operation_index": index, "adapter_namespace": SYNTHEX_DRAFT_ID}


class SynthExPaperDraftAdapter:
    """Normalize only the locally documented paper-derived operation envelope."""

    adapter_id = SYNTHEX_DRAFT_ID

    def normalize(self, source: SynthExPaperDraftInput) -> ReactionAdapterResultV1:
        payload = source.payload
        if isinstance(payload, list):
            envelope: dict[str, Any] = {"operations": payload}
        else:
            envelope = _object(payload, label="SynthEx draft payload")
        declared_schema = envelope.get("schema_version", envelope.get("schema"))
        if declared_schema is not None and declared_schema != SYNTHEX_DRAFT_ID:
            raise ValueError(
                f"draft payload schema must be {SYNTHEX_DRAFT_ID!r}; got {declared_schema!r}"
            )
        operations = _sequence(envelope.get("operations"), label="operations")
        product_smiles = source.mapped_product_smiles or envelope.get("mapped_product_smiles")
        if not isinstance(product_smiles, str) or not product_smiles:
            raise ValueError("SynthEx draft normalization requires a mapped product")
        product = cast(Chem.Mol | None, Chem.MolFromSmiles(product_smiles))
        if product is None:
            raise ValueError("SynthEx draft product is not valid SMILES")
        product_maps = atom_map_index(product)
        working = Chem.RWMol(Chem.Mol(product))

        known_envelope_fields = {
            "schema",
            "schema_version",
            "reaction_id",
            "mapped_product_smiles",
            "operations",
            "expected_precursors",
            "conditions",
            "metadata",
        }
        unsupported_fields = [key for key in envelope if key not in known_envelope_fields]
        warnings: list[AdapterWarningV1] = [
            AdapterWarningV1(
                code="unofficial_paper_draft",
                message=(
                    "this payload uses SynthAudit's paper-draft namespace and is not "
                    "official SynthEx ReactionJSON"
                ),
            )
        ]
        core_edits: list[AddBondEdit | BreakBondEdit | ChangeBondOrderEdit] = []
        attachment_edits: list[AttachFragmentEdit | DetachFragmentEdit] = []
        atom_state_edits: list[SetAtomStateEdit | SetExplicitHydrogenEdit] = []
        stereo_edits: list[
            InvertTetrahedralStereoEdit | ClearTetrahedralStereoEdit | SetBondStereoEdit
        ] = []
        next_map = max(product_maps) + 1

        for index, raw_operation in enumerate(operations):
            operation = _object(raw_operation, label=f"operations[{index}]")
            operation_name = operation.get("op")
            if not isinstance(operation_name, str):
                raise ValueError(f"operations[{index}].op must be a string")
            metadata = _operation_metadata(index)
            map_index = atom_map_index(working)

            if operation_name in {"break_bond", "add_bond", "change_bond_order"}:
                map_a = _required_int(operation, "map_a")
                map_b = _required_int(operation, "map_b")
                if map_a == map_b or map_a not in map_index or map_b not in map_index:
                    raise ValueError(f"operations[{index}] has invalid bond atom maps")
                rdkit_a, rdkit_b = map_index[map_a], map_index[map_b]
                bond = cast(Chem.Bond | None, working.GetBondBetweenAtoms(rdkit_a, rdkit_b))
                if operation_name == "break_bond":
                    if bond is None:
                        raise ValueError(f"operations[{index}] cannot break a missing bond")
                    current_order = bond.GetBondTypeAsDouble()
                    if "order" in operation and _number(operation, "order") != current_order:
                        raise ValueError(f"operations[{index}] declared bond order does not match")
                    core_edits.append(
                        BreakBondEdit(
                            edit_id=f"synthex-draft:{index}",
                            map_a=map_a,
                            map_b=map_b,
                            expected_order=current_order,
                            metadata=metadata,
                        )
                    )
                    working.RemoveBond(rdkit_a, rdkit_b)
                    allowed = {"op", "map_a", "map_b", "order"}
                elif operation_name == "add_bond":
                    if bond is not None:
                        raise ValueError(f"operations[{index}] cannot add an existing bond")
                    if "order" not in operation:
                        raise ValueError(f"operations[{index}] requires explicit order")
                    target_order = _number(operation, "order")
                    working.AddBond(rdkit_a, rdkit_b, bond_type(target_order))
                    core_edits.append(
                        AddBondEdit(
                            edit_id=f"synthex-draft:{index}",
                            map_a=map_a,
                            map_b=map_b,
                            order=target_order,
                            metadata=metadata,
                        )
                    )
                    allowed = {"op", "map_a", "map_b", "order"}
                else:
                    if bond is None:
                        raise ValueError(f"operations[{index}] cannot change a missing bond")
                    has_order = "order" in operation
                    has_delta = "delta" in operation
                    if has_order == has_delta:
                        raise ValueError(
                            f"operations[{index}] requires exactly one of order or delta"
                        )
                    current_order = bond.GetBondTypeAsDouble()
                    target_order = (
                        _number(operation, "order")
                        if has_order
                        else current_order + _number(operation, "delta")
                    )
                    if target_order == current_order:
                        raise ValueError(f"operations[{index}] is a no-op")
                    bond.SetBondType(bond_type(target_order))
                    core_edits.append(
                        ChangeBondOrderEdit(
                            edit_id=f"synthex-draft:{index}",
                            map_a=map_a,
                            map_b=map_b,
                            from_order=current_order,
                            to_order=target_order,
                            metadata=metadata,
                        )
                    )
                    allowed = {"op", "map_a", "map_b", "order", "delta"}

            elif operation_name in {"change_atom", "set_explicit_h"}:
                atom_map = _required_int(operation, "atom_map")
                if atom_map not in product_maps:
                    raise ValueError(f"operations[{index}] atom edits must reference product atoms")
                atom = product.GetAtomWithIdx(product_maps[atom_map])
                if operation_name == "set_explicit_h":
                    count = operation.get("count")
                    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                        raise ValueError(f"operations[{index}].count must be non-negative")
                    atom_state_edits.append(
                        SetExplicitHydrogenEdit(
                            edit_id=f"synthex-draft:{index}",
                            atom_map=atom_map,
                            from_count=atom.GetNumExplicitHs(),
                            to_count=count,
                            metadata=metadata,
                        )
                    )
                    allowed = {"op", "atom_map", "count"}
                else:
                    property_name = operation.get("property")
                    if property_name == "explicit_h":
                        value = operation.get("value")
                        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                            raise ValueError(
                                f"operations[{index}].value must be a non-negative integer"
                            )
                        atom_state_edits.append(
                            SetExplicitHydrogenEdit(
                                edit_id=f"synthex-draft:{index}",
                                atom_map=atom_map,
                                from_count=atom.GetNumExplicitHs(),
                                to_count=value,
                                metadata=metadata,
                            )
                        )
                    elif property_name in {
                        "formal_charge",
                        "isotope",
                        "aromatic",
                        "atomic_number",
                    }:
                        getters = {
                            "formal_charge": atom.GetFormalCharge,
                            "isotope": atom.GetIsotope,
                            "aromatic": atom.GetIsAromatic,
                            "atomic_number": atom.GetAtomicNum,
                        }
                        value = operation.get("value")
                        atom_state_edits.append(
                            SetAtomStateEdit(
                                edit_id=f"synthex-draft:{index}",
                                atom_map=atom_map,
                                property=property_name,
                                from_value=getters[property_name](),
                                to_value=value,
                                metadata=metadata,
                            )
                        )
                    else:
                        raise UnsupportedAdapterOperation(
                            f"operations[{index}] has unsupported atom property {property_name!r}"
                        )
                    allowed = {"op", "atom_map", "property", "value"}

            elif operation_name == "add_group":
                fragment_smiles = operation.get("fragment_smiles")
                if not isinstance(fragment_smiles, str) or not fragment_smiles:
                    raise ValueError(f"operations[{index}] requires fragment_smiles")
                fragment = cast(Chem.Mol | None, Chem.MolFromSmiles(fragment_smiles))
                if fragment is None:
                    raise ValueError(f"operations[{index}] fragment is not valid SMILES")
                source_fragment_maps = [atom.GetAtomMapNum() for atom in fragment.GetAtoms()]
                nonzero_maps = [value for value in source_fragment_maps if value > 0]
                if len(nonzero_maps) != len(set(nonzero_maps)):
                    raise ValueError(f"operations[{index}] fragment maps must be unique")
                collisions = sorted(set(nonzero_maps) & set(product_maps))
                if collisions:
                    raise ValueError(
                        f"operations[{index}] fragment maps collide with product maps: {collisions}"
                    )
                source_map_to_index = {
                    atom.GetAtomMapNum(): atom.GetIdx()
                    for atom in fragment.GetAtoms()
                    if atom.GetAtomMapNum() > 0
                }
                fresh_by_index: dict[int, int] = {}
                for atom in fragment.GetAtoms():
                    fresh_by_index[atom.GetIdx()] = next_map
                    atom.SetAtomMapNum(next_map)
                    next_map += 1
                raw_connections = _sequence(
                    operation.get("connections"),
                    label=f"operations[{index}].connections",
                )
                connections: list[FragmentConnection] = []
                for connection_index, raw_connection in enumerate(raw_connections):
                    connection = _object(
                        raw_connection,
                        label=f"operations[{index}].connections[{connection_index}]",
                    )
                    product_map = _required_int(connection, "product_atom_map")
                    if product_map not in product_maps:
                        raise ValueError(
                            f"operations[{index}] connection has a dangling product map"
                        )
                    has_index = "fragment_atom_index" in connection
                    has_map = "fragment_atom_map" in connection
                    if has_index == has_map:
                        raise ValueError(
                            f"operations[{index}] connection requires exactly one fragment selector"
                        )
                    if has_index:
                        fragment_index = connection["fragment_atom_index"]
                        if (
                            isinstance(fragment_index, bool)
                            or not isinstance(fragment_index, int)
                            or fragment_index not in fresh_by_index
                        ):
                            raise ValueError(f"operations[{index}] has invalid fragment_atom_index")
                    else:
                        source_fragment_map = _required_int(connection, "fragment_atom_map")
                        if source_fragment_map not in source_map_to_index:
                            raise ValueError(f"operations[{index}] has unknown fragment_atom_map")
                        fragment_index = source_map_to_index[source_fragment_map]
                    order = _number(connection, "order") if "order" in connection else 1.0
                    connections.append(
                        FragmentConnection(
                            product_atom_map=product_map,
                            fragment_atom_map=fresh_by_index[fragment_index],
                            order=order,
                        )
                    )
                if not connections:
                    raise ValueError(f"operations[{index}] requires at least one connection")
                attachment_edits.append(
                    AttachFragmentEdit(
                        edit_id=f"synthex-draft:{index}",
                        fragment_smiles=Chem.MolToSmiles(
                            fragment, canonical=False, isomericSmiles=True
                        ),
                        connections=tuple(connections),
                        metadata={
                            **metadata,
                            "source_fragment_maps": nonzero_maps,
                        },
                    )
                )
                allowed = {"op", "fragment_smiles", "connections"}

            elif operation_name == "remove_group":
                fragment_maps = tuple(
                    int(value)
                    for value in _sequence(
                        operation.get("fragment_atom_maps"),
                        label=f"operations[{index}].fragment_atom_maps",
                    )
                )
                bonds = tuple(
                    tuple(int(value) for value in _sequence(raw, label="attachment bond"))
                    for raw in _sequence(
                        operation.get("attachment_bonds"),
                        label=f"operations[{index}].attachment_bonds",
                    )
                )
                if any(len(pair) != 2 for pair in bonds):
                    raise ValueError(f"operations[{index}] attachment bonds require two maps")
                attachment_edits.append(
                    DetachFragmentEdit(
                        edit_id=f"synthex-draft:{index}",
                        fragment_atom_maps=fragment_maps,
                        attachment_bonds=cast(tuple[tuple[int, int], ...], bonds),
                        metadata=metadata,
                    )
                )
                allowed = {"op", "fragment_atom_maps", "attachment_bonds"}

            elif operation_name in {"invert_stereocenter", "clear_stereocenter"}:
                atom_map = _required_int(operation, "atom_map")
                if atom_map not in product_maps:
                    raise ValueError(f"operations[{index}] has a dangling stereo atom map")
                stereo_edits.append(
                    InvertTetrahedralStereoEdit(
                        edit_id=f"synthex-draft:{index}",
                        atom_map=atom_map,
                        metadata=metadata,
                    )
                    if operation_name == "invert_stereocenter"
                    else ClearTetrahedralStereoEdit(
                        edit_id=f"synthex-draft:{index}",
                        atom_map=atom_map,
                        metadata=metadata,
                    )
                )
                allowed = {"op", "atom_map"}

            elif operation_name == "set_bond_stereo":
                map_a = _required_int(operation, "map_a")
                map_b = _required_int(operation, "map_b")
                stereo = operation.get("stereo")
                if stereo not in {"E", "Z"}:
                    raise ValueError(f"operations[{index}].stereo must be E or Z")
                stereo_edits.append(
                    SetBondStereoEdit(
                        edit_id=f"synthex-draft:{index}",
                        map_a=map_a,
                        map_b=map_b,
                        stereo=stereo,
                        stereo_atom_a=operation.get("stereo_atom_a"),
                        stereo_atom_b=operation.get("stereo_atom_b"),
                        metadata=metadata,
                    )
                )
                allowed = {
                    "op",
                    "map_a",
                    "map_b",
                    "stereo",
                    "stereo_atom_a",
                    "stereo_atom_b",
                }
            else:
                raise UnsupportedAdapterOperation(
                    f"operations[{index}] uses unsupported draft operation {operation_name!r}"
                )

            unsupported_fields.extend(
                f"operations[{index}].{key}" for key in operation if key not in allowed
            )

        expected_precursors: tuple[MoleculeRecord, ...] = ()
        if "expected_precursors" in envelope:
            expected_values = _sequence(
                envelope["expected_precursors"], label="expected_precursors"
            )
            records: list[MoleculeRecord] = []
            for value in expected_values:
                if not isinstance(value, str):
                    raise ValueError("expected_precursors entries must be mapped SMILES strings")
                molecule = cast(Chem.Mol | None, Chem.MolFromSmiles(value))
                if molecule is None:
                    raise ValueError("expected precursor is not valid SMILES")
                atom_map_index(molecule)
                records.append(MoleculeRecord(mapped_smiles=value, role=MoleculeRole.PRECURSOR))
            expected_precursors = tuple(records)

        conditions = None
        if "conditions" in envelope:
            condition_payload = _object(envelope["conditions"], label="conditions")
            conditions = ReactionConditions.model_validate(condition_payload)

        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(serialized.encode()).hexdigest()
        reaction = ReactionIRV1(
            reaction_id=(
                source.reaction_id
                or (str(envelope["reaction_id"]) if "reaction_id" in envelope else None)
                or f"synthex-draft-{digest[:16]}"
            ),
            product=MoleculeRecord(mapped_smiles=product_smiles, role=MoleculeRole.PRODUCT),
            expected_precursors=expected_precursors,
            core_edits=tuple(core_edits),
            attachment_edits=tuple(attachment_edits),
            atom_state_edits=tuple(atom_state_edits),
            stereo_edits=tuple(stereo_edits),
            conditions=conditions,
            stage_metadata={
                "adapter_namespace": SYNTHEX_DRAFT_ID,
                "official_compatibility": False,
                "assumptions": [
                    "operation names are paper-derived",
                    "bond-order delta is added to the current product-side order",
                    "group connection fragment_atom_index is zero-based",
                    "operations are interpreted in listed order within canonical stages",
                ],
                "unsupported_fields": sorted(unsupported_fields),
            },
            provenance=(
                ProvenanceRecord(
                    source=SYNTHEX_REPOSITORY,
                    source_commit=SYNTHEX_UPSTREAM_COMMIT,
                    adapter=SYNTHEX_DRAFT_ID,
                    adapter_version=__version__,
                    metadata={"official_compatibility": False, "upstream_license": "absent"},
                ),
            ),
            source_payload_reference=SourcePayloadReference(
                representation=SYNTHEX_DRAFT_ID,
                sha256=digest,
                media_type="application/json",
                byte_length=len(serialized.encode()),
            ),
            metadata={
                "source_metadata": envelope.get("metadata", {}),
            },
        )
        return ReactionAdapterResultV1(
            adapter_id=SYNTHEX_DRAFT_ID,
            reaction_ir=reaction,
            warnings=tuple(warnings),
            unsupported_fields=tuple(sorted(unsupported_fields)),
            source_payload=payload,
        )

    def to_reaction_ir(self, source: SynthExPaperDraftInput) -> ReactionIRV1:
        return self.normalize(source).reaction_ir
