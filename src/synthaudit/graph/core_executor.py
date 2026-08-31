"""Transactional product-to-synthon core graph execution."""

from __future__ import annotations

from collections.abc import Sequence
from typing import cast

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
)
from synthaudit.graph.diff import graph_diff
from synthaudit.graph.sanitize import SanitationMode, mapped_fragments, sanitize_copy
from synthaudit.schema.edits import AddBondEdit, BreakBondEdit, ChangeBondOrderEdit, CoreEdit
from synthaudit.schema.results import CoreExecutionResult, ExecutionErrorV1


class CoreGraphExecutor:
    """Apply only reaction-centre edits to a copied mapped product."""

    def execute(
        self,
        product_smiles: str,
        edits: Sequence[CoreEdit],
        mode: SanitationMode | str = SanitationMode.STRICT,
    ) -> CoreExecutionResult:
        sanitation_mode = SanitationMode(mode)
        fallback = (product_smiles,)
        try:
            parsed = parse_mapped_molecule(product_smiles)
        except AtomMapError as exc:
            return self._input_failure(fallback, exc)

        initial = sanitize_copy(parsed)
        if not initial.success and sanitation_mode == SanitationMode.STRICT:
            return CoreExecutionResult(
                success=False,
                structurally_valid=False,
                input_mapped_structures=fallback,
                mapped_structures=fallback,
                error=ExecutionErrorV1(
                    error_type="InputSanitationError",
                    message=initial.error_message or "input sanitation failed",
                    rdkit_error=initial.error_message,
                ),
                provenance=executor_provenance("CoreGraphExecutor"),
            )

        original = initial.molecule if initial.success else parsed
        working = Chem.RWMol(Chem.Mol(original))
        applied: list[str] = []
        warnings: list[str] = []
        if not initial.success:
            warnings.append("input sanitation failed; diagnostic execution continued")

        for index, edit in enumerate(edits):
            try:
                self._apply(working, edit)
                applied.append(self._label(index, edit))
            except Exception as exc:
                partial = working.GetMol()
                return CoreExecutionResult(
                    success=False,
                    structurally_valid=False,
                    input_mapped_structures=fallback,
                    mapped_structures=safe_fragments(original, fallback),
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
                    provenance=executor_provenance("CoreGraphExecutor"),
                )

        candidate = working.GetMol()
        outcome = sanitize_copy(candidate)
        if not outcome.success or not initial.success:
            message = outcome.error_message or initial.error_message or "sanitation failed"
            return CoreExecutionResult(
                success=False,
                structurally_valid=False,
                input_mapped_structures=fallback,
                mapped_structures=safe_fragments(original, fallback),
                diagnostic_mapped_structures=safe_fragments(candidate, ()),
                applied_operations=tuple(applied),
                graph_diff=self._safe_diff(original, candidate),
                warnings=tuple(warnings),
                error=ExecutionErrorV1(
                    error_type="SanitationError",
                    message=message,
                    operation_index=len(edits) - 1 if edits else None,
                    rdkit_error=message,
                    details={"mode": sanitation_mode.value},
                ),
                provenance=executor_provenance("CoreGraphExecutor"),
            )

        return CoreExecutionResult(
            success=True,
            structurally_valid=True,
            input_mapped_structures=fallback,
            mapped_structures=mapped_fragments(outcome.molecule),
            applied_operations=tuple(applied),
            graph_diff=graph_diff(original, outcome.molecule),
            warnings=tuple(warnings),
            provenance=executor_provenance("CoreGraphExecutor"),
        )

    @staticmethod
    def _apply(working: Chem.RWMol, edit: CoreEdit) -> None:
        mapping = atom_map_index(working)
        try:
            index_a = mapping[edit.map_a]
            index_b = mapping[edit.map_b]
        except KeyError as exc:
            raise OperationError(f"dangling atom map reference: {exc.args[0]}") from exc
        bond = cast(Chem.Bond | None, working.GetBondBetweenAtoms(index_a, index_b))

        if isinstance(edit, BreakBondEdit):
            if bond is None:
                raise OperationError("cannot break a bond that does not exist")
            if (
                edit.expected_order is not None
                and bond.GetBondTypeAsDouble() != edit.expected_order
            ):
                raise OperationError(
                    f"bond order mismatch: expected {edit.expected_order}, got {bond.GetBondTypeAsDouble()}"
                )
            working.RemoveBond(index_a, index_b)
        elif isinstance(edit, AddBondEdit):
            if bond is not None:
                raise OperationError("cannot add a bond that already exists")
            working.AddBond(index_a, index_b, bond_type(edit.order))
        elif isinstance(edit, ChangeBondOrderEdit):
            if bond is None:
                raise OperationError("cannot change a bond that does not exist")
            if bond.GetBondTypeAsDouble() != edit.from_order:
                raise OperationError(
                    f"bond order mismatch: expected {edit.from_order}, got {bond.GetBondTypeAsDouble()}"
                )
            bond.SetBondType(bond_type(edit.to_order))
            bond.SetIsAromatic(edit.to_order == 1.5)
            if edit.to_order != 2.0:
                bond.SetStereo(Chem.BondStereo.STEREONONE)
        else:  # defensive if a caller bypasses Pydantic's discriminated union
            raise OperationError(f"unsupported core edit: {type(edit).__name__}")

    @staticmethod
    def _label(index: int, edit: CoreEdit) -> str:
        return f"{index}:{edit.edit_type}" + (f":{edit.edit_id}" if edit.edit_id else "")

    @staticmethod
    def _safe_diff(before: Chem.Mol, after: Chem.Mol):  # type: ignore[no-untyped-def]
        try:
            return graph_diff(before, after)
        except Exception:
            return None

    @staticmethod
    def _input_failure(fallback: tuple[str, ...], exc: AtomMapError) -> CoreExecutionResult:
        return CoreExecutionResult(
            success=False,
            structurally_valid=False,
            input_mapped_structures=fallback,
            mapped_structures=fallback,
            error=ExecutionErrorV1(
                error_type=type(exc).__name__,
                message=str(exc),
                affected_atom_maps=exc.atom_maps,
            ),
            provenance=executor_provenance("CoreGraphExecutor"),
        )
