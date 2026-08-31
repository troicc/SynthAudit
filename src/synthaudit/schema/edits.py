"""Discriminated ReactionIR edit unions."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, JsonValue, model_validator

from synthaudit.schema.common import StrictModel


class SourceRange(StrictModel):
    """Half-open character range in the source representation."""

    start: int = Field(ge=0)
    end: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_order(self) -> SourceRange:
        if self.end < self.start:
            raise ValueError("source range end must not precede start")
        return self


class EditBase(StrictModel):
    edit_id: str | None = None
    source_range: SourceRange | None = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class BondEditBase(EditBase):
    map_a: int = Field(ge=1)
    map_b: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_distinct_atoms(self) -> BondEditBase:
        if self.map_a == self.map_b:
            raise ValueError("a bond edit requires two distinct atom maps")
        return self


class BreakBondEdit(BondEditBase):
    edit_type: Literal["break_bond"] = "break_bond"
    expected_order: float | None = Field(default=None, gt=0, le=3)


class AddBondEdit(BondEditBase):
    edit_type: Literal["add_bond"] = "add_bond"
    order: float = Field(default=1.0, gt=0, le=3)


class ChangeBondOrderEdit(BondEditBase):
    edit_type: Literal["change_bond_order"] = "change_bond_order"
    from_order: float = Field(gt=0, le=3)
    to_order: float = Field(gt=0, le=3)

    @model_validator(mode="after")
    def validate_real_change(self) -> ChangeBondOrderEdit:
        if self.from_order == self.to_order:
            raise ValueError("bond-order edit must change the order")
        return self


class FragmentConnection(StrictModel):
    product_atom_map: int = Field(ge=1)
    fragment_atom_map: int = Field(ge=1)
    order: float = Field(default=1.0, gt=0, le=3)


class AttachFragmentEdit(EditBase):
    edit_type: Literal["attach_fragment"] = "attach_fragment"
    attachment_kind: Literal["fragment", "null", "charge_only"] = "fragment"
    fragment_smiles: str | None = None
    connections: tuple[FragmentConnection, ...] = ()
    target_atom_map: int | None = Field(default=None, ge=1)
    charge_delta: int | None = None

    @model_validator(mode="after")
    def validate_completion_kind(self) -> AttachFragmentEdit:
        if self.attachment_kind == "fragment":
            if not self.fragment_smiles or not self.connections:
                raise ValueError("fragment completion requires a fragment and connections")
            if self.target_atom_map is not None or self.charge_delta is not None:
                raise ValueError("fragment completion cannot use null/charge-only fields")
        elif self.attachment_kind == "null":
            if self.target_atom_map is None:
                raise ValueError("null completion requires target_atom_map")
            if self.fragment_smiles or self.connections or self.charge_delta is not None:
                raise ValueError("null completion cannot contain fragment or charge fields")
        else:
            if self.target_atom_map is None or self.charge_delta in (None, 0):
                raise ValueError("charge-only completion requires target map and nonzero delta")
            if self.fragment_smiles or self.connections:
                raise ValueError("charge-only completion cannot contain a fragment")
        return self


class DetachFragmentEdit(EditBase):
    edit_type: Literal["detach_fragment"] = "detach_fragment"
    fragment_atom_maps: tuple[int, ...] = Field(min_length=1)
    attachment_bonds: tuple[tuple[int, int], ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_maps(self) -> DetachFragmentEdit:
        if any(atom_map < 1 for atom_map in self.fragment_atom_maps):
            raise ValueError("fragment maps must be positive")
        if len(set(self.fragment_atom_maps)) != len(self.fragment_atom_maps):
            raise ValueError("fragment maps must be unique")
        for map_a, map_b in self.attachment_bonds:
            if map_a < 1 or map_b < 1 or map_a == map_b:
                raise ValueError("attachment bonds require distinct positive maps")
        return self


class SetAtomStateEdit(EditBase):
    edit_type: Literal["set_atom_state"] = "set_atom_state"
    atom_map: int = Field(ge=1)
    property: Literal["formal_charge", "isotope", "aromatic", "atomic_number"]
    from_value: int | bool | None = None
    to_value: int | bool

    @model_validator(mode="after")
    def validate_property_value(self) -> SetAtomStateEdit:
        if self.property == "aromatic" and not isinstance(self.to_value, bool):
            raise ValueError("aromatic state must be boolean")
        if self.property != "aromatic" and isinstance(self.to_value, bool):
            raise ValueError(f"{self.property} state must be integer")
        if self.property in {"isotope", "atomic_number"} and int(self.to_value) < 0:
            raise ValueError(f"{self.property} cannot be negative")
        if self.from_value is not None and self.from_value == self.to_value:
            raise ValueError("atom-state edit must change the value")
        return self


class SetExplicitHydrogenEdit(EditBase):
    edit_type: Literal["set_explicit_hydrogen"] = "set_explicit_hydrogen"
    atom_map: int = Field(ge=1)
    from_count: int | None = Field(default=None, ge=0)
    to_count: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_real_change(self) -> SetExplicitHydrogenEdit:
        if self.from_count is not None and self.from_count == self.to_count:
            raise ValueError("explicit-hydrogen edit must change the count")
        return self


class SetTetrahedralStereoEdit(EditBase):
    edit_type: Literal["set_tetrahedral_stereo"] = "set_tetrahedral_stereo"
    atom_map: int = Field(ge=1)
    configuration: Literal["R", "S", "CW", "CCW"]
    neighbour_maps: tuple[int, ...] = ()


class InvertTetrahedralStereoEdit(EditBase):
    edit_type: Literal["invert_tetrahedral_stereo"] = "invert_tetrahedral_stereo"
    atom_map: int = Field(ge=1)


class ClearTetrahedralStereoEdit(EditBase):
    edit_type: Literal["clear_tetrahedral_stereo"] = "clear_tetrahedral_stereo"
    atom_map: int = Field(ge=1)


class SetBondStereoEdit(BondEditBase):
    edit_type: Literal["set_bond_stereo"] = "set_bond_stereo"
    stereo: Literal["E", "Z"]
    stereo_atom_a: int | None = Field(default=None, ge=1)
    stereo_atom_b: int | None = Field(default=None, ge=1)


class ClearBondStereoEdit(BondEditBase):
    edit_type: Literal["clear_bond_stereo"] = "clear_bond_stereo"


CoreEdit = Annotated[
    BreakBondEdit | AddBondEdit | ChangeBondOrderEdit,
    Field(discriminator="edit_type"),
]
AttachmentEdit = Annotated[
    AttachFragmentEdit | DetachFragmentEdit,
    Field(discriminator="edit_type"),
]
AtomStateEdit = Annotated[
    SetAtomStateEdit | SetExplicitHydrogenEdit,
    Field(discriminator="edit_type"),
]
StereoEdit = Annotated[
    SetTetrahedralStereoEdit
    | InvertTetrahedralStereoEdit
    | ClearTetrahedralStereoEdit
    | SetBondStereoEdit
    | ClearBondStereoEdit,
    Field(discriminator="edit_type"),
]

AnyEdit = CoreEdit | AttachmentEdit | AtomStateEdit | StereoEdit
