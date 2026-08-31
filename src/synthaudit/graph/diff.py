"""Representation-independent molecular graph differences."""

from __future__ import annotations

from rdkit import Chem

from synthaudit.graph.atom_maps import atom_map_index
from synthaudit.schema.results import (
    AtomPropertyChangeV1,
    AtomSnapshotV1,
    BondOrderChangeV1,
    BondSnapshotV1,
    GraphDiffV1,
    StereoChangeV1,
)


def _atom_snapshots(molecule: Chem.Mol) -> dict[int, AtomSnapshotV1]:
    atom_map_index(molecule)
    return {
        atom.GetAtomMapNum(): AtomSnapshotV1(
            atom_map=atom.GetAtomMapNum(),
            atomic_number=atom.GetAtomicNum(),
            formal_charge=atom.GetFormalCharge(),
            isotope=atom.GetIsotope(),
            aromatic=atom.GetIsAromatic(),
            explicit_hydrogens=atom.GetNumExplicitHs(),
            chiral_tag=str(atom.GetChiralTag()),
        )
        for atom in molecule.GetAtoms()
    }


def _bond_snapshots(molecule: Chem.Mol) -> dict[tuple[int, int], BondSnapshotV1]:
    result: dict[tuple[int, int], BondSnapshotV1] = {}
    for bond in molecule.GetBonds():
        map_a = bond.GetBeginAtom().GetAtomMapNum()
        map_b = bond.GetEndAtom().GetAtomMapNum()
        key = (min(map_a, map_b), max(map_a, map_b))
        result[key] = BondSnapshotV1(
            map_a=key[0],
            map_b=key[1],
            order=bond.GetBondTypeAsDouble(),
            stereo=str(bond.GetStereo()),
        )
    return result


def _ring_count(molecule: Chem.Mol) -> int:
    candidate = Chem.Mol(molecule)
    try:
        Chem.GetSymmSSSR(candidate)
        return candidate.GetRingInfo().NumRings()
    except Exception:
        return 0


def graph_diff(before: Chem.Mol, after: Chem.Mol) -> GraphDiffV1:
    """Compare mapped atoms, bonds, stereo, fragments, and rings."""
    before_atoms = _atom_snapshots(before)
    after_atoms = _atom_snapshots(after)
    before_bonds = _bond_snapshots(before)
    after_bonds = _bond_snapshots(after)

    added_maps = sorted(set(after_atoms) - set(before_atoms))
    removed_maps = sorted(set(before_atoms) - set(after_atoms))
    shared_maps = sorted(set(before_atoms) & set(after_atoms))
    added_bond_keys = sorted(set(after_bonds) - set(before_bonds))
    removed_bond_keys = sorted(set(before_bonds) - set(after_bonds))
    shared_bonds = sorted(set(before_bonds) & set(after_bonds))

    atom_changes: list[AtomPropertyChangeV1] = []
    tetra_changes: list[StereoChangeV1] = []
    properties = (
        "atomic_number",
        "formal_charge",
        "isotope",
        "aromatic",
        "explicit_hydrogens",
    )
    for atom_map in shared_maps:
        old = before_atoms[atom_map]
        new = after_atoms[atom_map]
        for property_name in properties:
            old_value = getattr(old, property_name)
            new_value = getattr(new, property_name)
            if old_value != new_value:
                atom_changes.append(
                    AtomPropertyChangeV1(
                        atom_map=atom_map,
                        property=property_name,
                        before=old_value,
                        after=new_value,
                    )
                )
        if old.chiral_tag != new.chiral_tag:
            tetra_changes.append(
                StereoChangeV1(atom_maps=(atom_map,), before=old.chiral_tag, after=new.chiral_tag)
            )

    order_changes: list[BondOrderChangeV1] = []
    bond_stereo_changes: list[StereoChangeV1] = []
    for key in shared_bonds:
        old_bond = before_bonds[key]
        new_bond = after_bonds[key]
        if old_bond.order != new_bond.order:
            order_changes.append(
                BondOrderChangeV1(
                    map_a=key[0],
                    map_b=key[1],
                    before=old_bond.order,
                    after=new_bond.order,
                )
            )
        if old_bond.stereo != new_bond.stereo:
            bond_stereo_changes.append(
                StereoChangeV1(atom_maps=key, before=old_bond.stereo, after=new_bond.stereo)
            )

    return GraphDiffV1(
        added_atoms=tuple(after_atoms[item] for item in added_maps),
        removed_atoms=tuple(before_atoms[item] for item in removed_maps),
        changed_atom_properties=tuple(atom_changes),
        added_bonds=tuple(after_bonds[item] for item in added_bond_keys),
        removed_bonds=tuple(before_bonds[item] for item in removed_bond_keys),
        changed_bond_orders=tuple(order_changes),
        changed_tetrahedral_stereo=tuple(tetra_changes),
        changed_bond_stereo=tuple(bond_stereo_changes),
        precursor_fragment_count_before=len(Chem.GetMolFrags(before)),
        precursor_fragment_count_after=len(Chem.GetMolFrags(after)),
        ring_count_before=_ring_count(before),
        ring_count_after=_ring_count(after),
    )
