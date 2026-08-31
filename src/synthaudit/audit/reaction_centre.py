"""Reaction-centre consistency audit."""

from __future__ import annotations

from typing import Any, cast

from rdkit import Chem

from synthaudit.adapters.mapped_reaction_smiles import (
    MappedReactionSmilesAdapter,
    MappedReactionSmilesInput,
)
from synthaudit.audit.common import check, mapped_molecule, stage_result
from synthaudit.graph.atom_maps import affected_atom_maps, atom_map_index
from synthaudit.graph.executor import ReactionExecutor
from synthaudit.schema.edits import AddBondEdit, BreakBondEdit, ChangeBondOrderEdit
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


def _core_signature(reaction: ReactionIRV1) -> tuple[tuple[Any, ...], ...]:
    values: list[tuple[Any, ...]] = []
    for edit in reaction.core_edits:
        endpoints = _pair(edit.map_a, edit.map_b)
        if isinstance(edit, BreakBondEdit):
            values.append(("break_bond", *endpoints, edit.expected_order))
        elif isinstance(edit, AddBondEdit):
            values.append(("add_bond", *endpoints, edit.order))
        elif isinstance(edit, ChangeBondOrderEdit):
            values.append(("change_bond_order", *endpoints, edit.from_order, edit.to_order))
    return tuple(sorted(values))


