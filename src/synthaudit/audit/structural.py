"""Deterministic structural audit over ReactionIR and staged execution."""

from __future__ import annotations

from collections.abc import Iterable
from contextlib import suppress
from typing import cast

from rdkit import Chem

from synthaudit.audit.common import check, map_numbers, mapped_molecule, stage_result
from synthaudit.graph.atom_maps import affected_atom_maps, atom_map_index
from synthaudit.graph.executor import ReactionExecutor
from synthaudit.graph.sanitize import sanitize_copy
from synthaudit.schema.edits import (
    AddBondEdit,
    AttachFragmentEdit,
    BreakBondEdit,
    ChangeBondOrderEdit,
    ClearBondStereoEdit,
    ClearTetrahedralStereoEdit,
    DetachFragmentEdit,
    InvertTetrahedralStereoEdit,
    SetBondStereoEdit,
    SetExplicitHydrogenEdit,
    SetTetrahedralStereoEdit,
)
from synthaudit.schema.reaction_ir import ReactionIRV1
from synthaudit.schema.results import (
    CheckResultV1,
    CheckStatus,
    FullExecutionResult,
    Severity,
    StageAuditResultV1,
)


def _pair(map_a: int, map_b: int) -> tuple[int, int]:
    return (min(map_a, map_b), max(map_a, map_b))


def _fragment_maps(fragment_smiles: str) -> tuple[set[int], set[tuple[int, int]]]:
    fragment = cast(Chem.Mol | None, Chem.MolFromSmiles(fragment_smiles, sanitize=False))
    if fragment is None:
        raise ValueError(f"cannot parse attachment fragment: {fragment_smiles!r}")
    mapping = atom_map_index(fragment)
    bonds = {
        _pair(bond.GetBeginAtom().GetAtomMapNum(), bond.GetEndAtom().GetAtomMapNum())
        for bond in fragment.GetBonds()
    }
    return set(mapping), bonds


def _empty_fragment_tokens(smiles_values: Iterable[str]) -> list[str]:
    return [
        value
        for value in smiles_values
        if not value.strip() or value.startswith(".") or value.endswith(".") or ".." in value
    ]


