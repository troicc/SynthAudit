"""Full staged ReactionIR execution orchestrator."""

from __future__ import annotations

from synthaudit.graph._execution import executor_provenance
from synthaudit.graph.atom_maps import parse_mapped_molecule
from synthaudit.graph.completion_executor import AttachmentCompletionExecutor
from synthaudit.graph.core_executor import CoreGraphExecutor
from synthaudit.graph.diff import graph_diff
from synthaudit.graph.sanitize import SanitationMode
from synthaudit.graph.stereo_executor import StereoExecutor
from synthaudit.schema.reaction_ir import ReactionIRV1
from synthaudit.schema.results import FullExecutionResult


class ReactionExecutor:
    """Execute one ReactionIR transaction through all explicit stages."""

    def __init__(
        self,
        core: CoreGraphExecutor | None = None,
        completion: AttachmentCompletionExecutor | None = None,
        stereo: StereoExecutor | None = None,
    ) -> None:
        self.core = core or CoreGraphExecutor()
        self.completion = completion or AttachmentCompletionExecutor()
        self.stereo = stereo or StereoExecutor()

    def execute(
        self,
        reaction: ReactionIRV1,
        mode: SanitationMode | str = SanitationMode.STRICT,
    ) -> FullExecutionResult:
        sanitation_mode = SanitationMode(mode)
        product_input = (reaction.product.mapped_smiles,)
        core_result = self.core.execute(
            reaction.product.mapped_smiles, reaction.core_edits, sanitation_mode
        )
        if not core_result.success:
            return FullExecutionResult(
                success=False,
                structurally_valid=False,
                input_mapped_structures=product_input,
                mapped_structures=product_input,
                diagnostic_mapped_structures=core_result.diagnostic_mapped_structures,
                applied_operations=tuple(f"core/{item}" for item in core_result.applied_operations),
                graph_diff=core_result.graph_diff,
                warnings=core_result.warnings,
                error=core_result.error,
                provenance=executor_provenance("ReactionExecutor"),
                core_result=core_result,
            )

        completion_result = self.completion.execute(
            core_result.mapped_structures,
            reaction.attachment_edits,
            reaction.atom_state_edits,
            sanitation_mode,
        )
        if not completion_result.success:
            return FullExecutionResult(
                success=False,
                structurally_valid=False,
                input_mapped_structures=product_input,
                mapped_structures=product_input,
                diagnostic_mapped_structures=completion_result.diagnostic_mapped_structures,
                applied_operations=(
                    *(f"core/{item}" for item in core_result.applied_operations),
                    *(f"completion/{item}" for item in completion_result.applied_operations),
                ),
                graph_diff=self._full_diff(
                    reaction.product.mapped_smiles,
                    completion_result.diagnostic_mapped_structures,
                ),
                warnings=(*core_result.warnings, *completion_result.warnings),
                error=completion_result.error,
                provenance=executor_provenance("ReactionExecutor"),
                core_result=core_result,
                completion_result=completion_result,
            )

        stereo_result = self.stereo.execute(
            completion_result.mapped_structures, reaction.stereo_edits, sanitation_mode
        )
        final_structures = (
            stereo_result.mapped_structures if stereo_result.success else product_input
        )
        diagnostic = () if stereo_result.success else stereo_result.diagnostic_mapped_structures
        return FullExecutionResult(
            success=stereo_result.success,
            structurally_valid=stereo_result.structurally_valid,
            input_mapped_structures=product_input,
            mapped_structures=final_structures,
            diagnostic_mapped_structures=diagnostic,
            applied_operations=(
                *(f"core/{item}" for item in core_result.applied_operations),
                *(f"completion/{item}" for item in completion_result.applied_operations),
                *(f"stereo/{item}" for item in stereo_result.applied_operations),
            ),
            graph_diff=self._full_diff(
                reaction.product.mapped_smiles,
                stereo_result.mapped_structures
                if stereo_result.success
                else stereo_result.diagnostic_mapped_structures,
            ),
            warnings=(
                *core_result.warnings,
                *completion_result.warnings,
                *stereo_result.warnings,
            ),
            error=stereo_result.error,
            provenance=executor_provenance("ReactionExecutor"),
            core_result=core_result,
            completion_result=completion_result,
            stereo_result=stereo_result,
        )

    @staticmethod
    def _full_diff(product: str, outputs: tuple[str, ...]):  # type: ignore[no-untyped-def]
        if not outputs:
            return None
        try:
            before = parse_mapped_molecule(product)
            after = parse_mapped_molecule(".".join(outputs))
            return graph_diff(before, after)
        except Exception:
            return None
