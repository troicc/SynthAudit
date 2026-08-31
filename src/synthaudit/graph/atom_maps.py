"""Stable atom-map policy and lookup helpers."""

from __future__ import annotations

from rdkit import Chem

from synthaudit.schema.edits import EditBase


class AtomMapError(ValueError):
    """Raised when stable atom-map invariants are violated."""

    def __init__(self, message: str, atom_maps: tuple[int, ...] = ()) -> None:
        super().__init__(message)
        self.atom_maps = atom_maps


def atom_map_index(molecule: Chem.Mol, *, require_all: bool = True) -> dict[int, int]:
    """Return map -> RDKit index while rejecting zero and duplicate maps."""
    result: dict[int, int] = {}
    missing_indexes: list[int] = []
    duplicates: list[int] = []
    for atom in molecule.GetAtoms():
        atom_map = atom.GetAtomMapNum()
        if atom_map < 1:
            missing_indexes.append(atom.GetIdx())
            continue
        if atom_map in result:
            duplicates.append(atom_map)
        result[atom_map] = atom.GetIdx()
    if require_all and missing_indexes:
        raise AtomMapError(
            f"all atoms require positive atom maps; missing RDKit indexes={missing_indexes}"
        )
    if duplicates:
        raise AtomMapError("duplicate atom maps are forbidden", tuple(sorted(set(duplicates))))
    return result


def max_atom_map(molecule: Chem.Mol) -> int:
    """Return the largest stable map after validating map uniqueness."""
    mapping = atom_map_index(molecule)
    return max(mapping, default=0)


def validate_fresh_fragment_maps(fragment: Chem.Mol, used_maps: set[int]) -> tuple[int, ...]:
    """Require newly introduced atoms to use the next sequential maps."""
    fragment_maps = tuple(atom_map_index(fragment).keys())
    collisions = sorted(set(fragment_maps) & used_maps)
    if collisions:
        raise AtomMapError("introduced fragment reuses existing atom maps", tuple(collisions))
    expected = tuple(
        range(max(used_maps, default=0) + 1, max(used_maps, default=0) + 1 + len(fragment_maps))
    )
    if tuple(sorted(fragment_maps)) != expected:
        raise AtomMapError(
            f"introduced fragment maps must be fresh sequential maps {expected}; got {tuple(sorted(fragment_maps))}",
            tuple(sorted(fragment_maps)),
        )
    return fragment_maps


def affected_atom_maps(edit: EditBase) -> tuple[int, ...]:
    """Collect stable atom maps mentioned by an edit for diagnostics."""
    payload = edit.model_dump(mode="python", exclude_none=True)
    maps: set[int] = set()
    for key, value in payload.items():
        if key.endswith("_map") or key in {"map_a", "map_b", "stereo_atom_a", "stereo_atom_b"}:
            if isinstance(value, int):
                maps.add(value)
        elif key == "fragment_atom_maps":
            maps.update(int(item) for item in value)
        elif key == "attachment_bonds":
            maps.update(int(item) for pair in value for item in pair)
        elif key == "connections":
            for connection in value:
                maps.add(int(connection["product_atom_map"]))
                maps.add(int(connection["fragment_atom_map"]))
    return tuple(sorted(maps))


def parse_mapped_molecule(smiles: str) -> Chem.Mol:
    """Parse without silent mapping or repair, then validate map identity."""
    molecule = Chem.MolFromSmiles(smiles, sanitize=False)
    if molecule is None:
        raise AtomMapError(f"could not parse mapped SMILES: {smiles!r}")
    atom_map_index(molecule)
    return molecule