class StructuralAudit:
    """Check graph representation invariants without estimating chemical outcome."""

    def __init__(self, *, edit_complexity_warning: int = 12) -> None:
        if edit_complexity_warning < 1:
            raise ValueError("edit complexity warning threshold must be positive")
        self.edit_complexity_warning = edit_complexity_warning

    def run(
        self,
        reaction: ReactionIRV1,
        execution: FullExecutionResult | None = None,
    ) -> StageAuditResultV1:
        result = execution or ReactionExecutor().execute(reaction)
        checks = [
            self._map_uniqueness(reaction, result),
            self._dangling_references(reaction),
            self._valence(reaction, result),
            self._formal_charge(reaction, result),
            self._aromaticity(reaction, result),
            self._connectivity(reaction),
            self._empty_fragments(reaction),
            self._single_atom_fragments(reaction),
            self._atom_conservation(reaction, result),
            self._unexplained_changes(reaction, result),
            self._operation_noops(result),
            self._edit_complexity(reaction),
        ]
        return stage_result("structural", checks)

    @staticmethod
    def _source_structures(
        reaction: ReactionIRV1,
        execution: FullExecutionResult,
    ) -> tuple[str, ...]:
        final = (
            execution.mapped_structures
            if execution.success
            else execution.diagnostic_mapped_structures
        )
        return (
            reaction.product.mapped_smiles,
            *(item.mapped_smiles for item in reaction.expected_precursors),
            *final,
        )

    def _map_uniqueness(
        self,
        reaction: ReactionIRV1,
        execution: FullExecutionResult,
    ) -> CheckResultV1:
        failures: list[str] = []
        for label, values in (
            ("product", (reaction.product.mapped_smiles,)),
            (
                "expected_precursors",
                tuple(item.mapped_smiles for item in reaction.expected_precursors),
            ),
            (
                "execution_output",
                execution.mapped_structures
                if execution.success
                else execution.diagnostic_mapped_structures,
            ),
        ):
            if not values:
                continue
            try:
                mapped_molecule(values)
            except Exception as exc:
                failures.append(f"{label}: {exc}")
        return check(
            "structural.map_uniqueness",
            "structural",
            CheckStatus.FAIL if failures else CheckStatus.PASS,
            "Atom maps are complete and unique in every inspected stage."
            if not failures
            else "Atom-map validation failed in one or more stages.",
            severity=Severity.BLOCKING if failures else Severity.INFO,
            evidence={"errors": failures},
        )

    def _dangling_references(self, reaction: ReactionIRV1) -> CheckResultV1:
        try:
            available = map_numbers(reaction.product.mapped_smiles)
        except Exception as exc:
            return check(
                "structural.dangling_references",
                "structural",
                CheckStatus.INDETERMINATE,
                "Edit references cannot be checked because the product map set is invalid.",
                evidence={"error": str(exc)},
            )
        dangling: set[int] = set()
        for base_edit in (*reaction.core_edits, *reaction.atom_state_edits):
            dangling.update(set(affected_atom_maps(base_edit)) - available)
        for attachment_edit in reaction.attachment_edits:
            if isinstance(attachment_edit, AttachFragmentEdit):
                if attachment_edit.attachment_kind == "fragment":
                    assert attachment_edit.fragment_smiles is not None
                    try:
                        fragment_maps, _ = _fragment_maps(attachment_edit.fragment_smiles)
                    except Exception:
                        fragment_maps = set()
                    for connection in attachment_edit.connections:
                        if connection.product_atom_map not in available:
                            dangling.add(connection.product_atom_map)
                        if connection.fragment_atom_map not in fragment_maps:
                            dangling.add(connection.fragment_atom_map)
                    available.update(fragment_maps)
                elif attachment_edit.target_atom_map not in available:
                    if attachment_edit.target_atom_map is not None:
                        dangling.add(attachment_edit.target_atom_map)
            elif isinstance(attachment_edit, DetachFragmentEdit):
                dangling.update(set(affected_atom_maps(attachment_edit)) - available)
                available.difference_update(attachment_edit.fragment_atom_maps)
        for stereo_edit in reaction.stereo_edits:
            dangling.update(set(affected_atom_maps(stereo_edit)) - available)
        return check(
            "structural.dangling_references",
            "structural",
            CheckStatus.FAIL if dangling else CheckStatus.PASS,
            "All edit atom references resolve in execution order."
            if not dangling
            else "One or more edits contain dangling atom-map references.",
            severity=Severity.BLOCKING if dangling else Severity.INFO,
            affected_atom_maps=dangling,
            evidence={"dangling_atom_maps": sorted(dangling)},
        )

    def _valence(
        self,
        reaction: ReactionIRV1,
        execution: FullExecutionResult,
    ) -> CheckResultV1:
        errors: list[str] = []
        for value in self._source_structures(reaction, execution):
            try:
                outcome = sanitize_copy(mapped_molecule(value))
                if not outcome.success:
                    errors.append(outcome.error_message or "RDKit sanitation failed")
            except Exception as exc:
                errors.append(str(exc))
        return check(
            "structural.valence",
            "structural",
            CheckStatus.FAIL if errors else CheckStatus.PASS,
            "RDKit sanitation accepted the inspected mapped structures."
            if not errors
            else "Valence or sanitation errors were retained for review.",
            severity=Severity.BLOCKING if errors else Severity.INFO,
            evidence={"rdkit_errors": errors},
        )

    def _formal_charge(
        self,
        reaction: ReactionIRV1,
        execution: FullExecutionResult,
    ) -> CheckResultV1:
        unusual: dict[int, int] = {}
        net_charges: list[int] = []
        for value in self._source_structures(reaction, execution):
            try:
                molecule = mapped_molecule(value)
            except Exception:
                continue
            net_charges.append(sum(atom.GetFormalCharge() for atom in molecule.GetAtoms()))
            unusual.update(
                {
                    atom.GetAtomMapNum(): atom.GetFormalCharge()
                    for atom in molecule.GetAtoms()
                    if abs(atom.GetFormalCharge()) > 3
                }
            )
        status = CheckStatus.WARNING if unusual else CheckStatus.PASS
        return check(
            "structural.formal_charge",
            "structural",
            status,
            "Formal charges were recorded without extreme per-atom values."
            if not unusual
            else "Extreme formal-charge values require expert review.",
            affected_atom_maps=unusual,
            evidence={
                "net_charges": net_charges,
                "review_threshold_absolute_charge": 3,
                "unusual_atom_charges": {str(key): value for key, value in unusual.items()},
            },
        )

    def _aromaticity(
        self,
        reaction: ReactionIRV1,
        execution: FullExecutionResult,
    ) -> CheckResultV1:
        errors: list[str] = []
        for value in self._source_structures(reaction, execution):
            try:
                molecule = mapped_molecule(value)
                outcome = sanitize_copy(molecule)
                if not outcome.success:
                    errors.append(outcome.error_message or "sanitation failed before Kekulization")
                    continue
                candidate = Chem.Mol(outcome.molecule)
                Chem.Kekulize(candidate, clearAromaticFlags=False)
            except Exception as exc:
                errors.append(str(exc))
        return check(
            "structural.aromaticity_kekule",
            "structural",
            CheckStatus.FAIL if errors else CheckStatus.PASS,
            "Aromatic and Kekule forms are internally representable."
            if not errors
            else "Aromaticity or Kekulization failed for an inspected structure.",
            evidence={"errors": errors},
        )

    def _connectivity(self, reaction: ReactionIRV1) -> CheckResultV1:
        disconnected = [
            item.mapped_smiles
            for item in (reaction.product, *reaction.expected_precursors)
            if "." in item.mapped_smiles
        ]
        product_disconnected = "." in reaction.product.mapped_smiles
        return check(
            "structural.connectivity",
            "structural",
            CheckStatus.FAIL
            if product_disconnected
            else (CheckStatus.WARNING if disconnected else CheckStatus.PASS),
            "Each molecule record contains one connected graph."
            if not disconnected
            else "Disconnected components occur inside one or more molecule records.",
            severity=Severity.BLOCKING if product_disconnected else None,
            evidence={"disconnected_records": disconnected},
        )

    def _empty_fragments(self, reaction: ReactionIRV1) -> CheckResultV1:
        values = [
            reaction.product.mapped_smiles,
            *(item.mapped_smiles for item in reaction.expected_precursors),
            *(
                edit.fragment_smiles
                for edit in reaction.attachment_edits
                if isinstance(edit, AttachFragmentEdit) and edit.fragment_smiles is not None
            ),
        ]
        invalid = _empty_fragment_tokens(values)
        return check(
            "structural.empty_fragments",
            "structural",
            CheckStatus.FAIL if invalid else CheckStatus.PASS,
            "No empty fragment token is present."
            if not invalid
            else "Empty fragment syntax is forbidden.",
            severity=Severity.BLOCKING if invalid else Severity.INFO,
            evidence={"invalid_values": invalid},
        )

    def _single_atom_fragments(self, reaction: ReactionIRV1) -> CheckResultV1:
        single_atoms: list[str] = []
        for precursor in reaction.expected_precursors:
            molecule = cast(Chem.Mol | None, Chem.MolFromSmiles(precursor.mapped_smiles))
            if molecule is not None and molecule.GetNumHeavyAtoms() == 1:
                single_atoms.append(precursor.mapped_smiles)
        return check(
            "structural.suspicious_single_atom_fragments",
            "structural",
            CheckStatus.WARNING if single_atoms else CheckStatus.PASS,
            "No single-heavy-atom precursor requires structural review."
            if not single_atoms
            else "Single-heavy-atom precursors are retained but flagged for review.",
            evidence={"fragments": single_atoms},
        )

    def _atom_conservation(
        self,
        reaction: ReactionIRV1,
        execution: FullExecutionResult,
    ) -> CheckResultV1:
        if not execution.success:
            return check(
                "structural.atom_conservation",
                "structural",
                CheckStatus.INDETERMINATE,
                "Atom conservation is indeterminate because full execution failed.",
                evidence={"execution_error": execution.error.message if execution.error else None},
            )
        try:
            product_maps = map_numbers(reaction.product.mapped_smiles)
            output_maps = map_numbers(execution.mapped_structures)
        except Exception as exc:
            return check(
                "structural.atom_conservation",
                "structural",
                CheckStatus.FAIL,
                "Atom-map conservation could not be established.",
                evidence={"error": str(exc)},
            )
        declared_added: set[int] = set()
        declared_removed: set[int] = set()
        for edit in reaction.attachment_edits:
            if isinstance(edit, AttachFragmentEdit) and edit.fragment_smiles:
                try:
                    fragment_maps, _ = _fragment_maps(edit.fragment_smiles)
                    declared_added.update(fragment_maps)
                except Exception:
                    pass
            elif isinstance(edit, DetachFragmentEdit):
                declared_removed.update(edit.fragment_atom_maps)
        unexplained_added = output_maps - product_maps - declared_added
        unexplained_removed = product_maps - output_maps - declared_removed
        failures = unexplained_added | unexplained_removed
        return check(
            "structural.atom_conservation",
            "structural",
            CheckStatus.FAIL if failures else CheckStatus.PASS,
            "All added and removed atom maps are explained by attachment edits."
            if not failures
            else "Execution contains unexplained atom-map additions or removals.",
            affected_atom_maps=failures,
            evidence={
                "unexplained_added": sorted(unexplained_added),
                "unexplained_removed": sorted(unexplained_removed),
            },
        )

    def _unexplained_changes(
        self,
        reaction: ReactionIRV1,
        execution: FullExecutionResult,
    ) -> CheckResultV1:
        diff = execution.graph_diff
        if diff is None:
            return check(
                "structural.unexplained_graph_changes",
                "structural",
                CheckStatus.INDETERMINATE,
                "No full graph diff is available for explanation checking.",
            )
        added_atoms: set[int] = set()
        removed_atoms: set[int] = set()
        added_bonds: set[tuple[int, int]] = set()
        removed_bonds: set[tuple[int, int]] = set()
        order_changes: set[tuple[int, int]] = set()
        atom_properties: set[tuple[int, str]] = set()
        stereo_atoms: set[int] = set()
        stereo_bonds: set[tuple[int, int]] = set()
        product = mapped_molecule(reaction.product.mapped_smiles)
        product_index = atom_map_index(product)
        for core_edit in reaction.core_edits:
            pair = _pair(core_edit.map_a, core_edit.map_b)
            if isinstance(core_edit, BreakBondEdit):
                removed_bonds.add(pair)
            elif isinstance(core_edit, AddBondEdit):
                added_bonds.add(pair)
            elif isinstance(core_edit, ChangeBondOrderEdit):
                order_changes.add(pair)
        for atom_state_edit in reaction.atom_state_edits:
            property_name = (
                "explicit_hydrogens"
                if isinstance(atom_state_edit, SetExplicitHydrogenEdit)
                else atom_state_edit.property
            )
            atom_properties.add((atom_state_edit.atom_map, property_name))
        for attachment_edit in reaction.attachment_edits:
            if isinstance(attachment_edit, AttachFragmentEdit):
                if attachment_edit.attachment_kind == "fragment":
                    assert attachment_edit.fragment_smiles is not None
                    with suppress(Exception):
                        fragment_maps, fragment_bonds = _fragment_maps(
                            attachment_edit.fragment_smiles
                        )
                        added_atoms.update(fragment_maps)
                        added_bonds.update(fragment_bonds)
                    added_bonds.update(
                        _pair(item.product_atom_map, item.fragment_atom_map)
                        for item in attachment_edit.connections
                    )
                elif (
                    attachment_edit.attachment_kind == "charge_only"
                    and attachment_edit.target_atom_map is not None
                ):
                    atom_properties.add((attachment_edit.target_atom_map, "formal_charge"))
            elif isinstance(attachment_edit, DetachFragmentEdit):
                removed_atoms.update(attachment_edit.fragment_atom_maps)
                removed_bonds.update(_pair(*item) for item in attachment_edit.attachment_bonds)
                for atom_map in attachment_edit.fragment_atom_maps:
                    atom_index = product_index.get(atom_map)
                    if atom_index is not None:
                        atom = product.GetAtomWithIdx(atom_index)
                        removed_bonds.update(
                            _pair(atom_map, neighbour.GetAtomMapNum())
                            for neighbour in atom.GetNeighbors()
                        )
        tetrahedral_types = (
            SetTetrahedralStereoEdit,
            InvertTetrahedralStereoEdit,
            ClearTetrahedralStereoEdit,
        )
        bond_stereo_types = (SetBondStereoEdit, ClearBondStereoEdit)
        for stereo_edit in reaction.stereo_edits:
            if isinstance(stereo_edit, tetrahedral_types):
                stereo_atoms.add(stereo_edit.atom_map)
            elif isinstance(stereo_edit, bond_stereo_types):
                stereo_bonds.add(_pair(stereo_edit.map_a, stereo_edit.map_b))

        unexplained: list[str] = []
        unexplained.extend(
            f"added_atom:{item.atom_map}"
            for item in diff.added_atoms
            if item.atom_map not in added_atoms
        )
        unexplained.extend(
            f"removed_atom:{item.atom_map}"
            for item in diff.removed_atoms
            if item.atom_map not in removed_atoms
        )
        unexplained.extend(
            f"added_bond:{item.map_a}-{item.map_b}"
            for item in diff.added_bonds
            if _pair(item.map_a, item.map_b) not in added_bonds
        )
        unexplained.extend(
            f"removed_bond:{item.map_a}-{item.map_b}"
            for item in diff.removed_bonds
            if _pair(item.map_a, item.map_b) not in removed_bonds
        )
        unexplained.extend(
            f"bond_order:{item.map_a}-{item.map_b}"
            for item in diff.changed_bond_orders
            if _pair(item.map_a, item.map_b) not in order_changes
        )
        unexplained.extend(
            f"atom_property:{item.atom_map}:{item.property}"
            for item in diff.changed_atom_properties
            if (item.atom_map, item.property) not in atom_properties
        )
        unexplained.extend(
            f"tetrahedral:{item.atom_maps[0]}"
            for item in diff.changed_tetrahedral_stereo
            if item.atom_maps[0] not in stereo_atoms
        )
        unexplained.extend(
            f"bond_stereo:{item.atom_maps[0]}-{item.atom_maps[1]}"
            for item in diff.changed_bond_stereo
            if _pair(*item.atom_maps) not in stereo_bonds
        )
        return check(
            "structural.unexplained_graph_changes",
            "structural",
            CheckStatus.FAIL if unexplained else CheckStatus.PASS,
            "Every observed graph change is explained by a declared edit."
            if not unexplained
            else "The execution graph diff contains undeclared changes.",
            evidence={"unexplained_changes": unexplained},
        )

    def _operation_noops(self, execution: FullExecutionResult) -> CheckResultV1:
        message = execution.error.message if execution.error else ""
        no_op = "no-op" in message.lower()
        return check(
            "structural.operation_noops",
            "structural",
            CheckStatus.FAIL if no_op else CheckStatus.PASS,
            "No operation was diagnosed as a no-op."
            if not no_op
            else "Execution rejected an operation that produced no graph-state change.",
            evidence={"execution_error": message or None},
        )

    def _edit_complexity(self, reaction: ReactionIRV1) -> CheckResultV1:
        excessive = reaction.edit_count > self.edit_complexity_warning
        return check(
            "structural.edit_complexity",
            "structural",
            CheckStatus.WARNING if excessive else CheckStatus.PASS,
            "Declared edit count is within the transparent review threshold."
            if not excessive
            else "Declared edit count exceeds the review threshold.",
            evidence={
                "edit_count": reaction.edit_count,
                "warning_threshold": self.edit_complexity_warning,
            },
        )
