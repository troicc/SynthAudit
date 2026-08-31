"""Dependency, continuity, condition, and evidence audit for complete routes."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Sequence
from typing import Any, Literal, cast

from rdkit import Chem, rdBase

from synthaudit.audit.common import audit_provenance, check
from synthaudit.audit.reaction import ReactionAuditor
from synthaudit.graph.semantic_hash import reaction_ir_semantic_hash
from synthaudit.schema.common import MoleculeRecord
from synthaudit.schema.results import CheckResultV1, CheckStatus, Severity
from synthaudit.schema.route_audit import (
    RouteAuditResultV1,
    RouteReviewItemV1,
    RouteStepAuditV1,
    RouteStepEvidenceV1,
)
from synthaudit.schema.route_ir import RouteIRV1, RouteStepIRV1


def _canonical_unmapped(value: str) -> str | None:
    with rdBase.BlockLogs():
        molecule = cast(Chem.Mol | None, Chem.MolFromSmiles(value))
    if molecule is None:
        return None
    for atom in molecule.GetAtoms():
        atom.SetAtomMapNum(0)
    return Chem.MolToSmiles(molecule, canonical=True, isomericSmiles=True)


def _token_keys(value: str) -> set[str]:
    result = {f"literal:{value}"}
    canonical = _canonical_unmapped(value)
    if canonical is not None:
        result.add(f"molecule:{canonical}")
    return result


def _record_keys(record: MoleculeRecord) -> set[str]:
    result = _token_keys(record.mapped_smiles)
    result.update(f"literal:{value}" for value in record.identifiers.values() if value)
    if record.name:
        result.add(f"literal:{record.name}")
    return result


def _map_signature(value: str) -> tuple[tuple[int, int], ...] | None:
    with rdBase.BlockLogs():
        molecule = cast(Chem.Mol | None, Chem.MolFromSmiles(value))
    if molecule is None:
        return None
    signature = tuple(
        sorted((atom.GetAtomMapNum(), atom.GetAtomicNum()) for atom in molecule.GetAtoms())
    )
    if not signature or any(atom_map <= 0 for atom_map, _ in signature):
        return None
    return signature


def _has_dependency_cycle(steps: Sequence[RouteStepIRV1]) -> bool:
    dependencies = {step.step_id: set(step.depends_on) for step in steps}
    remaining = set(dependencies)
    while remaining:
        ready = {step_id for step_id in remaining if not (dependencies[step_id] & remaining)}
        if not ready:
            return True
        remaining -= ready
    return False


def _status(checks: Sequence[CheckResultV1]) -> CheckStatus:
    if any(item.status == CheckStatus.FAIL for item in checks):
        return CheckStatus.FAIL
    if any(item.status == CheckStatus.INDETERMINATE for item in checks):
        return CheckStatus.INDETERMINATE
    if any(item.status in {CheckStatus.WARNING, CheckStatus.UNSUPPORTED} for item in checks):
        return CheckStatus.WARNING
    if checks and all(item.status == CheckStatus.UNAVAILABLE for item in checks):
        return CheckStatus.UNAVAILABLE
    return CheckStatus.PASS


def _metadata_strings(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (list, tuple)) and all(isinstance(item, str) for item in value):
        return tuple(value)
    return ()


def _condition_tags(step: RouteStepIRV1) -> set[str]:
    tags = {
        item.lower()
        for item in _metadata_strings(step.metadata.get("condition_tags"))
        if item.strip()
    }
    conditions = step.reaction.conditions
    if conditions is None:
        return tags
    values = (
        *conditions.solvents,
        *conditions.catalysts,
        *conditions.reagents,
        conditions.atmosphere or "",
        conditions.source_text or "",
    )
    for value in values:
        lowered = value.lower().strip()
        if lowered:
            tags.add(lowered)
            tags.update(lowered.replace("/", " ").replace(",", " ").split())
    return tags


def _protection_events(step: RouteStepIRV1) -> tuple[str | None, tuple[str, ...]]:
    strategy = (step.strategy_text or "").lower()
    if "deprotection" in strategy or "deprotect" in strategy:
        event = "deprotect"
    elif "protection" in strategy or "protect" in strategy:
        event = "protect"
    else:
        event = None
    groups = _metadata_strings(step.metadata.get("protection_groups"))
    return event, groups or (("__unspecified__",) if event is not None else ())


def _continuity_checks(
    route: RouteIRV1,
) -> tuple[tuple[CheckResultV1, ...], tuple[str, ...]]:
    checks: list[CheckResultV1] = []
    ordered_ids: set[str] = set()
    ordering_violations: list[str] = []
    for step in route.steps:
        missing = sorted(set(step.depends_on) - ordered_ids)
        if missing:
            ordering_violations.append(f"{step.step_id} before {','.join(missing)}")
        ordered_ids.add(step.step_id)
    checks.append(
        check(
            "route.ordering",
            "route",
            CheckStatus.FAIL if ordering_violations else CheckStatus.PASS,
            (
                "Declared step order violates dependency order."
                if ordering_violations
                else "Every dependency precedes its dependent step."
            ),
            severity=Severity.BLOCKING if ordering_violations else Severity.INFO,
            evidence={"violations": ordering_violations},
        )
    )

    inventory: set[str] = set()
    for record in route.starting_materials:
        inventory.update(_record_keys(record))
    missing_consumes: list[str] = []
    declared_material_count = 0
    produced_by_step: dict[str, set[str]] = {}
    consumed_by_step: dict[str, set[str]] = {}
    for step in route.steps:
        consumed_keys: set[str] = set()
        for value in step.consumes:
            declared_material_count += 1
            keys = _token_keys(value)
            consumed_keys.update(keys)
            if inventory.isdisjoint(keys):
                missing_consumes.append(f"{step.step_id}:{value}")
        consumed_by_step[step.step_id] = consumed_keys
        produced_keys: set[str] = set()
        for value in step.produces:
            declared_material_count += 1
            produced_keys.update(_token_keys(value))
        produced_by_step[step.step_id] = produced_keys
        inventory.update(produced_keys)

    dependency_graph_breaks: list[str] = []
    step_by_id = {step.step_id: step for step in route.steps}
    comparable_edges = 0
    for step in route.steps:
        precursor_graphs: set[str] = set()
        for record in step.reaction.expected_precursors:
            precursor_graph = _canonical_unmapped(record.mapped_smiles)
            if precursor_graph is not None:
                precursor_graphs.add(precursor_graph)
        for dependency_id in step.depends_on:
            dependency = step_by_id[dependency_id]
            product_graph = _canonical_unmapped(dependency.reaction.product.mapped_smiles)
            if product_graph is None or not precursor_graphs:
                continue
            comparable_edges += 1
            if product_graph not in precursor_graphs:
                dependency_graph_breaks.append(f"{dependency_id}->{step.step_id}")

    if missing_consumes or dependency_graph_breaks:
        continuity_status = CheckStatus.FAIL
        continuity_message = "Declared route material or mapped dependency continuity is broken."
    elif declared_material_count or comparable_edges:
        continuity_status = CheckStatus.PASS
        continuity_message = (
            "Declared route material and comparable dependency links are continuous."
        )
    else:
        continuity_status = CheckStatus.UNAVAILABLE
        continuity_message = (
            "No declared material flow or comparable mapped dependency was available."
        )
    checks.append(
        check(
            "route.precursor_intermediate_continuity",
            "route",
            continuity_status,
            continuity_message,
            severity=Severity.BLOCKING if continuity_status == CheckStatus.FAIL else None,
            evidence={
                "missing_consumes": missing_consumes,
                "broken_dependency_edges": dependency_graph_breaks,
                "comparable_dependency_edges": comparable_edges,
            },
        )
    )

    unexplained: list[str] = []
    produced_all = set().union(*produced_by_step.values()) if produced_by_step else set()
    consumed_all = set().union(*consumed_by_step.values()) if consumed_by_step else set()
    target_keys = _record_keys(route.target)
    for record in route.intermediates:
        keys = _record_keys(record)
        if produced_all.isdisjoint(keys) or consumed_all.isdisjoint(keys):
            unexplained.append(
                record.name or record.identifiers.get("route_node_id") or record.mapped_smiles
            )
    for step in route.steps:
        for produced in step.produces:
            keys = _token_keys(produced)
            if consumed_all.isdisjoint(keys) and target_keys.isdisjoint(keys):
                unexplained.append(f"{step.step_id}:{produced}")
    checks.append(
        check(
            "route.unexplained_intermediates",
            "route",
            CheckStatus.WARNING if unexplained else CheckStatus.PASS,
            (
                "Some declared intermediates are not both produced and consumed."
                if unexplained
                else "No unexplained declared intermediate was found."
            ),
            evidence={"unexplained": sorted(set(unexplained))},
        )
    )
    affected_steps = {value.split(":", 1)[0] for value in missing_consumes}
    for edge in dependency_graph_breaks:
        affected_steps.update(edge.split("->", 1))
    continuity_steps = tuple(sorted(affected_steps))
    return tuple(checks), continuity_steps


def _atom_map_check(route: RouteIRV1) -> CheckResultV1:
    occurrences: dict[str, list[tuple[str, tuple[tuple[int, int], ...]]]] = defaultdict(list)

    def add(label: str, value: str) -> None:
        canonical = _canonical_unmapped(value)
        signature = _map_signature(value)
        if canonical is not None and signature is not None:
            occurrences[canonical].append((label, signature))

    add("target", route.target.mapped_smiles)
    for index, record in enumerate(route.starting_materials):
        add(f"starting_material:{index}", record.mapped_smiles)
    for index, record in enumerate(route.intermediates):
        add(f"intermediate:{index}", record.mapped_smiles)
    for step in route.steps:
        add(f"{step.step_id}:product", step.reaction.product.mapped_smiles)
        for index, precursor in enumerate(step.reaction.expected_precursors):
            add(f"{step.step_id}:precursor:{index}", precursor.mapped_smiles)
    repeated = {key: values for key, values in occurrences.items() if len(values) > 1}
    conflicts = {
        key: [label for label, _ in values]
        for key, values in repeated.items()
        if len({signature for _, signature in values}) > 1
    }
    if conflicts:
        return check(
            "route.atom_map_continuity",
            "route",
            CheckStatus.FAIL,
            "The same intermediate graph uses conflicting atom-map identities across steps.",
            severity=Severity.BLOCKING,
            evidence={"conflicting_occurrences": conflicts},
        )
    if not repeated:
        return check(
            "route.atom_map_continuity",
            "route",
            CheckStatus.UNAVAILABLE,
            "No repeated mapped intermediate graph was available for an atom-map continuity check.",
        )
    return check(
        "route.atom_map_continuity",
        "route",
        CheckStatus.PASS,
        "Repeated intermediate graphs preserve their atom-map identities.",
        evidence={"repeated_graph_count": len(repeated)},
    )


def _target_check(route: RouteIRV1) -> CheckResultV1:
    target = _canonical_unmapped(route.target.mapped_smiles)
    if target is None or not route.steps:
        return check(
            "route.target_reachability",
            "route",
            CheckStatus.UNAVAILABLE,
            "A parsed target and at least one route step are required.",
        )
    target_steps = [
        step.step_id
        for step in route.steps
        if _canonical_unmapped(step.reaction.product.mapped_smiles) == target
        or any(_canonical_unmapped(value) == target for value in step.produces)
    ]
    depended_on = {dependency for step in route.steps for dependency in step.depends_on}
    terminal_target_steps = sorted(set(target_steps) - depended_on)
    status = CheckStatus.PASS if terminal_target_steps else CheckStatus.FAIL
    return check(
        "route.target_reachability",
        "route",
        status,
        (
            "The declared target is produced by a terminal route step."
            if terminal_target_steps
            else "No terminal route step produces the declared target graph."
        ),
        severity=Severity.BLOCKING if status == CheckStatus.FAIL else None,
        evidence={"target_steps": target_steps, "terminal_target_steps": terminal_target_steps},
    )


def _redundancy_check(route: RouteIRV1) -> CheckResultV1:
    by_hash: dict[str, list[str]] = defaultdict(list)
    by_material_flow: dict[tuple[tuple[str, ...], tuple[str, ...]], list[str]] = defaultdict(list)
    for step in route.steps:
        by_hash[reaction_ir_semantic_hash(step.reaction)].append(step.step_id)
        by_material_flow[(tuple(sorted(step.consumes)), tuple(sorted(step.produces)))].append(
            step.step_id
        )
    duplicate_groups = [values for values in by_hash.values() if len(values) > 1]
    duplicate_flows = [
        values for key, values in by_material_flow.items() if len(values) > 1 and any(key)
    ]
    duplicated = sorted(
        {step_id for values in (*duplicate_groups, *duplicate_flows) for step_id in values}
    )
    return check(
        "route.duplicate_or_redundant_steps",
        "route",
        CheckStatus.WARNING if duplicated else CheckStatus.PASS,
        (
            "Duplicate reaction semantics or material-flow declarations require review."
            if duplicated
            else "No duplicate reaction semantics or declared material flows were found."
        ),
        evidence={"step_ids": duplicated},
    )


def _protection_check(route: RouteIRV1) -> tuple[CheckResultV1, tuple[str, ...]]:
    active: set[str] = set()
    events_seen = 0
    conflicts: list[str] = []
    for step in route.steps:
        required = set(_metadata_strings(step.metadata.get("requires_protected_groups")))
        missing = sorted(required - active)
        if missing:
            conflicts.append(f"{step.step_id}:requires:{','.join(missing)}")
        event, groups = _protection_events(step)
        if event is None:
            continue
        events_seen += 1
        if event == "protect":
            active.update(groups)
        else:
            absent = sorted(set(groups) - active)
            if absent:
                conflicts.append(f"{step.step_id}:deprotects-before-protection:{','.join(absent)}")
            active.difference_update(groups)
    if conflicts:
        status = CheckStatus.FAIL
        message = "Protection/deprotection timing conflicts with declared route order."
    elif events_seen:
        status = CheckStatus.PASS
        message = "Protection/deprotection events are ordered consistently under declared rules."
    else:
        status = CheckStatus.UNAVAILABLE
        message = "No explicit or strategy-labelled protection events were available."
    return (
        check(
            "route.protection_deprotection_timing",
            "route",
            status,
            message,
            evidence={"event_count": events_seen, "conflicts": conflicts},
        ),
        tuple(sorted({value.split(":", 1)[0] for value in conflicts})),
    )


def _condition_lifetime_check(route: RouteIRV1) -> tuple[CheckResultV1, tuple[str, ...]]:
    conflicts: list[str] = []
    evaluated_constraints = 0
    produced_at: dict[str, int] = {}
    consumed_at: dict[str, int] = {}
    for index, step in enumerate(route.steps):
        for value in step.produces:
            produced_at[value] = index
        for value in step.consumes:
            consumed_at.setdefault(value, index)
        counterfactual = step.metadata.get("counterfactual_incompatible_condition")
        if isinstance(counterfactual, str) and counterfactual:
            evaluated_constraints += 1
            conflicts.append(f"{step.step_id}:{counterfactual}")
    for record in route.intermediates:
        node_id = record.identifiers.get("route_node_id") or record.name
        incompatible = {
            value.lower()
            for value in _metadata_strings(record.metadata.get("fragile_to_condition_tags"))
        }
        if not node_id or not incompatible:
            continue
        evaluated_constraints += 1
        start = produced_at.get(node_id)
        end = consumed_at.get(node_id)
        if start is None or end is None or end < start:
            conflicts.append(f"{node_id}:lifetime-not-resolved")
            continue
        for step in route.steps[start : end + 1]:
            matched = sorted(incompatible & _condition_tags(step))
            if matched:
                conflicts.append(f"{step.step_id}:{node_id}:{','.join(matched)}")
    if conflicts:
        status = CheckStatus.FAIL
        message = "Condition-sensitive intermediate lifetime has declared conflicts."
    elif evaluated_constraints:
        status = CheckStatus.PASS
        message = "No declared fragile-intermediate condition conflict was found."
    else:
        status = CheckStatus.UNAVAILABLE
        message = "No structured fragile-intermediate compatibility constraint was supplied."
    return (
        check(
            "route.condition_sensitive_intermediate_lifetime",
            "route",
            status,
            message,
            evidence={"evaluated_constraints": evaluated_constraints, "conflicts": conflicts},
        ),
        tuple(conflicts),
    )


class RouteAuditor:
    """Audit a route without collapsing independent step evidence into success probability."""

    def __init__(self, *, reaction_auditor: ReactionAuditor | None = None) -> None:
        self.reaction_auditor = reaction_auditor or ReactionAuditor()

    def audit(
        self,
        route: RouteIRV1,
        *,
        step_evidence: Sequence[RouteStepEvidenceV1] = (),
        high_novelty_threshold: float = 0.7,
        high_uncertainty_threshold: float | None = None,
        compute_exploratory_naive_independence_score: bool = False,
    ) -> RouteAuditResultV1:
        if not 0 <= high_novelty_threshold <= 1:
            raise ValueError("high-novelty threshold must be within [0, 1]")
        if high_uncertainty_threshold is not None and high_uncertainty_threshold < 0:
            raise ValueError("high-uncertainty threshold cannot be negative")
        step_ids = [step.step_id for step in route.steps]
        evidence_ids = [item.step_id for item in step_evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("route-step evidence IDs must be unique")
        unknown_evidence = sorted(set(evidence_ids) - set(step_ids))
        if unknown_evidence:
            raise ValueError(f"route-step evidence references unknown steps: {unknown_evidence}")
        evidence_by_step = {item.step_id: item for item in step_evidence}

        step_audits = tuple(
            RouteStepAuditV1(
                step_id=step.step_id,
                reaction_audit=self.reaction_auditor.audit(step.reaction),
            )
            for step in route.steps
        )
        audit_by_step = {item.step_id: item.reaction_audit for item in step_audits}
        structural_blocking = tuple(
            step_id for step_id, result in audit_by_step.items() if result.blocking
        )
        completion_failures = tuple(
            step_id
            for step_id, result in audit_by_step.items()
            if result.completion_audit.status == CheckStatus.FAIL
        )
        stereo_sensitive = tuple(
            step.step_id for step in route.steps if bool(step.reaction.stereo_edits)
        )

        checks: list[CheckResultV1] = [
            check(
                "route.unique_step_ids",
                "route",
                CheckStatus.PASS,
                "Route step identifiers are unique under RouteIR validation.",
                evidence={"step_count": len(step_ids)},
            ),
            check(
                "route.valid_dependency_references",
                "route",
                CheckStatus.PASS,
                "Every dependency references a declared route step under RouteIR validation.",
            ),
        ]
        cycle = _has_dependency_cycle(route.steps)
        checks.append(
            check(
                "route.acyclic_dependencies",
                "route",
                CheckStatus.FAIL if cycle else CheckStatus.PASS,
                (
                    "The dependency graph contains a cycle."
                    if cycle
                    else "The dependency graph is acyclic."
                ),
                severity=Severity.BLOCKING if cycle else Severity.INFO,
            )
        )
        checks.append(_target_check(route))
        continuity_checks, continuity_steps = _continuity_checks(route)
        checks.extend(continuity_checks)
        checks.append(_atom_map_check(route))
        checks.append(_redundancy_check(route))
        protection_check, protection_steps = _protection_check(route)
        checks.append(protection_check)
        condition_check, condition_conflicts = _condition_lifetime_check(route)
        checks.append(condition_check)

        checks.append(
            check(
                "route.structural_blocking_steps",
                "route",
                CheckStatus.FAIL if structural_blocking else CheckStatus.PASS,
                (
                    "One or more reaction steps contain blocking structural audit failures."
                    if structural_blocking
                    else "No reaction step contains a blocking structural audit failure."
                ),
                severity=Severity.BLOCKING if structural_blocking else Severity.INFO,
                evidence={"step_ids": list(structural_blocking)},
            )
        )
        checks.append(
            check(
                "route.unresolved_completion_failures",
                "route",
                CheckStatus.FAIL if completion_failures else CheckStatus.PASS,
                (
                    "One or more steps have unresolved completion failures."
                    if completion_failures
                    else "No step has an unresolved completion failure."
                ),
                evidence={"step_ids": list(completion_failures)},
            )
        )
        checks.append(
            check(
                "route.stereo_sensitive_steps",
                "route",
                CheckStatus.PASS,
                "Stereo-sensitive steps remain explicitly identified.",
                evidence={"step_ids": list(stereo_sensitive)},
            )
        )

        supports = {
            step_id: item.calibrated_evidence_support_score
            for step_id, item in evidence_by_step.items()
            if item.calibrated_evidence_support_score is not None
        }
        minimum_support = min(supports.values()) if supports else None
        missing_support = sorted(set(step_ids) - set(supports))
        checks.append(
            check(
                "route.minimum_step_support",
                "route",
                (
                    CheckStatus.UNAVAILABLE
                    if not supports
                    else CheckStatus.WARNING
                    if missing_support
                    else CheckStatus.PASS
                ),
                (
                    "No calibrated step-support evidence was supplied."
                    if not supports
                    else "Minimum support is reported over available steps; some are missing."
                    if missing_support
                    else "Calibrated support evidence is available for every step."
                ),
                evidence={
                    "available_step_count": len(supports),
                    "missing_step_ids": missing_support,
                },
                deterministic=False,
            )
        )

        uncertainties = {
            step_id: item.uncertainty
            for step_id, item in evidence_by_step.items()
            if item.uncertainty is not None
        }
        maximum_uncertainty = max(uncertainties.values()) if uncertainties else None
        maximum_uncertainty_steps = tuple(
            sorted(
                step_id
                for step_id, value in uncertainties.items()
                if maximum_uncertainty is not None and value == maximum_uncertainty
            )
        )
        checks.append(
            check(
                "route.maximum_uncertainty",
                "route",
                CheckStatus.PASS if uncertainties else CheckStatus.UNAVAILABLE,
                (
                    "Maximum uncertainty and contributing steps are reported separately."
                    if uncertainties
                    else "No step-level uncertainty evidence was supplied."
                ),
                evidence={
                    "available_step_count": len(uncertainties),
                    "maximum_step_ids": list(maximum_uncertainty_steps),
                },
                deterministic=False,
            )
        )

        high_novelty_key_steps = tuple(
            step.step_id
            for step in route.steps
            if step.key_step
            and (evidence := evidence_by_step.get(step.step_id)) is not None
            and evidence.product_novelty is not None
            and evidence.product_novelty >= high_novelty_threshold
        )
        novelty_available = any(item.product_novelty is not None for item in step_evidence)
        checks.append(
            check(
                "route.high_novelty_key_step_location",
                "route",
                CheckStatus.PASS if novelty_available else CheckStatus.UNAVAILABLE,
                (
                    "High-novelty key steps are listed without treating novelty as implausibility."
                    if novelty_available
                    else "No corpus-relative step novelty evidence was supplied."
                ),
                evidence={
                    "threshold": high_novelty_threshold,
                    "step_ids": list(high_novelty_key_steps),
                },
                deterministic=False,
            )
        )

        exploratory_score: float | None = None
        exploratory_interpretation: (
            Literal["Exploratory naive independence product; not a route success probability."]
            | None
        ) = None
        if compute_exploratory_naive_independence_score and len(supports) == len(route.steps):
            exploratory_score = math.prod(supports.values())
            exploratory_interpretation = (
                "Exploratory naive independence product; not a route success probability."
            )
            exploratory_status = CheckStatus.WARNING
            exploratory_message = (
                "An explicitly requested naive independence product was computed and must not "
                "be interpreted as route success probability."
            )
        elif compute_exploratory_naive_independence_score:
            exploratory_status = CheckStatus.UNAVAILABLE
            exploratory_message = (
                "The requested exploratory product requires support for every step."
            )
        else:
            exploratory_status = CheckStatus.UNAVAILABLE
            exploratory_message = "Exploratory independence aggregation was not requested."
        checks.append(
            check(
                "route.exploratory_naive_independence_score",
                "route",
                exploratory_status,
                exploratory_message,
                deterministic=False,
            )
        )

        review: list[RouteReviewItemV1] = []
        for step_id in structural_blocking:
            review.append(
                RouteReviewItemV1(
                    review_id=f"structural:{step_id}",
                    priority=1,
                    category="structural",
                    step_ids=(step_id,),
                    reason="Blocking reaction-level structural audit failure.",
                    deterministic=True,
                )
            )
        if continuity_steps:
            review.append(
                RouteReviewItemV1(
                    review_id="continuity:declared-flow",
                    priority=1,
                    category="continuity",
                    step_ids=continuity_steps,
                    reason="Declared dependency or material flow is discontinuous.",
                    deterministic=True,
                )
            )
        if condition_conflicts:
            named_conflict_steps = {
                value.split(":", 1)[0]
                for value in condition_conflicts
                if value.split(":", 1)[0] in set(step_ids)
            }
            conflict_steps = tuple(sorted(named_conflict_steps or set(step_ids)))
            review.append(
                RouteReviewItemV1(
                    review_id="condition:fragile-lifetime",
                    priority=1,
                    category="condition",
                    step_ids=conflict_steps,
                    reason="Declared fragile-intermediate condition conflict.",
                    deterministic=True,
                )
            )
        for step_id in completion_failures:
            review.append(
                RouteReviewItemV1(
                    review_id=f"completion:{step_id}",
                    priority=2,
                    category="completion",
                    step_ids=(step_id,),
                    reason="Unresolved completion-stage failure.",
                    deterministic=True,
                )
            )
        if (
            high_uncertainty_threshold is not None
            and maximum_uncertainty is not None
            and maximum_uncertainty >= high_uncertainty_threshold
        ):
            review.append(
                RouteReviewItemV1(
                    review_id="uncertainty:maximum",
                    priority=2,
                    category="uncertainty",
                    step_ids=maximum_uncertainty_steps,
                    reason="Maximum step uncertainty meets the declared review threshold.",
                    deterministic=False,
                )
            )
        for step_id in stereo_sensitive:
            review.append(
                RouteReviewItemV1(
                    review_id=f"stereo:{step_id}",
                    priority=3,
                    category="stereo",
                    step_ids=(step_id,),
                    reason="Step contains an explicit stereochemical operation.",
                    deterministic=True,
                )
            )
        for step_id in high_novelty_key_steps:
            review.append(
                RouteReviewItemV1(
                    review_id=f"novelty:{step_id}",
                    priority=3,
                    category="novelty",
                    step_ids=(step_id,),
                    reason="Key step lies in the declared high-novelty corpus-relative slice.",
                    deterministic=False,
                )
            )
        if protection_steps:
            review.append(
                RouteReviewItemV1(
                    review_id="continuity:protection-timing",
                    priority=2,
                    category="continuity",
                    step_ids=protection_steps,
                    reason="Protection/deprotection timing conflict.",
                    deterministic=True,
                )
            )
        review.sort(key=lambda item: (item.priority, item.review_id))
        blocking = bool(structural_blocking) or any(
            item.status == CheckStatus.FAIL and item.severity == Severity.BLOCKING
            for item in checks
        )
        return RouteAuditResultV1(
            route_id=route.route_id,
            status=_status(checks),
            checks=tuple(checks),
            step_audits=step_audits,
            minimum_step_support=minimum_support,
            maximum_uncertainty=maximum_uncertainty,
            maximum_uncertainty_steps=maximum_uncertainty_steps,
            structural_blocking_steps=structural_blocking,
            unresolved_completion_failures=completion_failures,
            stereo_sensitive_steps=stereo_sensitive,
            high_novelty_key_steps=high_novelty_key_steps,
            critical_condition_conflicts=condition_conflicts,
            expert_review_queue=tuple(review),
            exploratory_naive_independence_score=exploratory_score,
            exploratory_score_interpretation=exploratory_interpretation,
            blocking=blocking,
            provenance=audit_provenance("RouteAuditor"),
        )