class ReactionCentreAudit:
    """Audit only product-to-synthon edits and their declared reaction centre."""

    def run(
        self,
        reaction: ReactionIRV1,
        execution: FullExecutionResult | None = None,
    ) -> StageAuditResultV1:
        result = execution or ReactionExecutor().execute(reaction)
        checks = [
            self._referenced_atoms(reaction),
            self._declared_bond_state(reaction),
            self._core_execution(result),
            self._explained_diff(reaction, result),
            self._ring_consistency(reaction, result),
            self._real_change(reaction, result),
            self._alternative_site_ambiguity(reaction),
            self._expected_precursor_reconstruction(reaction),
        ]
        return stage_result("reaction_centre", checks)

    def _referenced_atoms(self, reaction: ReactionIRV1) -> CheckResultV1:
        try:
            maps = set(atom_map_index(mapped_molecule(reaction.product.mapped_smiles)))
        except Exception as exc:
            return check(
                "reaction_centre.referenced_atoms",
                "reaction_centre",
                CheckStatus.FAIL,
                "Product atom maps cannot be inspected.",
                severity=Severity.BLOCKING,
                evidence={"error": str(exc)},
            )
        referenced = {
            atom_map for edit in reaction.core_edits for atom_map in affected_atom_maps(edit)
        }
        missing = referenced - maps
        return check(
            "reaction_centre.referenced_atoms",
            "reaction_centre",
            CheckStatus.FAIL if missing else CheckStatus.PASS,
            "Every core edit references a mapped product atom."
            if not missing
            else "Core edits reference atoms absent from the mapped product.",
            severity=Severity.BLOCKING if missing else Severity.INFO,
            affected_atom_maps=missing,
            evidence={"referenced_atom_maps": sorted(referenced)},
        )

    def _declared_bond_state(self, reaction: ReactionIRV1) -> CheckResultV1:
        errors: list[str] = []
        affected: set[int] = set()
        try:
            molecule = mapped_molecule(reaction.product.mapped_smiles)
            mapping = atom_map_index(molecule)
            working = Chem.RWMol(Chem.Mol(molecule))
            for index, edit in enumerate(reaction.core_edits):
                if edit.map_a not in mapping or edit.map_b not in mapping:
                    continue
                atom_a = mapping[edit.map_a]
                atom_b = mapping[edit.map_b]
                bond = cast(Chem.Bond | None, working.GetBondBetweenAtoms(atom_a, atom_b))
                if isinstance(edit, BreakBondEdit):
                    if bond is None:
                        errors.append(f"edit {index}: break bond is absent")
                    elif (
                        edit.expected_order is not None
                        and bond.GetBondTypeAsDouble() != edit.expected_order
                    ):
                        errors.append(f"edit {index}: break bond order does not match")
                    else:
                        working.RemoveBond(atom_a, atom_b)
                elif isinstance(edit, AddBondEdit):
                    if bond is not None:
                        errors.append(f"edit {index}: added bond already exists")
                    else:
                        working.AddBond(atom_a, atom_b, Chem.BondType.SINGLE)
                        added_bond = working.GetBondBetweenAtoms(atom_a, atom_b)
                        added_bond.SetBondType(
                            {
                                1.0: Chem.BondType.SINGLE,
                                1.5: Chem.BondType.AROMATIC,
                                2.0: Chem.BondType.DOUBLE,
                                3.0: Chem.BondType.TRIPLE,
                            }[edit.order]
                        )
                elif bond is None:
                    errors.append(f"edit {index}: changed bond is absent")
                elif bond.GetBondTypeAsDouble() != edit.from_order:
                    errors.append(f"edit {index}: changed bond order does not match")
                else:
                    bond.SetBondType(
                        {
                            1.0: Chem.BondType.SINGLE,
                            1.5: Chem.BondType.AROMATIC,
                            2.0: Chem.BondType.DOUBLE,
                            3.0: Chem.BondType.TRIPLE,
                        }[edit.to_order]
                    )
                if errors and errors[-1].startswith(f"edit {index}:"):
                    affected.update((edit.map_a, edit.map_b))
        except Exception as exc:
            errors.append(str(exc))
        return check(
            "reaction_centre.declared_bond_state",
            "reaction_centre",
            CheckStatus.FAIL if errors else CheckStatus.PASS,
            "Every core edit matches the graph state at its declared operation order."
            if not errors
            else "One or more core edits disagree with the declared graph state.",
            affected_atom_maps=affected,
            evidence={"errors": errors},
        )

    def _core_execution(self, execution: FullExecutionResult) -> CheckResultV1:
        core = execution.core_result
        recoverable = (
            not core.success
            and core.error is not None
            and core.error.error_type == "SanitationError"
            and bool(core.diagnostic_mapped_structures)
        )
        status = (
            CheckStatus.PASS
            if core.success
            else (CheckStatus.WARNING if recoverable else CheckStatus.FAIL)
        )
        return check(
            "reaction_centre.core_execution",
            "reaction_centre",
            status,
            "Core graph edits executed to a sanitized synthon graph."
            if core.success
            else (
                "Core edits produced a diagnostic synthon that required later completion."
                if recoverable
                else "Core graph execution failed transactionally."
            ),
            severity=Severity.BLOCKING if status == CheckStatus.FAIL else None,
            affected_atom_maps=core.error.affected_atom_maps if core.error else (),
            evidence={
                "applied_operations": list(core.applied_operations),
                "error_type": core.error.error_type if core.error else None,
                "rdkit_error": core.error.rdkit_error if core.error else None,
            },
        )

    def _explained_diff(
        self,
        reaction: ReactionIRV1,
        execution: FullExecutionResult,
    ) -> CheckResultV1:
        diff = execution.core_result.graph_diff
        if diff is None:
            return check(
                "reaction_centre.explained_graph_diff",
                "reaction_centre",
                CheckStatus.INDETERMINATE,
                "No core-stage graph diff is available.",
            )
        declared_removed = {
            _pair(edit.map_a, edit.map_b)
            for edit in reaction.core_edits
            if isinstance(edit, BreakBondEdit)
        }
        declared_added = {
            _pair(edit.map_a, edit.map_b)
            for edit in reaction.core_edits
            if isinstance(edit, AddBondEdit)
        }
        declared_orders = {
            _pair(edit.map_a, edit.map_b)
            for edit in reaction.core_edits
            if isinstance(edit, ChangeBondOrderEdit)
        }
        observed_removed = {_pair(item.map_a, item.map_b) for item in diff.removed_bonds}
        observed_added = {_pair(item.map_a, item.map_b) for item in diff.added_bonds}
        observed_orders = {_pair(item.map_a, item.map_b) for item in diff.changed_bond_orders}
        mismatches = {
            "removed": sorted(declared_removed ^ observed_removed),
            "added": sorted(declared_added ^ observed_added),
            "order_changed": sorted(declared_orders ^ observed_orders),
        }
        mismatch = any(mismatches.values())
        return check(
            "reaction_centre.explained_graph_diff",
            "reaction_centre",
            CheckStatus.FAIL if mismatch else CheckStatus.PASS,
            "Core graph diff is exactly explained by declared bond edits."
            if not mismatch
            else "Declared and observed core bond changes differ.",
            evidence={key: [list(pair) for pair in value] for key, value in mismatches.items()},
        )

    def _ring_consistency(
        self,
        reaction: ReactionIRV1,
        execution: FullExecutionResult,
    ) -> CheckResultV1:
        diff = execution.core_result.graph_diff
        if diff is None:
            return check(
                "reaction_centre.ring_change",
                "reaction_centre",
                CheckStatus.INDETERMINATE,
                "Ring change cannot be evaluated without a core graph diff.",
            )
        delta = diff.ring_count_after - diff.ring_count_before
        topology_edits = sum(
            isinstance(edit, (BreakBondEdit, AddBondEdit)) for edit in reaction.core_edits
        )
        consistent = delta == 0 or (topology_edits > 0 and abs(delta) <= topology_edits)
        return check(
            "reaction_centre.ring_change",
            "reaction_centre",
            CheckStatus.PASS if consistent else CheckStatus.FAIL,
            "Observed ring-count change is consistent with declared topology edits."
            if consistent
            else "Observed ring-count change is not explained by topology edits.",
            evidence={
                "ring_count_before": diff.ring_count_before,
                "ring_count_after": diff.ring_count_after,
                "topology_edit_count": topology_edits,
            },
        )

    def _real_change(
        self,
        reaction: ReactionIRV1,
        execution: FullExecutionResult,
    ) -> CheckResultV1:
        diff = execution.core_result.graph_diff
        observed_count = 0
        if diff is not None:
            observed_count = (
                len(diff.added_bonds) + len(diff.removed_bonds) + len(diff.changed_bond_orders)
            )
        real = not reaction.core_edits or observed_count > 0
        status = (
            CheckStatus.PASS
            if real
            else (CheckStatus.INDETERMINATE if diff is None else CheckStatus.FAIL)
        )
        return check(
            "reaction_centre.real_graph_change",
            "reaction_centre",
            status,
            "Declared core edits produce observable bond changes."
            if real and reaction.core_edits
            else (
                "No core edit was declared; no reaction-centre graph change is required."
                if not reaction.core_edits
                else "Declared core edits produced no observable bond change."
            ),
            evidence={
                "declared_edits": len(reaction.core_edits),
                "observed_changes": observed_count,
            },
        )

    def _alternative_site_ambiguity(self, reaction: ReactionIRV1) -> CheckResultV1:
        if not reaction.core_edits:
            return check(
                "reaction_centre.alternative_site_ambiguity",
                "reaction_centre",
                CheckStatus.PASS,
                "No reaction-centre atom selection was declared.",
            )
        try:
            molecule = mapped_molecule(reaction.product.mapped_smiles)
            mapping = atom_map_index(molecule)
            candidate = Chem.Mol(molecule)
            for atom in candidate.GetAtoms():
                atom.SetAtomMapNum(0)
                atom.SetChiralTag(Chem.ChiralType.CHI_UNSPECIFIED)
            ranks = tuple(
                Chem.CanonicalRankAtoms(candidate, breakTies=False, includeChirality=False)
            )
            rank_counts: dict[int, int] = {}
            for rank in ranks:
                rank_counts[rank] = rank_counts.get(rank, 0) + 1
            ambiguous = {
                atom_map
                for edit in reaction.core_edits
                for atom_map in (edit.map_a, edit.map_b)
                if atom_map in mapping and rank_counts[ranks[mapping[atom_map]]] > 1
            }
        except Exception as exc:
            return check(
                "reaction_centre.alternative_site_ambiguity",
                "reaction_centre",
                CheckStatus.INDETERMINATE,
                "Alternative-site symmetry could not be evaluated.",
                evidence={"error": str(exc)},
            )
        return check(
            "reaction_centre.alternative_site_ambiguity",
            "reaction_centre",
            CheckStatus.WARNING if ambiguous else CheckStatus.PASS,
            "Referenced reaction-centre atoms have unique graph environments."
            if not ambiguous
            else "Symmetry-equivalent product atoms create alternative-site ambiguity.",
            affected_atom_maps=ambiguous,
            evidence={"ambiguous_atom_maps": sorted(ambiguous)},
        )

    def _expected_precursor_reconstruction(self, reaction: ReactionIRV1) -> CheckResultV1:
        if not reaction.expected_precursors:
            return check(
                "reaction_centre.expected_precursor_reconstruction",
                "reaction_centre",
                CheckStatus.UNAVAILABLE,
                "No expected precursor set was supplied for reaction-centre reconstruction.",
            )
        reaction_smiles = (
            ".".join(item.mapped_smiles for item in reaction.expected_precursors)
            + ">>"
            + reaction.product.mapped_smiles
        )
        try:
            derived = MappedReactionSmilesAdapter().to_reaction_ir(
                MappedReactionSmilesInput(reaction_smiles=reaction_smiles)
            )
            expected = _core_signature(derived)
            declared = _core_signature(reaction)
            matches = expected == declared
        except Exception as exc:
            return check(
                "reaction_centre.expected_precursor_reconstruction",
                "reaction_centre",
                CheckStatus.INDETERMINATE,
                "Expected precursor graph differencing could not be completed.",
                evidence={"error": str(exc)},
            )
        return check(
            "reaction_centre.expected_precursor_reconstruction",
            "reaction_centre",
            CheckStatus.PASS if matches else CheckStatus.FAIL,
            "Declared reaction-centre edits match mapped expected-precursor graph differences."
            if matches
            else "Expected precursors imply a different reaction centre.",
            evidence={
                "declared_signature": [list(item) for item in declared],
                "expected_signature": [list(item) for item in expected],
            },
        )
