"""Transactional stereochemistry execution and verification."""

from __future__ import annotations

from collections.abc import Sequence

from rdkit import Chem

from synthaudit.graph._execution import OperationError, executor_provenance, safe_fragments
from synthaudit.graph.atom_maps import (
    AtomMapError,
    affected_atom_maps,
    atom_map_index,
    parse_mapped_molecule,
)
from synthaudit.graph.diff import graph_diff
from synthaudit.graph.sanitize import SanitationMode, mapped_fragments, sanitize_copy
from synthaudit.schema.edits import (
    ClearBondStereoEdit,
    ClearTetrahedralStereoEdit,
    InvertTetrahedralStereoEdit,
    SetBondStereoEdit,
    SetTetrahedralStereoEdit,
    StereoEdit,
)
from synthaudit.schema.results import ExecutionErrorV1, GraphDiffV1, StereoExecutionResult


class StereoExecutor:
    """Apply explicit tetrahedral and E/Z edits after graph completion."""

    def execute(
        self,
        precursors: str | Sequence[str],
        edits: Sequence[StereoEdit],
        mode: SanitationMode | str = SanitationMode.STRICT,
    ) -> StereoExecutionResult:
        sanitation_mode = SanitationMode(mode)
        input_structures = (precursors,) if isinstance(precursors, str) else tuple(precursors)
        try:
            parsed = parse_mapped_molecule(".".join(input_structures))
        except AtomMapError as exc:
            return self._input_failure(input_structures, exc)
        initial = sanitize_copy(parsed)
        if not initial.success:
            return StereoExecutionResult(
                success=False,
                structurally_valid=False,
                input_mapped_structures=input_structures,
                mapped_structures=input_structures,
                diagnostic_mapped_structures=safe_fragments(parsed, ()),
                error=ExecutionErrorV1(
                    error_type="InputSanitationError",
                    message=initial.error_message or "input sanitation failed",
                    rdkit_error=initial.error_message,
                    details={"mode": sanitation_mode.value},
                ),
                provenance=executor_provenance("StereoExecutor"),
            )

        original = initial.molecule
        working = Chem.RWMol(Chem.Mol(original))
        applied: list[str] = []
        for index, edit in enumerate(edits):
            try:
                self._apply(working, edit)
                applied.append(self._label(index, edit))
            except Exception as exc:
                partial = working.GetMol()
                return StereoExecutionResult(
                    success=False,
                    structurally_valid=False,
                    input_mapped_structures=input_structures,
                    mapped_structures=mapped_fragments(original),
                    diagnostic_mapped_structures=safe_fragments(partial, ()),
                    applied_operations=tuple(applied),
                    graph_diff=self._safe_diff(original, partial),
                    error=ExecutionErrorV1(
                        error_type=type(exc).__name__,
                        message=str(exc),
                        operation_index=index,
                        operation_type=edit.edit_type,
                        affected_atom_maps=affected_atom_maps(edit),
                        rdkit_error=str(exc) if not isinstance(exc, OperationError) else None,
                    ),
                    provenance=executor_provenance("StereoExecutor"),
                )

        candidate = working.GetMol()
        outcome = sanitize_copy(candidate)
        if not outcome.success:
            return StereoExecutionResult(
                success=False,
                structurally_valid=False,
                input_mapped_structures=input_structures,
                mapped_structures=mapped_fragments(original),
                diagnostic_mapped_structures=safe_fragments(candidate, ()),
                applied_operations=tuple(applied),
                graph_diff=self._safe_diff(original, candidate),
                error=ExecutionErrorV1(
                    error_type="SanitationError",
                    message=outcome.error_message or "stereo output sanitation failed",
                    operation_index=len(edits) - 1 if edits else None,
                    rdkit_error=outcome.error_message,
                    details={"mode": sanitation_mode.value},
                ),
                provenance=executor_provenance("StereoExecutor"),
            )
        return StereoExecutionResult(
            success=True,
            structurally_valid=True,
            input_mapped_structures=input_structures,
            mapped_structures=mapped_fragments(outcome.molecule),
            applied_operations=tuple(applied),
            graph_diff=graph_diff(original, outcome.molecule),
            provenance=executor_provenance("StereoExecutor"),
        )

    def _apply(self, working: Chem.RWMol, edit: StereoEdit) -> None:
        mapping = atom_map_index(working)
        if isinstance(
            edit,
            (
                SetTetrahedralStereoEdit,
                InvertTetrahedralStereoEdit,
                ClearTetrahedralStereoEdit,
            ),
        ):
            try:
                atom = working.GetAtomWithIdx(mapping[edit.atom_map])
            except KeyError as exc:
                raise OperationError(f"dangling stereocentre map: {edit.atom_map}") from exc
            if isinstance(edit, SetTetrahedralStereoEdit):
                self._set_tetrahedral(working, atom.GetIdx(), edit.configuration)
            elif isinstance(edit, InvertTetrahedralStereoEdit):
                current = atom.GetChiralTag()
                if current == Chem.ChiralType.CHI_TETRAHEDRAL_CW:
                    atom.SetChiralTag(Chem.ChiralType.CHI_TETRAHEDRAL_CCW)
                elif current == Chem.ChiralType.CHI_TETRAHEDRAL_CCW:
                    atom.SetChiralTag(Chem.ChiralType.CHI_TETRAHEDRAL_CW)
                else:
                    raise OperationError("cannot invert an unspecified tetrahedral centre")
            else:
                if atom.GetChiralTag() == Chem.ChiralType.CHI_UNSPECIFIED:
                    raise OperationError("clear tetrahedral stereo is a no-op")
                atom.SetChiralTag(Chem.ChiralType.CHI_UNSPECIFIED)
            return

        try:
            index_a = mapping[edit.map_a]
            index_b = mapping[edit.map_b]
        except KeyError as exc:
            raise OperationError(f"dangling stereo bond map: {exc.args[0]}") from exc
        bond = working.GetBondBetweenAtoms(index_a, index_b)
        if bond is None:
            raise OperationError("stereo edit references a missing bond")
        if isinstance(edit, SetBondStereoEdit):
            if bond.GetBondType() != Chem.BondType.DOUBLE:
                raise OperationError("E/Z stereo requires a double bond")
            reference_a, reference_b = self._stereo_references(
                working, edit, mapping, index_a, index_b
            )
            begin_map = bond.GetBeginAtom().GetAtomMapNum()
            if begin_map == edit.map_a:
                bond.SetStereoAtoms(reference_a, reference_b)
            else:
                bond.SetStereoAtoms(reference_b, reference_a)
            bond.SetStereo(
                Chem.BondStereo.STEREOE if edit.stereo == "E" else Chem.BondStereo.STEREOZ
            )
        elif isinstance(edit, ClearBondStereoEdit):
            if bond.GetStereo() == Chem.BondStereo.STEREONONE:
                raise OperationError("clear bond stereo is a no-op")
            bond.SetStereo(Chem.BondStereo.STEREONONE)
            for atom_index, other_index in ((index_a, index_b), (index_b, index_a)):
                for neighbour_bond in working.GetAtomWithIdx(atom_index).GetBonds():
                    if neighbour_bond.GetOtherAtomIdx(atom_index) != other_index:
                        neighbour_bond.SetBondDir(Chem.BondDir.NONE)
        else:
            raise OperationError(f"unsupported stereo edit: {type(edit).__name__}")

    @staticmethod
    def _set_tetrahedral(working: Chem.RWMol, atom_index: int, configuration: str) -> None:
        atom = working.GetAtomWithIdx(atom_index)
        if atom.GetDegree() < 3:
            raise OperationError("tetrahedral stereo requires at least three explicit neighbours")
        if configuration in {"CW", "CCW"}:
            tag = (
                Chem.ChiralType.CHI_TETRAHEDRAL_CW
                if configuration == "CW"
                else Chem.ChiralType.CHI_TETRAHEDRAL_CCW
            )
            if atom.GetChiralTag() == tag:
                raise OperationError("tetrahedral stereo edit is a no-op")
            atom.SetChiralTag(tag)
            return
        if not StereoExecutor._has_distinct_tetrahedral_substituents(working, atom_index):
            raise OperationError(
                "requested absolute configuration is indeterminate at a symmetric centre"
            )
        for tag in (
            Chem.ChiralType.CHI_TETRAHEDRAL_CW,
            Chem.ChiralType.CHI_TETRAHEDRAL_CCW,
        ):
            candidate = Chem.Mol(working)
            candidate.GetAtomWithIdx(atom_index).SetChiralTag(tag)
            Chem.AssignStereochemistry(candidate, cleanIt=True, force=True)
            candidate_atom = candidate.GetAtomWithIdx(atom_index)
            if (
                candidate_atom.HasProp("_CIPCode")
                and candidate_atom.GetProp("_CIPCode") == configuration
            ):
                if atom.GetChiralTag() == tag:
                    raise OperationError("tetrahedral stereo edit is a no-op")
                atom.SetChiralTag(tag)
                return
        raise OperationError(
            f"requested absolute configuration {configuration} is indeterminate at this centre"
        )

    @staticmethod
    def _has_distinct_tetrahedral_substituents(working: Chem.RWMol, atom_index: int) -> bool:
        candidate = Chem.Mol(working)
        for candidate_atom in candidate.GetAtoms():
            candidate_atom.SetAtomMapNum(0)
            candidate_atom.SetChiralTag(Chem.ChiralType.CHI_UNSPECIFIED)
        ranks = tuple(Chem.CanonicalRankAtoms(candidate, breakTies=False, includeChirality=False))
        atom = candidate.GetAtomWithIdx(atom_index)
        neighbour_ranks = [ranks[item.GetIdx()] for item in atom.GetNeighbors()]
        if atom.GetDegree() == 3 and atom.GetTotalNumHs() > 0:
            neighbour_ranks.append(-1)
        return len(neighbour_ranks) == 4 and len(set(neighbour_ranks)) == 4

    @staticmethod
    def _stereo_references(
        working: Chem.RWMol,
        edit: SetBondStereoEdit,
        mapping: dict[int, int],
        index_a: int,
        index_b: int,
    ) -> tuple[int, int]:
        if edit.stereo_atom_a is not None or edit.stereo_atom_b is not None:
            if edit.stereo_atom_a is None or edit.stereo_atom_b is None:
                raise OperationError("both stereo neighbour maps are required together")
            try:
                reference_a = mapping[edit.stereo_atom_a]
                reference_b = mapping[edit.stereo_atom_b]
            except KeyError as exc:
                raise OperationError(f"dangling stereo neighbour map: {exc.args[0]}") from exc
        else:
            neighbours_a = [
                atom.GetIdx()
                for atom in working.GetAtomWithIdx(index_a).GetNeighbors()
                if atom.GetIdx() != index_b
            ]
            neighbours_b = [
                atom.GetIdx()
                for atom in working.GetAtomWithIdx(index_b).GetNeighbors()
                if atom.GetIdx() != index_a
            ]
            if len(neighbours_a) != 1 or len(neighbours_b) != 1:
                raise OperationError(
                    "stereo neighbour identity is ambiguous; explicit maps are required"
                )
            reference_a, reference_b = neighbours_a[0], neighbours_b[0]
        if reference_a not in {
            atom.GetIdx() for atom in working.GetAtomWithIdx(index_a).GetNeighbors()
        }:
            raise OperationError("stereo_atom_a is not a neighbour of map_a")
        if reference_b not in {
            atom.GetIdx() for atom in working.GetAtomWithIdx(index_b).GetNeighbors()
        }:
            raise OperationError("stereo_atom_b is not a neighbour of map_b")
        return reference_a, reference_b

    @staticmethod
    def _label(index: int, edit: StereoEdit) -> str:
        return f"{index}:{edit.edit_type}" + (f":{edit.edit_id}" if edit.edit_id else "")

    @staticmethod
    def _safe_diff(before: Chem.Mol, after: Chem.Mol) -> GraphDiffV1 | None:
        try:
            return graph_diff(before, after)
        except Exception:
            return None

    @staticmethod
    def _input_failure(inputs: tuple[str, ...], exc: AtomMapError) -> StereoExecutionResult:
        return StereoExecutionResult(
            success=False,
            structurally_valid=False,
            input_mapped_structures=inputs,
            mapped_structures=inputs,
            error=ExecutionErrorV1(
                error_type=type(exc).__name__,
                message=str(exc),
                affected_atom_maps=exc.atom_maps,
            ),
            provenance=executor_provenance("StereoExecutor"),
        )
