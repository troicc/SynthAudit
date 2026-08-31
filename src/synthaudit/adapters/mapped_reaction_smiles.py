"""Mapped reaction-SMILES graph-difference adapter."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from typing import cast

from pydantic import Field
from rdkit import Chem

from synthaudit import __version__
from synthaudit.adapters.errors import AtomMappingRequired
from synthaudit.adapters.models import AdapterWarningV1, ReactionAdapterResultV1
from synthaudit.graph.atom_maps import AtomMapError, atom_map_index
from synthaudit.schema.common import (
    MoleculeRecord,
    MoleculeRole,
    ProvenanceRecord,
    SourcePayloadReference,
    StrictModel,
)
from synthaudit.schema.edits import (
    AddBondEdit,
    AttachFragmentEdit,
    BreakBondEdit,
    ChangeBondOrderEdit,
    ClearBondStereoEdit,
    ClearTetrahedralStereoEdit,
    DetachFragmentEdit,
    FragmentConnection,
    InvertTetrahedralStereoEdit,
    SetAtomStateEdit,
    SetBondStereoEdit,
    SetExplicitHydrogenEdit,
    SetTetrahedralStereoEdit,
)
from synthaudit.schema.reaction_ir import ReactionIRV1


class MappedReactionSmilesInput(StrictModel):
    reaction_smiles: str = Field(min_length=1)
    reaction_id: str | None = None


def _parse_smiles(smiles: str, *, label: str) -> Chem.Mol:
    molecule = cast(Chem.Mol | None, Chem.MolFromSmiles(smiles))
    if molecule is None:
        raise ValueError(f"{label} is not valid SMILES: {smiles!r}")
    return molecule


def _map_state(molecule: Chem.Mol) -> str:
    mapped = [atom.GetAtomMapNum() > 0 for atom in molecule.GetAtoms()]
    if all(mapped):
        return "all"
    if not any(mapped):
        return "none"
    return "mixed"


def _induced_molecule(molecule: Chem.Mol, indexes: Iterable[int]) -> Chem.Mol:
    keep = set(indexes)
    editable = Chem.RWMol(Chem.Mol(molecule))
    for index in reversed(range(molecule.GetNumAtoms())):
        if index not in keep:
            editable.RemoveAtom(index)
    return editable.GetMol()


def _component_indexes(molecule: Chem.Mol, allowed: set[int]) -> tuple[tuple[int, ...], ...]:
    remaining = set(allowed)
    components: list[tuple[int, ...]] = []
    while remaining:
        start = min(remaining)
        stack = [start]
        seen: set[int] = set()
        while stack:
            index = stack.pop()
            if index in seen:
                continue
            seen.add(index)
            atom = molecule.GetAtomWithIdx(index)
            stack.extend(
                neighbour.GetIdx()
                for neighbour in atom.GetNeighbors()
                if neighbour.GetIdx() in allowed and neighbour.GetIdx() not in seen
            )
        remaining -= seen
        components.append(tuple(sorted(seen)))
    return tuple(components)


def _canonical_without_maps(molecule: Chem.Mol) -> str:
    copy = Chem.Mol(molecule)
    for atom in copy.GetAtoms():
        atom.SetAtomMapNum(0)
    return Chem.MolToSmiles(copy, canonical=True, isomericSmiles=True)


def _bond_table(molecule: Chem.Mol, allowed_maps: set[int]) -> dict[tuple[int, int], Chem.Bond]:
    result: dict[tuple[int, int], Chem.Bond] = {}
    for bond in molecule.GetBonds():
        map_a = bond.GetBeginAtom().GetAtomMapNum()
        map_b = bond.GetEndAtom().GetAtomMapNum()
        if map_a in allowed_maps and map_b in allowed_maps:
            result[(min(map_a, map_b), max(map_a, map_b))] = bond
    return result


def _cip_by_map(molecule: Chem.Mol) -> dict[int, str]:
    copy = Chem.Mol(molecule)
    Chem.AssignStereochemistry(copy, cleanIt=True, force=True)
    return {
        atom.GetAtomMapNum(): atom.GetProp("_CIPCode")
        for atom in copy.GetAtoms()
        if atom.HasProp("_CIPCode")
    }


def _stereo_code(bond: Chem.Bond) -> str | None:
    if bond.GetStereo() == Chem.BondStereo.STEREOE:
        return "E"
    if bond.GetStereo() == Chem.BondStereo.STEREOZ:
        return "Z"
    return None


class MappedReactionSmilesAdapter:
    """Derive canonical retrosynthetic edits from an already mapped reaction."""

    adapter_id = "synthaudit.mapped-reaction-smiles/1"

    def normalize(self, source: MappedReactionSmilesInput) -> ReactionAdapterResultV1:
        parts = source.reaction_smiles.split(">")
        if len(parts) != 3:
            raise ValueError("mapped reaction SMILES must have reactants>reagents>product")
        reactant_text, reagent_text, product_text = parts
        if not reactant_text or not product_text:
            raise ValueError("mapped reaction requires non-empty reactants and product")
        product = _parse_smiles(product_text, label="product")
        if _map_state(product) != "all":
            raise AtomMappingRequired("every product atom must have a positive atom map")
        try:
            product_map_to_index = atom_map_index(product)
        except AtomMapError as exc:
            raise AtomMappingRequired(str(exc)) from exc

        participant_fragments: list[Chem.Mol] = []
        participant_sources: list[str] = []
        unmapped_reagents: list[str] = []
        warnings: list[AdapterWarningV1] = []
        for fragment_text in reactant_text.split("."):
            fragment = _parse_smiles(fragment_text, label="reactant fragment")
            state = _map_state(fragment)
            if state == "mixed":
                raise AtomMappingRequired(
                    "reactant fragment mixes mapped and unmapped atoms; participation is ambiguous"
                )
            if state == "none":
                unmapped_reagents.append(fragment_text)
            else:
                participant_fragments.append(fragment)
                participant_sources.append(fragment_text)
        if not participant_fragments:
            raise AtomMappingRequired(
                "no fully mapped participating reactant fragment was supplied"
            )
        if unmapped_reagents:
            warnings.append(
                AdapterWarningV1(
                    code="unmapped_left_side_reagents",
                    message="unmapped left-side fragments were retained as reagents, not silently mapped",
                    details={"fragments": unmapped_reagents},
                )
            )
        if reagent_text:
            warnings.append(
                AdapterWarningV1(
                    code="reagent_field_preserved",
                    message="the reaction reagent field is preserved but not treated as a precursor",
                    details={"reagent_smiles": reagent_text},
                )
            )

        precursor = participant_fragments[0]
        for fragment in participant_fragments[1:]:
            precursor = Chem.CombineMols(precursor, fragment)
        try:
            precursor_map_to_index = atom_map_index(precursor)
        except AtomMapError as exc:
            raise AtomMappingRequired(str(exc)) from exc

        product_maps = set(product_map_to_index)
        precursor_maps = set(precursor_map_to_index)
        shared_maps = product_maps & precursor_maps
        missing_product_maps = product_maps - precursor_maps
        external_indexes = {
            atom.GetIdx()
            for atom in precursor.GetAtoms()
            if atom.GetAtomMapNum() not in product_maps
        }

        external_components = list(_component_indexes(precursor, external_indexes))
        external_components.sort(
            key=lambda indexes: (
                _canonical_without_maps(_induced_molecule(precursor, indexes)),
                min(precursor.GetAtomWithIdx(index).GetAtomMapNum() for index in indexes),
            )
        )
        remapped_precursor = Chem.Mol(precursor)
        source_to_fresh: dict[int, int] = {}
        next_map = max(product_maps) + 1
        for component in external_components:
            for index in sorted(
                component,
                key=lambda value: precursor.GetAtomWithIdx(value).GetAtomMapNum(),
            ):
                source_map = precursor.GetAtomWithIdx(index).GetAtomMapNum()
                source_to_fresh[source_map] = next_map
                remapped_precursor.GetAtomWithIdx(index).SetAtomMapNum(next_map)
                next_map += 1

        core_edits: list[AddBondEdit | BreakBondEdit | ChangeBondOrderEdit] = []
        product_bonds = _bond_table(product, shared_maps)
        precursor_bonds = _bond_table(remapped_precursor, shared_maps)
        for pair in sorted(set(product_bonds) | set(precursor_bonds)):
            before = product_bonds.get(pair)
            after = precursor_bonds.get(pair)
            if before is not None and after is None:
                core_edits.append(
                    BreakBondEdit(
                        edit_id=f"mapped:core:{len(core_edits)}",
                        map_a=pair[0],
                        map_b=pair[1],
                        expected_order=before.GetBondTypeAsDouble(),
                    )
                )
            elif before is None and after is not None:
                core_edits.append(
                    AddBondEdit(
                        edit_id=f"mapped:core:{len(core_edits)}",
                        map_a=pair[0],
                        map_b=pair[1],
                        order=after.GetBondTypeAsDouble(),
                    )
                )
            elif before is not None and after is not None:
                old_order = before.GetBondTypeAsDouble()
                new_order = after.GetBondTypeAsDouble()
                if old_order != new_order:
                    core_edits.append(
                        ChangeBondOrderEdit(
                            edit_id=f"mapped:core:{len(core_edits)}",
                            map_a=pair[0],
                            map_b=pair[1],
                            from_order=old_order,
                            to_order=new_order,
                        )
                    )

        attachment_edits: list[AttachFragmentEdit | DetachFragmentEdit] = []
        precursor_old_map_by_index = {
            atom.GetIdx(): atom.GetAtomMapNum() for atom in precursor.GetAtoms()
        }
        for component in external_components:
            fragment = _induced_molecule(remapped_precursor, component)
            fragment_smiles = Chem.MolToSmiles(fragment, canonical=True, isomericSmiles=True)
            component_set = set(component)
            connections: list[FragmentConnection] = []
            for bond in precursor.GetBonds():
                begin = bond.GetBeginAtomIdx()
                end = bond.GetEndAtomIdx()
                if (begin in component_set) == (end in component_set):
                    continue
                fragment_index = begin if begin in component_set else end
                product_index = end if begin in component_set else begin
                product_map = precursor_old_map_by_index[product_index]
                if product_map not in product_maps:
                    continue
                fragment_source_map = precursor_old_map_by_index[fragment_index]
                connections.append(
                    FragmentConnection(
                        product_atom_map=product_map,
                        fragment_atom_map=source_to_fresh[fragment_source_map],
                        order=bond.GetBondTypeAsDouble(),
                    )
                )
            if connections:
                attachment_edits.append(
                    AttachFragmentEdit(
                        edit_id=f"mapped:attach:{len(attachment_edits)}",
                        fragment_smiles=fragment_smiles,
                        connections=tuple(
                            sorted(
                                connections,
                                key=lambda item: (item.product_atom_map, item.fragment_atom_map),
                            )
                        ),
                        metadata={
                            "source_external_maps": sorted(
                                precursor_old_map_by_index[index] for index in component
                            )
                        },
                    )
                )
            else:
                warnings.append(
                    AdapterWarningV1(
                        code="unattached_mapped_fragment",
                        message="a fully mapped precursor fragment is not connected to a product-derived atom",
                        affected_atom_maps=tuple(
                            sorted(
                                source_to_fresh[precursor_old_map_by_index[index]]
                                for index in component
                            )
                        ),
                    )
                )

        if missing_product_maps:
            missing_indexes = {product_map_to_index[value] for value in missing_product_maps}
            for component in _component_indexes(product, missing_indexes):
                component_maps = tuple(
                    sorted(product.GetAtomWithIdx(index).GetAtomMapNum() for index in component)
                )
                component_set = set(component)
                attachment_bonds: list[tuple[int, int]] = []
                for bond in product.GetBonds():
                    begin = bond.GetBeginAtomIdx()
                    end = bond.GetEndAtomIdx()
                    if (begin in component_set) == (end in component_set):
                        continue
                    attachment_bonds.append(
                        (
                            bond.GetBeginAtom().GetAtomMapNum(),
                            bond.GetEndAtom().GetAtomMapNum(),
                        )
                    )
                if attachment_bonds:
                    attachment_edits.append(
                        DetachFragmentEdit(
                            edit_id=f"mapped:detach:{len(attachment_edits)}",
                            fragment_atom_maps=component_maps,
                            attachment_bonds=tuple(attachment_bonds),
                        )
                    )
                else:
                    warnings.append(
                        AdapterWarningV1(
                            code="unbalanced_unrepresentable_atom_loss",
                            message="product atoms absent from precursors cannot be represented as an attached fragment",
                            affected_atom_maps=component_maps,
                        )
                    )

        atom_state_edits: list[SetAtomStateEdit | SetExplicitHydrogenEdit] = []
        remapped_map_to_index = atom_map_index(remapped_precursor)
        for atom_map in sorted(shared_maps):
            before_atom = product.GetAtomWithIdx(product_map_to_index[atom_map])
            after_atom = remapped_precursor.GetAtomWithIdx(remapped_map_to_index[atom_map])
            property_values = (
                ("formal_charge", before_atom.GetFormalCharge(), after_atom.GetFormalCharge()),
                ("isotope", before_atom.GetIsotope(), after_atom.GetIsotope()),
                ("aromatic", before_atom.GetIsAromatic(), after_atom.GetIsAromatic()),
                ("atomic_number", before_atom.GetAtomicNum(), after_atom.GetAtomicNum()),
            )
            for property_name, before_value, after_value in property_values:
                if before_value != after_value:
                    atom_state_edits.append(
                        SetAtomStateEdit(
                            edit_id=f"mapped:atom:{len(atom_state_edits)}",
                            atom_map=atom_map,
                            property=property_name,
                            from_value=before_value,
                            to_value=after_value,
                        )
                    )
            if before_atom.GetNumExplicitHs() != after_atom.GetNumExplicitHs():
                atom_state_edits.append(
                    SetExplicitHydrogenEdit(
                        edit_id=f"mapped:atom:{len(atom_state_edits)}",
                        atom_map=atom_map,
                        from_count=before_atom.GetNumExplicitHs(),
                        to_count=after_atom.GetNumExplicitHs(),
                    )
                )

        stereo_edits: list[
            SetTetrahedralStereoEdit
            | InvertTetrahedralStereoEdit
            | ClearTetrahedralStereoEdit
            | SetBondStereoEdit
            | ClearBondStereoEdit
        ] = []
        product_cip = _cip_by_map(product)
        precursor_cip = _cip_by_map(remapped_precursor)
        for atom_map in sorted(shared_maps):
            before_cip = product_cip.get(atom_map)
            after_cip = precursor_cip.get(atom_map)
            if before_cip == after_cip:
                continue
            if after_cip is None:
                stereo_edits.append(
                    ClearTetrahedralStereoEdit(
                        edit_id=f"mapped:stereo:{len(stereo_edits)}", atom_map=atom_map
                    )
                )
            elif before_cip is not None and {before_cip, after_cip} == {"R", "S"}:
                stereo_edits.append(
                    InvertTetrahedralStereoEdit(
                        edit_id=f"mapped:stereo:{len(stereo_edits)}", atom_map=atom_map
                    )
                )
            else:
                stereo_edits.append(
                    SetTetrahedralStereoEdit(
                        edit_id=f"mapped:stereo:{len(stereo_edits)}",
                        atom_map=atom_map,
                        configuration=after_cip,
                    )
                )
        for pair in sorted(set(product_bonds) & set(precursor_bonds)):
            before_stereo = _stereo_code(product_bonds[pair])
            after_stereo = _stereo_code(precursor_bonds[pair])
            if before_stereo == after_stereo:
                continue
            if after_stereo is None:
                stereo_edits.append(
                    ClearBondStereoEdit(
                        edit_id=f"mapped:stereo:{len(stereo_edits)}",
                        map_a=pair[0],
                        map_b=pair[1],
                    )
                )
            else:
                stereo_edits.append(
                    SetBondStereoEdit(
                        edit_id=f"mapped:stereo:{len(stereo_edits)}",
                        map_a=pair[0],
                        map_b=pair[1],
                        stereo=after_stereo,
                    )
                )

        expected_precursors = tuple(
            MoleculeRecord(
                mapped_smiles=smiles,
                role=MoleculeRole.PRECURSOR,
            )
            for smiles in sorted(
                Chem.MolToSmiles(fragment, canonical=True, isomericSmiles=True)
                for fragment in Chem.GetMolFrags(
                    remapped_precursor, asMols=True, sanitizeFrags=False
                )
            )
        )
        source_bytes = source.reaction_smiles.encode("utf-8")
        digest = hashlib.sha256(source_bytes).hexdigest()
        reaction = ReactionIRV1(
            reaction_id=source.reaction_id or f"mapped-{digest[:16]}",
            product=MoleculeRecord(mapped_smiles=product_text, role=MoleculeRole.PRODUCT),
            expected_precursors=expected_precursors,
            core_edits=tuple(core_edits),
            attachment_edits=tuple(attachment_edits),
            atom_state_edits=tuple(atom_state_edits),
            stereo_edits=tuple(stereo_edits),
            stage_metadata={
                "source_direction": "forward_reaction_smiles",
                "canonical_direction": "retrosynthesis",
                "participating_reactant_fragments": participant_sources,
                "unmapped_left_side_reagents": unmapped_reagents,
                "reagent_field": reagent_text,
                "source_external_map_to_fresh_map": {
                    str(key): value for key, value in sorted(source_to_fresh.items())
                },
            },
            provenance=(
                ProvenanceRecord(
                    source="mapped-reaction-smiles",
                    adapter=self.adapter_id,
                    adapter_version=__version__,
                    license="input-controlled",
                ),
            ),
            source_payload_reference=SourcePayloadReference(
                representation="mapped-reaction-smiles",
                sha256=digest,
                media_type="chemical/x-daylight-smiles",
                byte_length=len(source_bytes),
            ),
        )
        return ReactionAdapterResultV1(
            adapter_id=self.adapter_id,
            reaction_ir=reaction,
            warnings=tuple(warnings),
            source_payload=source.reaction_smiles,
        )

    def to_reaction_ir(self, source: MappedReactionSmilesInput) -> ReactionIRV1:
        return self.normalize(source).reaction_ir
