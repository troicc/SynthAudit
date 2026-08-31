"""Stereochemistry-specific audit with CIP-aware evidence."""

from __future__ import annotations

from typing import cast

from rdkit import Chem

from synthaudit.audit.common import check, cip_assignments, mapped_molecule, stage_result
from synthaudit.graph.atom_maps import atom_map_index
from synthaudit.graph.executor import ReactionExecutor
from synthaudit.schema.edits import (
    ClearBondStereoEdit,
    ClearTetrahedralStereoEdit,
    InvertTetrahedralStereoEdit,
    SetBondStereoEdit,
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

TETRAHEDRAL_TYPES = (
    SetTetrahedralStereoEdit,
    InvertTetrahedralStereoEdit,
    ClearTetrahedralStereoEdit,
)
BOND_STEREO_TYPES = (SetBondStereoEdit, ClearBondStereoEdit)


class StereoAudit:
    """Audit declared tetrahedral and E/Z semantics after completion."""

    def run(
        self,
        reaction: ReactionIRV1,
        execution: FullExecutionResult | None = None,
    ) -> StageAuditResultV1:
        result = execution or ReactionExecutor().execute(reaction)
        checks = [
            self._centres_exist(reaction, result),
            self._cip_intent(reaction, result),
            self._bond_references(reaction, result),
            self._silent_erasure(reaction, result),
            self._new_centres(reaction, result),
            self._symmetric_centres(reaction, result),
            self._cyclic_path(reaction, result),
            self._stereo_execution(result),
        ]
        return stage_result("stereo", checks)

    @staticmethod
    def _stage_inputs(execution: FullExecutionResult) -> tuple[str, ...]:
        completion = execution.completion_result
        return completion.mapped_structures if completion and completion.success else ()

    def _centres_exist(
        self,
        reaction: ReactionIRV1,
        execution: FullExecutionResult,
    ) -> CheckResultV1:
        inputs = self._stage_inputs(execution)
        if not inputs:
            return check(
                "stereo.centres_exist",
                "stereo",
                CheckStatus.INDETERMINATE,
                "Stereo targets cannot be inspected because completion output is unavailable.",
            )
        try:
            molecule = mapped_molecule(inputs)
            mapping = atom_map_index(molecule)
        except Exception as exc:
            return check(
                "stereo.centres_exist",
                "stereo",
                CheckStatus.INDETERMINATE,
                "Stereo-stage input cannot be parsed.",
                evidence={"error": str(exc)},
            )
        missing: set[int] = set()
        invalid_degree: set[int] = set()
        for edit in reaction.stereo_edits:
            if isinstance(edit, TETRAHEDRAL_TYPES):
                if edit.atom_map not in mapping:
                    missing.add(edit.atom_map)
                elif molecule.GetAtomWithIdx(mapping[edit.atom_map]).GetDegree() < 3:
                    invalid_degree.add(edit.atom_map)
        failures = missing | invalid_degree
        return check(
            "stereo.centres_exist",
            "stereo",
            CheckStatus.FAIL if failures else CheckStatus.PASS,
            "Every tetrahedral target exists and has at least three explicit neighbours."
            if not failures
            else "One or more tetrahedral targets are absent or topologically invalid.",
            severity=Severity.BLOCKING if failures else Severity.INFO,
            affected_atom_maps=failures,
            evidence={
                "missing_atom_maps": sorted(missing),
                "invalid_degree_atom_maps": sorted(invalid_degree),
            },
        )

    def _cip_intent(
        self,
        reaction: ReactionIRV1,
        execution: FullExecutionResult,
    ) -> CheckResultV1:
        tetra_edits = [
            edit for edit in reaction.stereo_edits if isinstance(edit, TETRAHEDRAL_TYPES)
        ]
        if not tetra_edits:
            return check(
                "stereo.cip_intent",
                "stereo",
                CheckStatus.PASS,
                "No tetrahedral CIP transition was declared.",
                evidence={"before_cip": {}, "after_cip": {}},
            )
        inputs = self._stage_inputs(execution)
        stereo = execution.stereo_result
        if not inputs or stereo is None or not stereo.success:
            return check(
                "stereo.cip_intent",
                "stereo",
                CheckStatus.INDETERMINATE,
                "CIP transition is unavailable because stereo execution did not succeed.",
            )
        try:
            before = cip_assignments(inputs)
            after = cip_assignments(stereo.mapped_structures)
        except Exception as exc:
            return check(
                "stereo.cip_intent",
                "stereo",
                CheckStatus.INDETERMINATE,
                "CIP assignment failed for a stereo stage structure.",
                evidence={"error": str(exc)},
            )
        failures: list[str] = []
        indeterminate: list[int] = []
        for edit in tetra_edits:
            atom_map = edit.atom_map
            if isinstance(edit, SetTetrahedralStereoEdit):
                if edit.configuration in {"R", "S"}:
                    if atom_map not in after:
                        indeterminate.append(atom_map)
                    elif after[atom_map] != edit.configuration:
                        failures.append(
                            f"map {atom_map}: expected {edit.configuration}, got {after[atom_map]}"
                        )
            elif isinstance(edit, InvertTetrahedralStereoEdit):
                if atom_map not in before or atom_map not in after:
                    indeterminate.append(atom_map)
                elif before[atom_map] == after[atom_map]:
                    failures.append(f"map {atom_map}: CIP assignment did not invert")
            elif atom_map in after:
                failures.append(f"map {atom_map}: CIP assignment remains after clear")
        status = (
            CheckStatus.FAIL
            if failures
            else (CheckStatus.INDETERMINATE if indeterminate else CheckStatus.PASS)
        )
        return check(
            "stereo.cip_intent",
            "stereo",
            status,
            "CIP assignments before and after stereo edits match declared intent."
            if status == CheckStatus.PASS
            else (
                "CIP assignments contradict one or more declared stereo edits."
                if failures
                else "Absolute CIP intent is indeterminate for one or more targets."
            ),
            affected_atom_maps=indeterminate,
            evidence={
                "before_cip": {str(key): value for key, value in before.items()},
                "after_cip": {str(key): value for key, value in after.items()},
                "failures": failures,
                "indeterminate_atom_maps": sorted(set(indeterminate)),
            },
        )

    def _bond_references(
        self,
        reaction: ReactionIRV1,
        execution: FullExecutionResult,
    ) -> CheckResultV1:
        edits = [edit for edit in reaction.stereo_edits if isinstance(edit, BOND_STEREO_TYPES)]
        if not edits:
            return check(
                "stereo.bond_references",
                "stereo",
                CheckStatus.PASS,
                "No E/Z bond operation was declared.",
            )
        inputs = self._stage_inputs(execution)
        if not inputs:
            return check(
                "stereo.bond_references",
                "stereo",
                CheckStatus.INDETERMINATE,
                "E/Z references cannot be checked without completion output.",
            )
        failures: list[str] = []
        affected: set[int] = set()
        try:
            molecule = mapped_molecule(inputs)
            mapping = atom_map_index(molecule)
            for edit in edits:
                if edit.map_a not in mapping or edit.map_b not in mapping:
                    failures.append(f"missing bond endpoint {edit.map_a}-{edit.map_b}")
                    affected.update((edit.map_a, edit.map_b))
                    continue
                index_a = mapping[edit.map_a]
                index_b = mapping[edit.map_b]
                bond = cast(
                    Chem.Bond | None,
                    molecule.GetBondBetweenAtoms(index_a, index_b),
                )
                if bond is None:
                    failures.append(f"missing stereo bond {edit.map_a}-{edit.map_b}")
                    affected.update((edit.map_a, edit.map_b))
                    continue
                if isinstance(edit, SetBondStereoEdit):
                    if bond.GetBondType() != Chem.BondType.DOUBLE:
                        failures.append(f"non-double stereo bond {edit.map_a}-{edit.map_b}")
                    if (edit.stereo_atom_a is None) != (edit.stereo_atom_b is None):
                        failures.append("both stereo neighbour maps must be supplied together")
                    if edit.stereo_atom_a is not None and edit.stereo_atom_b is not None:
                        for centre_index, other_index, reference_map in (
                            (index_a, index_b, edit.stereo_atom_a),
                            (index_b, index_a, edit.stereo_atom_b),
                        ):
                            neighbour_maps = {
                                atom.GetAtomMapNum()
                                for atom in molecule.GetAtomWithIdx(centre_index).GetNeighbors()
                                if atom.GetIdx() != other_index
                            }
                            if reference_map not in neighbour_maps:
                                failures.append(
                                    f"stereo neighbour map {reference_map} is not adjacent"
                                )
                                affected.add(reference_map)
        except Exception as exc:
            failures.append(str(exc))
        return check(
            "stereo.bond_references",
            "stereo",
            CheckStatus.FAIL if failures else CheckStatus.PASS,
            "Every E/Z edit references a valid double bond and neighbour identity."
            if not failures
            else "One or more E/Z bond references are invalid.",
            affected_atom_maps=affected,
            evidence={"errors": failures},
        )

    def _silent_erasure(
        self,
        reaction: ReactionIRV1,
        execution: FullExecutionResult,
    ) -> CheckResultV1:
        inputs = self._stage_inputs(execution)
        stereo = execution.stereo_result
        if not inputs or stereo is None or not stereo.success:
            return check(
                "stereo.silent_erasure",
                "stereo",
                CheckStatus.INDETERMINATE,
                "Silent stereo erasure cannot be checked after a failed stage.",
            )
        before = mapped_molecule(inputs)
        after = mapped_molecule(stereo.mapped_structures)
        before_mapping = atom_map_index(before)
        after_mapping = atom_map_index(after)
        explicit_atom_targets = {
            edit.atom_map for edit in reaction.stereo_edits if isinstance(edit, TETRAHEDRAL_TYPES)
        }
        explicit_bond_targets = {
            tuple(sorted((edit.map_a, edit.map_b)))
            for edit in reaction.stereo_edits
            if isinstance(edit, BOND_STEREO_TYPES)
        }
        erased_atoms: set[int] = set()
        for atom_map in set(before_mapping) & set(after_mapping):
            old = before.GetAtomWithIdx(before_mapping[atom_map]).GetChiralTag()
            new = after.GetAtomWithIdx(after_mapping[atom_map]).GetChiralTag()
            if (
                old != Chem.ChiralType.CHI_UNSPECIFIED
                and new == Chem.ChiralType.CHI_UNSPECIFIED
                and atom_map not in explicit_atom_targets
            ):
                erased_atoms.add(atom_map)
        erased_bonds: list[list[int]] = []
        for bond in before.GetBonds():
            pair = tuple(
                sorted(
                    (
                        bond.GetBeginAtom().GetAtomMapNum(),
                        bond.GetEndAtom().GetAtomMapNum(),
                    )
                )
            )
            if (
                pair in explicit_bond_targets
                or pair[0] not in after_mapping
                or pair[1] not in after_mapping
            ):
                continue
            new_bond = after.GetBondBetweenAtoms(after_mapping[pair[0]], after_mapping[pair[1]])
            if (
                new_bond is not None
                and bond.GetStereo() != Chem.BondStereo.STEREONONE
                and new_bond.GetStereo() == Chem.BondStereo.STEREONONE
            ):
                erased_bonds.append(list(pair))
        failed = bool(erased_atoms or erased_bonds)
        return check(
            "stereo.silent_erasure",
            "stereo",
            CheckStatus.FAIL if failed else CheckStatus.PASS,
            "No unrequested tetrahedral or bond stereo was erased."
            if not failed
            else "Stereo information disappeared without an explicit clear operation.",
            affected_atom_maps=erased_atoms,
            evidence={
                "erased_atom_maps": sorted(erased_atoms),
                "erased_bonds": erased_bonds,
            },
        )

    def _new_centres(
        self,
        reaction: ReactionIRV1,
        execution: FullExecutionResult,
    ) -> CheckResultV1:
        inputs = self._stage_inputs(execution)
        stereo = execution.stereo_result
        if not inputs or stereo is None or not stereo.success:
            return check(
                "stereo.new_centres",
                "stereo",
                CheckStatus.INDETERMINATE,
                "New stereocentres cannot be detected after failed stereo execution.",
            )
        try:
            before = cip_assignments(inputs)
            after = cip_assignments(stereo.mapped_structures)
        except Exception as exc:
            return check(
                "stereo.new_centres",
                "stereo",
                CheckStatus.INDETERMINATE,
                "New stereocentre CIP assignment failed.",
                evidence={"error": str(exc)},
            )
        new = set(after) - set(before)
        declared = {
            edit.atom_map
            for edit in reaction.stereo_edits
            if isinstance(edit, SetTetrahedralStereoEdit)
        }
        undeclared = new - declared
        return check(
            "stereo.new_centres",
            "stereo",
            CheckStatus.WARNING if undeclared else CheckStatus.PASS,
            "Every newly assigned stereocentre was explicitly declared."
            if not undeclared
            else "Execution created stereocentres without explicit stereo edits.",
            affected_atom_maps=undeclared,
            evidence={
                "new_cip_atom_maps": sorted(new),
                "undeclared_new_atom_maps": sorted(undeclared),
            },
        )

    def _symmetric_centres(
        self,
        reaction: ReactionIRV1,
        execution: FullExecutionResult,
    ) -> CheckResultV1:
        tetra = [edit for edit in reaction.stereo_edits if isinstance(edit, TETRAHEDRAL_TYPES)]
        if not tetra:
            return check(
                "stereo.symmetric_centres",
                "stereo",
                CheckStatus.PASS,
                "No tetrahedral target requires symmetry analysis.",
            )
        inputs = self._stage_inputs(execution)
        if not inputs:
            return check(
                "stereo.symmetric_centres",
                "stereo",
                CheckStatus.INDETERMINATE,
                "Symmetry analysis is unavailable without completion output.",
            )
        molecule = mapped_molecule(inputs)
        mapping = atom_map_index(molecule)
        candidate = Chem.Mol(molecule)
        for atom in candidate.GetAtoms():
            atom.SetAtomMapNum(0)
            atom.SetChiralTag(Chem.ChiralType.CHI_UNSPECIFIED)
        ranks = tuple(Chem.CanonicalRankAtoms(candidate, breakTies=False, includeChirality=False))
        symmetric: set[int] = set()
        for edit in tetra:
            if edit.atom_map not in mapping:
                continue
            atom = candidate.GetAtomWithIdx(mapping[edit.atom_map])
            neighbour_ranks = [ranks[item.GetIdx()] for item in atom.GetNeighbors()]
            if atom.GetDegree() == 3 and atom.GetTotalNumHs() > 0:
                neighbour_ranks.append(-1)
            if len(neighbour_ranks) != 4 or len(set(neighbour_ranks)) != 4:
                symmetric.add(edit.atom_map)
        return check(
            "stereo.symmetric_centres",
            "stereo",
            CheckStatus.INDETERMINATE if symmetric else CheckStatus.PASS,
            "Tetrahedral targets have four distinguishable substituent environments."
            if not symmetric
            else "Symmetric or pseudo-asymmetric targets prevent forced absolute assignment.",
            affected_atom_maps=symmetric,
            evidence={"indeterminate_atom_maps": sorted(symmetric)},
        )

    def _cyclic_path(
        self,
        reaction: ReactionIRV1,
        execution: FullExecutionResult,
    ) -> CheckResultV1:
        inputs = self._stage_inputs(execution)
        if not inputs:
            return check(
                "stereo.cyclic_path",
                "stereo",
                CheckStatus.INDETERMINATE,
                "Cyclic stereo context is unavailable without completion output.",
            )
        molecule = mapped_molecule(inputs)
        mapping = atom_map_index(molecule)
        cyclic: set[int] = set()
        for edit in reaction.stereo_edits:
            if isinstance(edit, TETRAHEDRAL_TYPES):
                if (
                    edit.atom_map in mapping
                    and molecule.GetAtomWithIdx(mapping[edit.atom_map]).IsInRing()
                ):
                    cyclic.add(edit.atom_map)
            elif edit.map_a in mapping and edit.map_b in mapping:
                bond = molecule.GetBondBetweenAtoms(mapping[edit.map_a], mapping[edit.map_b])
                if bond is not None and bond.IsInRing():
                    cyclic.update((edit.map_a, edit.map_b))
        return check(
            "stereo.cyclic_path",
            "stereo",
            CheckStatus.WARNING if cyclic else CheckStatus.PASS,
            "No declared stereo edit occurs in a ring-specific context."
            if not cyclic
            else "Cyclic stereochemical edits require a dedicated expert-review path.",
            affected_atom_maps=cyclic,
            evidence={"cyclic_stereo_atom_maps": sorted(cyclic)},
        )

    def _stereo_execution(self, execution: FullExecutionResult) -> CheckResultV1:
        stereo = execution.stereo_result
        if stereo is None:
            return check(
                "stereo.execution",
                "stereo",
                CheckStatus.INDETERMINATE,
                "Stereo stage did not run because an earlier stage failed.",
            )
        return check(
            "stereo.execution",
            "stereo",
            CheckStatus.PASS if stereo.success else CheckStatus.FAIL,
            "Stereo edits executed and the final graph sanitized."
            if stereo.success
            else "Stereo execution failed transactionally.",
            severity=Severity.BLOCKING if not stereo.success else Severity.INFO,
            affected_atom_maps=stereo.error.affected_atom_maps if stereo.error else (),
            evidence={
                "applied_operations": list(stereo.applied_operations),
                "error_type": stereo.error.error_type if stereo.error else None,
                "rdkit_error": stereo.error.rdkit_error if stereo.error else None,
            },
        )
