"""Orchestrate independent stage-specific audits for one reaction."""

from __future__ import annotations

from synthaudit.audit.common import audit_provenance
from synthaudit.audit.completion import SynthonCompletionAudit
from synthaudit.audit.reaction_centre import ReactionCentreAudit
from synthaudit.audit.stereo import StereoAudit
from synthaudit.audit.structural import StructuralAudit
from synthaudit.graph.executor import ReactionExecutor
from synthaudit.schema.reaction_ir import ReactionIRV1
from synthaudit.schema.results import CheckStatus, ReactionAuditResultV1, Severity


class ReactionAuditor:
    """Execute once, then retain four independent audit result groups."""

    def __init__(
        self,
        *,
        executor: ReactionExecutor | None = None,
        structural: StructuralAudit | None = None,
        reaction_centre: ReactionCentreAudit | None = None,
        completion: SynthonCompletionAudit | None = None,
        stereo: StereoAudit | None = None,
    ) -> None:
        self.executor = executor or ReactionExecutor()
        self.structural = structural or StructuralAudit()
        self.reaction_centre = reaction_centre or ReactionCentreAudit()
        self.completion = completion or SynthonCompletionAudit()
        self.stereo = stereo or StereoAudit()

    def audit(self, reaction: ReactionIRV1) -> ReactionAuditResultV1:
        execution = self.executor.execute(reaction)
        structural = self.structural.run(reaction, execution)
        reaction_centre = self.reaction_centre.run(reaction, execution)
        completion = self.completion.run(reaction, execution)
        stereo = self.stereo.run(reaction, execution)
        all_checks = (
            *structural.checks,
            *reaction_centre.checks,
            *completion.checks,
            *stereo.checks,
        )
        blocking = any(
            item.status == CheckStatus.FAIL and item.severity == Severity.BLOCKING
            for item in all_checks
        )
        structurally_valid = execution.structurally_valid and not any(
            item.status == CheckStatus.FAIL for item in structural.checks
        )
        return ReactionAuditResultV1(
            reaction_id=reaction.reaction_id,
            structural_audit=structural,
            reaction_centre_audit=reaction_centre,
            completion_audit=completion,
            stereo_audit=stereo,
            execution=execution,
            blocking=blocking,
            structurally_valid=structurally_valid,
            provenance=audit_provenance("ReactionAuditor"),
        )
