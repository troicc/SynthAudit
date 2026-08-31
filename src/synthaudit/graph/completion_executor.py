"""Transactional synthon-to-precursor completion execution."""

from __future__ import annotations

from collections.abc import Sequence

from rdkit import Chem

from synthaudit.graph._execution import (
    OperationError,
    bond_type,
    executor_provenance,
    safe_fragments,
)
from synthaudit.graph.atom_maps import (
    AtomMapError,
    affected_atom_maps,
    atom_map_index,
    parse_mapped_molecule,
    validate_fresh_fragment_maps,
)
from synthaudit.graph.diff import graph_diff
from synthaudit.graph.sanitize import SanitationMode, mapped_fragments, sanitize_copy
from synthaudit.schema.edits import (
    AtomStateEdit,
    AttachFragmentEdit,
    AttachmentEdit,
    DetachFragmentEdit,
    SetAtomStateEdit,
    SetExplicitHydrogenEdit,
)
from synthaudit.schema.results import CompletionExecutionResult, ExecutionErrorV1, GraphDiffV1


class AttachmentCompletionExecutor:
    """Apply atom-state edits and explicit external-fragment completion."""

    def execute(
        self,
        synthons: str | Sequence[str],
        attachment_edits: Sequence[AttachmentEdit],
        atom_state_edits: Sequence[AtomStateEdit] = (),
        mode: SanitationMode | str = SanitationMode.STRICT,
    ) -> CompletionExecutionResult:
        sanitation_mode = SanitationMode(mode)
        input_structures = (synthons,) if isinstance(synthons, str) else tuple(synthons)
        combined_smiles = ".".join(input_structures)
        try:
            parsed = parse_mapped_molecule(combined_smiles)
        except AtomMapError as exc:
            return self._input_failure(input_structures, exc)
        initial = sanitize_copy(parsed)
        if not initial.success and sanitation_mode == SanitationMode.STRICT:
            return self._sanitation_failure(input_structures, parsed, initial.error_message)

        original = initial.molecule if initial.success else parsed
        working = Chem.RWMol(Chem.Mol(original))
        applied: list[str] = []
        warnings: list[str] = []
        if not initial.success:
            warnings.append("input sanitation failed; diagnostic execution continued")

        operations: list[AtomStateEdit | AttachmentEdit] = [
            *atom_state_edits,
            *attachment_edits,
        ]
        for index, edit in enumerate(operations):
            try:
                if isinstance(edit, (SetAtomStateEdit, SetExplicitHydrogenEdit)):
                    self._apply_atom_state(working, edit)
                else:
                    working = self._apply_attachment(working, edit, sanitation_mode, warnings)
                applied.append(self._label(index, edit))
            except Exception as exc:
                partial = working.GetMol()
                return CompletionExecutionResult(
                    success=False,
                    structurally_valid=False,
                    input_mapped_structures=input_structures,
                    mapped_structures=safe_fragments(original, input_structures),
                    diagnostic_mapped_structures=safe_fragments(partial, ()),
                    applied_operations=tuple(applied),
                    graph_diff=self._safe_diff(original, partial),
                    warnings=tuple(warnings),
                    error=ExecutionErrorV1(
                        error_type=type(exc).__name__,
                        message=str(exc),
                        operation_index=index,
                        operation_type=edit.edit_type,
                        affected_atom_maps=affected_atom_maps(edit),
                        rdkit_error=str(exc) if not isinstance(exc, OperationError) else None,
                    ),
                    provenance=executor_provenance("AttachmentCompletionExecutor"),
                )

        candidate = working.GetMol()
        atom_map_index(candidate)
        outcome = sanitize_copy(candidate)
        if not outcome.success or not initial.success:
            message = outcome.error_message or initial.error_message or "sanitation failed"
            return CompletionExecutionResult(
                success=False,
                structurally_valid=False,
                input_mapped_structures=input_structures,
                mapped_structures=safe_fragments(original, input_structures),
                diagnostic_mapped_structures=safe_fragments(
                    outcome.molecule if outcome.success else candidate, ()
                ),
                applied_operations=tuple(applied),
                graph_diff=self._safe_diff(original, candidate),
                warnings=tuple(warnings),
                error=ExecutionErrorV1(
                    error_type="SanitationError",
                    message=message,
                    operation_index=len(operations) - 1 if operations else None,
                    rdkit_error=message,
                    details={"mode": sanitation_mode.value},
                ),
                provenance=executor_provenance("AttachmentCompletionExecutor"),
            )

        return CompletionExecutionResult(
            success=True,
            structurally_valid=True,
            input_mapped_structures=input_structures,
            mapped_structures=mapped_fragments(outcome.molecule),
            applied_operations=tuple(applied),
            graph_diff=graph_diff(original, outcome.molecule),
            warnings=tuple(warnings),
            provenance=executor_provenance("AttachmentCompletionExecutor"),
        )

    @staticmethod
    def _apply_atom_state(working: Chem.RWMol, edit: AtomStateEdit) -> None:
        mapping = atom_map_index(working)
        try:
            atom = working.GetAtomWithIdx(mapping[edit.atom_map])
        except KeyError as exc:
            raise OperationError(f"dangling atom map reference: {edit.atom_map}") from exc
        if isinstance(edit, SetExplicitHydrogenEdit):
            current = atom.GetNumExplicitHs()
            if edit.from_count is not None and current != edit.from_count:
                raise OperationError(
                    f"explicit hydrogen mismatch: expected {edit.from_count}, got {current}"
                )
            if current == edit.to_count:
                raise OperationError("explicit hydrogen edit is a no-op")
            atom.SetNoImplicit(True)
            atom.SetNumExplicitHs(edit.to_count)
            return

        getters = {
            "formal_charge": atom.GetFormalCharge,
            "isotope": atom.GetIsotope,
            "aromatic": atom.GetIsAromatic,
            "atomic_number": atom.GetAtomicNum,
        }
        current = getters[edit.property]()
        if edit.from_value is not None and current != edit.from_value:
            raise OperationError(
                f"{edit.property} mismatch: expected {edit.from_value}, got {current}"
            )
        if current == edit.to_value:
            raise OperationError(f"{edit.property} edit is a no-op")
        if edit.property == "formal_charge":
            atom.SetFormalCharge(int(edit.to_value))
        elif edit.property == "isotope":
            atom.SetIsotope(int(edit.to_value))
        elif edit.property == "aromatic":
            atom.SetIsAromatic(bool(edit.to_value))
        elif edit.property == "atomic_number":
            if int(edit.to_value) < 1:
                raise OperationError("atomic number changes require a positive element")
            atom.SetAtomicNum(int(edit.to_value))

    def _apply_attachment(
        self,
        working: Chem.RWMol,
        edit: AttachmentEdit,
        mode: SanitationMode,
        warnings: list[str],
    ) -> Chem.RWMol:
        if isinstance(edit, AttachFragmentEdit):
            if edit.attachment_kind == "null":
                if edit.target_atom_map not in atom_map_index(working):
                    raise OperationError(f"dangling null-completion map: {edit.target_atom_map}")
                return working
            if edit.attachment_kind == "charge_only":
                assert edit.target_atom_map is not None
                assert edit.charge_delta is not None
                mapping = atom_map_index(working)
                try:
                    atom = working.GetAtomWithIdx(mapping[edit.target_atom_map])
                except KeyError as exc:
                    raise OperationError(
                        f"dangling charge-completion map: {edit.target_atom_map}"
                    ) from exc
                atom.SetFormalCharge(atom.GetFormalCharge() + edit.charge_delta)
                return working
            return self._attach_fragment(working, edit, mode, warnings)
        if isinstance(edit, DetachFragmentEdit):
            return self._detach_fragment(working, edit)
        raise OperationError(f"unsupported attachment edit: {type(edit).__name__}")

    @staticmethod
    def _attach_fragment(
        working: Chem.RWMol,
        edit: AttachFragmentEdit,
        mode: SanitationMode,
        warnings: list[str],
    ) -> Chem.RWMol:
        assert edit.fragment_smiles is not None
        fragment = parse_mapped_molecule(edit.fragment_smiles)
        current_maps = set(atom_map_index(working))
        fragment_maps = set(validate_fresh_fragment_maps(fragment, current_maps))
        fragment_sanitation = sanitize_copy(fragment)
        if not fragment_sanitation.success:
            if mode == SanitationMode.STRICT:
                raise OperationError(
                    fragment_sanitation.error_message or "fragment sanitation failed"
                )
            warnings.append("fragment sanitation failed; diagnostic execution continued")
        fragment_to_use = fragment_sanitation.molecule if fragment_sanitation.success else fragment
        combined = Chem.RWMol(Chem.CombineMols(working.GetMol(), fragment_to_use))
        mapping = atom_map_index(combined)
        seen_connections: set[tuple[int, int]] = set()
        for connection in edit.connections:
            pair = (connection.product_atom_map, connection.fragment_atom_map)
            if pair in seen_connections:
                raise OperationError(f"duplicate fragment connection: {pair}")
            seen_connections.add(pair)
            if connection.product_atom_map not in current_maps:
                raise OperationError(
                    f"attachment point is not in the synthon: {connection.product_atom_map}"
                )
            if connection.fragment_atom_map not in fragment_maps:
                raise OperationError(
                    f"fragment attachment map is not in the fragment: {connection.fragment_atom_map}"
                )
            index_a = mapping[connection.product_atom_map]
            index_b = mapping[connection.fragment_atom_map]
            if combined.GetBondBetweenAtoms(index_a, index_b) is not None:
                raise OperationError(f"fragment connection already exists: {pair}")
            combined.AddBond(index_a, index_b, bond_type(connection.order))
        return combined

    @staticmethod
    def _detach_fragment(working: Chem.RWMol, edit: DetachFragmentEdit) -> Chem.RWMol:
        mapping = atom_map_index(working)
        for map_a, map_b in edit.attachment_bonds:
            if map_a not in mapping or map_b not in mapping:
                raise OperationError(f"dangling detach bond maps: {(map_a, map_b)}")
            if working.GetBondBetweenAtoms(mapping[map_a], mapping[map_b]) is None:
                raise OperationError(f"detach bond does not exist: {(map_a, map_b)}")
            working.RemoveBond(mapping[map_a], mapping[map_b])
        mapping = atom_map_index(working)
        missing = sorted(set(edit.fragment_atom_maps) - set(mapping))
        if missing:
            raise OperationError(f"fragment atoms do not exist: {missing}")
        for atom_index in sorted((mapping[item] for item in edit.fragment_atom_maps), reverse=True):
            working.RemoveAtom(atom_index)
        return working

    @staticmethod
    def _label(index: int, edit: AtomStateEdit | AttachmentEdit) -> str:
        return f"{index}:{edit.edit_type}" + (f":{edit.edit_id}" if edit.edit_id else "")

    @staticmethod
    def _safe_diff(before: Chem.Mol, after: Chem.Mol) -> GraphDiffV1 | None:
        try:
            return graph_diff(before, after)
        except Exception:
            return None

    @staticmethod
    def _input_failure(inputs: tuple[str, ...], exc: AtomMapError) -> CompletionExecutionResult:
        return CompletionExecutionResult(
            success=False,
            structurally_valid=False,
            input_mapped_structures=inputs,
            mapped_structures=inputs,
            error=ExecutionErrorV1(
                error_type=type(exc).__name__,
                message=str(exc),
                affected_atom_maps=exc.atom_maps,
            ),
            provenance=executor_provenance("AttachmentCompletionExecutor"),
        )

    @staticmethod
    def _sanitation_failure(
        inputs: tuple[str, ...], parsed: Chem.Mol, message: str | None
    ) -> CompletionExecutionResult:
        return CompletionExecutionResult(
            success=False,
            structurally_valid=False,
            input_mapped_structures=inputs,
            mapped_structures=inputs,
            diagnostic_mapped_structures=safe_fragments(parsed, ()),
            error=ExecutionErrorV1(
                error_type="InputSanitationError",
                message=message or "input sanitation failed",
                rdkit_error=message,
            ),
            provenance=executor_provenance("AttachmentCompletionExecutor"),
        )
