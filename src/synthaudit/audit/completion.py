"""Synthon-completion consistency audit."""

from __future__ import annotations

from contextlib import suppress
from typing import cast

from rdkit import Chem

from synthaudit.audit.common import (
    canonical_structure_set,
    check,
    map_numbers,
    mapped_molecule,
    stage_result,
)
from synthaudit.graph.atom_maps import atom_map_index
from synthaudit.graph.executor import ReactionExecutor
from synthaudit.schema.edits import AttachFragmentEdit, DetachFragmentEdit
from synthaudit.schema.reaction_ir import ReactionIRV1
from synthaudit.schema.results import (
    CheckResultV1,
    CheckStatus,
    FullExecutionResult,
    Severity,
    StageAuditResultV1,
)


def _fragment_maps(fragment_smiles: str) -> set[int]:
    molecule = cast(Chem.Mol | None, Chem.MolFromSmiles(fragment_smiles, sanitize=False))
    if molecule is None:
        raise ValueError(f"cannot parse fragment: {fragment_smiles!r}")
    return set(atom_map_index(molecule))


class SynthonCompletionAudit:
    """Audit only synthon-to-precursor state and attachment completion."""

    def run(
        self,
        reaction: ReactionIRV1,
        execution: FullExecutionResult | None = None,
    ) -> StageAuditResultV1:
        result = execution or ReactionExecutor().execute(reaction)
        checks = [
            self._attachment_points(reaction, result),
            self._fragment_parsing(reaction),
            self._attachment_identity(reaction),
            self._completion_execution(result),
            self._charge_and_valence(result),
            self._expected_reconstruction(reaction, result),
            self._external_fragments_explained(reaction, result),
            self._required_fragments_present(reaction, result),
            self._unexplained_atoms(reaction, result),
            self._leaving_group_review(reaction),
        ]
        return stage_result("completion", checks)

    @staticmethod
    def _synthon_structures(execution: FullExecutionResult) -> tuple[str, ...]:
        core = execution.core_result
        if core.success:
            return core.mapped_structures
        return core.diagnostic_mapped_structures

    def _attachment_points(
        self,
        reaction: ReactionIRV1,
        execution: FullExecutionResult,
    ) -> CheckResultV1:
        synthons = self._synthon_structures(execution)
        if not synthons:
            return check(
                "completion.attachment_points",
                "completion",
                CheckStatus.INDETERMINATE,
                "Attachment points cannot be checked because no synthon graph is available.",
            )
        try:
            available = map_numbers(synthons)
        except Exception as exc:
            return check(
                "completion.attachment_points",
                "completion",
                CheckStatus.INDETERMINATE,
                "Synthon atom maps cannot be inspected.",
                evidence={"error": str(exc)},
            )
        missing: set[int] = set()
        for edit in reaction.attachment_edits:
            if isinstance(edit, AttachFragmentEdit):
                if edit.attachment_kind == "fragment":
                    missing.update(
                        item.product_atom_map
                        for item in edit.connections
                        if item.product_atom_map not in available
                    )
                    if edit.fragment_smiles:
                        with suppress(Exception):
                            available.update(_fragment_maps(edit.fragment_smiles))
                elif edit.target_atom_map is not None and edit.target_atom_map not in available:
                    missing.add(edit.target_atom_map)
            else:
                for map_a, map_b in edit.attachment_bonds:
                    if map_a not in available:
                        missing.add(map_a)
                    if map_b not in available:
                        missing.add(map_b)
                available.difference_update(edit.fragment_atom_maps)
        return check(
            "completion.attachment_points",
            "completion",
            CheckStatus.FAIL if missing else CheckStatus.PASS,
            "Every completion attachment point exists at its execution stage."
            if not missing
            else "Completion edits contain missing attachment points.",
            severity=Severity.BLOCKING if missing else Severity.INFO,
            affected_atom_maps=missing,
            evidence={"missing_attachment_maps": sorted(missing)},
        )

    def _fragment_parsing(self, reaction: ReactionIRV1) -> CheckResultV1:
        errors: list[str] = []
        fragment_count = 0
        for index, edit in enumerate(reaction.attachment_edits):
            if not isinstance(edit, AttachFragmentEdit) or edit.attachment_kind != "fragment":
                continue
            fragment_count += 1
            assert edit.fragment_smiles is not None
            try:
                molecule = mapped_molecule(edit.fragment_smiles)
                outcome = Chem.Mol(molecule)
                Chem.SanitizeMol(outcome)
            except Exception as exc:
                errors.append(f"attachment edit {index}: {exc}")
        return check(
            "completion.fragment_parsing",
            "completion",
            CheckStatus.FAIL if errors else CheckStatus.PASS,
            "Every declared external fragment parses and sanitizes."
            if not errors
            else "One or more external fragments failed parsing or sanitation.",
            severity=Severity.BLOCKING if errors else Severity.INFO,
            evidence={"fragment_count": fragment_count, "errors": errors},
        )

    def _attachment_identity(self, reaction: ReactionIRV1) -> CheckResultV1:
        errors: list[str] = []
        multi_attached: list[int] = []
        affected: set[int] = set()
        for index, edit in enumerate(reaction.attachment_edits):
            if not isinstance(edit, AttachFragmentEdit) or edit.attachment_kind != "fragment":
                continue
            assert edit.fragment_smiles is not None
            try:
                fragment_maps = _fragment_maps(edit.fragment_smiles)
            except Exception as exc:
                errors.append(f"attachment edit {index}: {exc}")
                continue
            pairs = [(item.product_atom_map, item.fragment_atom_map) for item in edit.connections]
            duplicate_pairs = {pair for pair in pairs if pairs.count(pair) > 1}
            if duplicate_pairs:
                errors.append(f"attachment edit {index}: duplicate connection pair")
                affected.update(atom_map for pair in duplicate_pairs for atom_map in pair)
            for connection in edit.connections:
                if connection.fragment_atom_map not in fragment_maps:
                    errors.append(
                        f"attachment edit {index}: fragment map "
                        f"{connection.fragment_atom_map} is absent"
                    )
                    affected.add(connection.fragment_atom_map)
            counts: dict[int, int] = {}
            for connection in edit.connections:
                counts[connection.fragment_atom_map] = (
                    counts.get(connection.fragment_atom_map, 0) + 1
                )
            multi_attached.extend(atom_map for atom_map, count in counts.items() if count > 1)
        return check(
            "completion.attachment_identity",
            "completion",
            CheckStatus.FAIL if errors else CheckStatus.PASS,
            "Fragment attachment atoms are explicit and connection pairs are unique."
            if not errors
            else "Fragment attachment identity is invalid or duplicated.",
            affected_atom_maps=affected,
            evidence={
                "errors": errors,
                "explicit_multi_attached_fragment_maps": sorted(set(multi_attached)),
            },
        )

    def _completion_execution(self, execution: FullExecutionResult) -> CheckResultV1:
        completion = execution.completion_result
        if completion is None:
            return check(
                "completion.execution",
                "completion",
                CheckStatus.INDETERMINATE,
                "Completion did not run because an earlier blocking stage failed.",
                evidence={
                    "upstream_error": execution.core_result.error.message
                    if execution.core_result.error
                    else None
                },
            )
        return check(
            "completion.execution",
            "completion",
            CheckStatus.PASS if completion.success else CheckStatus.FAIL,
            "Completion edits executed transactionally."
            if completion.success
            else "Completion execution failed transactionally.",
            severity=Severity.BLOCKING if not completion.success else Severity.INFO,
            affected_atom_maps=completion.error.affected_atom_maps if completion.error else (),
            evidence={
                "applied_operations": list(completion.applied_operations),
                "error_type": completion.error.error_type if completion.error else None,
                "rdkit_error": completion.error.rdkit_error if completion.error else None,
            },
        )

    def _charge_and_valence(self, execution: FullExecutionResult) -> CheckResultV1:
        completion = execution.completion_result
        if completion is None:
            return check(
                "completion.charge_valence",
                "completion",
                CheckStatus.INDETERMINATE,
                "Post-completion charge and valence are unavailable.",
            )
        return check(
            "completion.charge_valence",
            "completion",
            CheckStatus.PASS if completion.structurally_valid else CheckStatus.FAIL,
            "Post-completion graph passed RDKit charge/valence sanitation."
            if completion.structurally_valid
            else "Post-completion graph failed charge/valence sanitation.",
            evidence={
                "structurally_valid": completion.structurally_valid,
                "rdkit_error": completion.error.rdkit_error if completion.error else None,
            },
        )

    def _expected_reconstruction(
        self,
        reaction: ReactionIRV1,
        execution: FullExecutionResult,
    ) -> CheckResultV1:
        if not reaction.expected_precursors:
            return check(
                "completion.expected_precursor_reconstruction",
                "completion",
                CheckStatus.UNAVAILABLE,
                "No expected precursor set was supplied for completion comparison.",
            )
        completion = execution.completion_result
        if completion is None or not completion.success:
            return check(
                "completion.expected_precursor_reconstruction",
                "completion",
                CheckStatus.INDETERMINATE,
                "Expected precursors cannot be compared because completion failed.",
            )
        expected = tuple(item.mapped_smiles for item in reaction.expected_precursors)
        try:
            reconstructed = canonical_structure_set(completion.mapped_structures, clear_stereo=True)
            expected_set = canonical_structure_set(expected, clear_stereo=True)
            matches = reconstructed == expected_set
        except Exception as exc:
            return check(
                "completion.expected_precursor_reconstruction",
                "completion",
                CheckStatus.INDETERMINATE,
                "Precursor comparison failed during canonicalization.",
                evidence={"error": str(exc)},
            )
        return check(
            "completion.expected_precursor_reconstruction",
            "completion",
            CheckStatus.PASS if matches else CheckStatus.FAIL,
            "Completion reconstructs the expected mapped precursor set before stereo."
            if matches
            else "Completion does not reconstruct the expected mapped precursor set.",
            evidence={
                "reconstructed": list(reconstructed),
                "expected": list(expected_set),
                "stereo_ignored_at_completion_stage": True,
            },
        )

    def _declared_fragment_maps(self, reaction: ReactionIRV1) -> set[int]:
        result: set[int] = set()
        for edit in reaction.attachment_edits:
            if isinstance(edit, AttachFragmentEdit) and edit.fragment_smiles:
                with suppress(Exception):
                    result.update(_fragment_maps(edit.fragment_smiles))
        return result

    def _external_fragments_explained(
        self,
        reaction: ReactionIRV1,
        execution: FullExecutionResult,
    ) -> CheckResultV1:
        completion = execution.completion_result
        if completion is None or completion.graph_diff is None:
            return check(
                "completion.external_fragments_explained",
                "completion",
                CheckStatus.INDETERMINATE,
                "No completion graph diff is available for fragment attribution.",
            )
        declared = self._declared_fragment_maps(reaction)
        observed = {item.atom_map for item in completion.graph_diff.added_atoms}
        unexplained = observed - declared
        return check(
            "completion.external_fragments_explained",
            "completion",
            CheckStatus.FAIL if unexplained else CheckStatus.PASS,
            "Every externally introduced atom belongs to an attachment edit."
            if not unexplained
            else "Completion introduced atoms without a corresponding fragment edit.",
            affected_atom_maps=unexplained,
            evidence={
                "declared_external_atom_maps": sorted(declared),
                "observed_added_atom_maps": sorted(observed),
            },
        )

    def _required_fragments_present(
        self,
        reaction: ReactionIRV1,
        execution: FullExecutionResult,
    ) -> CheckResultV1:
        completion = execution.completion_result
        if completion is None or not completion.success:
            return check(
                "completion.required_fragments_present",
                "completion",
                CheckStatus.INDETERMINATE,
                "Required-fragment retention cannot be checked after failed completion.",
            )
        declared = self._declared_fragment_maps(reaction)
        try:
            output = map_numbers(completion.mapped_structures)
        except Exception as exc:
            return check(
                "completion.required_fragments_present",
                "completion",
                CheckStatus.INDETERMINATE,
                "Completion atom maps cannot be inspected.",
                evidence={"error": str(exc)},
            )
        missing = declared - output
        return check(
            "completion.required_fragments_present",
            "completion",
            CheckStatus.FAIL if missing else CheckStatus.PASS,
            "Every required attachment-fragment atom remains in completed precursors."
            if not missing
            else "A required external fragment silently disappeared.",
            affected_atom_maps=missing,
            evidence={"missing_fragment_atom_maps": sorted(missing)},
        )

    def _unexplained_atoms(
        self,
        reaction: ReactionIRV1,
        execution: FullExecutionResult,
    ) -> CheckResultV1:
        completion = execution.completion_result
        synthons = self._synthon_structures(execution)
        if completion is None or not completion.success or not synthons:
            return check(
                "completion.unexplained_atoms",
                "completion",
                CheckStatus.INDETERMINATE,
                "Completion atom accounting is unavailable after a failed stage.",
            )
        try:
            before = map_numbers(synthons)
            after = map_numbers(completion.mapped_structures)
        except Exception as exc:
            return check(
                "completion.unexplained_atoms",
                "completion",
                CheckStatus.INDETERMINATE,
                "Completion atom accounting could not parse mapped structures.",
                evidence={"error": str(exc)},
            )
        declared_added = self._declared_fragment_maps(reaction)
        declared_removed = {
            atom_map
            for edit in reaction.attachment_edits
            if isinstance(edit, DetachFragmentEdit)
            for atom_map in edit.fragment_atom_maps
        }
        unexplained_added = after - before - declared_added
        unexplained_removed = before - after - declared_removed
        unexplained = unexplained_added | unexplained_removed
        return check(
            "completion.unexplained_atoms",
            "completion",
            CheckStatus.FAIL if unexplained else CheckStatus.PASS,
            "Completion atom accounting is fully explained by declared fragments."
            if not unexplained
            else "Completion contains unexplained atom additions or removals.",
            affected_atom_maps=unexplained,
            evidence={
                "unexplained_added": sorted(unexplained_added),
                "unexplained_removed": sorted(unexplained_removed),
            },
        )

    def _leaving_group_review(self, reaction: ReactionIRV1) -> CheckResultV1:
        review: list[dict[str, object]] = []
        fragment_count = 0
        common_atomic_numbers = {1, 5, 6, 7, 8, 9, 14, 15, 16, 17, 35, 53}
        for index, edit in enumerate(reaction.attachment_edits):
            if not isinstance(edit, AttachFragmentEdit) or not edit.fragment_smiles:
                continue
            fragment_count += 1
            molecule = cast(Chem.Mol | None, Chem.MolFromSmiles(edit.fragment_smiles))
            if molecule is None:
                continue
            unusual = sorted(
                {
                    atom.GetAtomicNum()
                    for atom in molecule.GetAtoms()
                    if atom.GetAtomicNum() not in common_atomic_numbers
                }
            )
            if unusual or molecule.GetNumHeavyAtoms() > 20:
                review.append(
                    {
                        "attachment_edit_index": index,
                        "heavy_atoms": molecule.GetNumHeavyAtoms(),
                        "unusual_atomic_numbers": unusual,
                    }
                )
        if review:
            return check(
                "completion.leaving_group_review",
                "completion",
                CheckStatus.WARNING,
                "One or more external fragments cross transparent structural review rules.",
                evidence={"review_items": review, "corpus_novelty_evaluated": False},
            )
        if fragment_count:
            return check(
                "completion.leaving_group_review",
                "completion",
                CheckStatus.UNAVAILABLE,
                "Fragments passed structural rules; corpus-based leaving-group novelty is unavailable.",
                evidence={"fragment_count": fragment_count, "corpus_novelty_evaluated": False},
            )
        return check(
            "completion.leaving_group_review",
            "completion",
            CheckStatus.PASS,
            "No external leaving-group fragment requires review.",
            evidence={"fragment_count": 0, "corpus_novelty_evaluated": False},
        )
