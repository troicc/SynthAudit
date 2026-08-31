"""Core-backed view models for the five-page UI; no Streamlit dependency."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, JsonValue

from synthaudit import __version__
from synthaudit.adapters.mapped_reaction_smiles import (
    MappedReactionSmilesAdapter,
    MappedReactionSmilesInput,
)
from synthaudit.audit import ReactionAuditor, RouteAuditor
from synthaudit.counterfactuals import validate_benchmark_artifacts
from synthaudit.evaluation import (
    ReactSeqConformanceSummary,
    RoutePromptContractSmokeV1,
    run_reactseq_conformance,
    run_route_prompt_contract_smoke,
)
from synthaudit.novelty.engine import MultiViewNoveltyEngine
from synthaudit.precedent.index import ReferenceIndex
from synthaudit.precedent.retrieval import PrecedentRetriever
from synthaudit.prompting import validate_prompt_benchmark_artifacts
from synthaudit.reports.models import ReactionReportV1, RouteReportV1
from synthaudit.reports.standalone import report_provenance
from synthaudit.schema.common import MoleculeRole, ProvenanceRecord, StrictModel
from synthaudit.schema.reaction_ir import ReactionIRV1
from synthaudit.schema.route_audit import RouteStepEvidenceV1
from synthaudit.schema.route_ir import RouteIRV1, RouteStepIRV1

DEMO_REACTION_SMILES = "[CH3:1][CH2:2][Br:3].[OH-:4]>>[CH3:1][CH2:2][OH:4]"


class BenchmarkWorkspaceV1(StrictModel):
    """Only observed fixture validation and conformance facts for the dashboard."""

    schema_version: Literal["synthaudit.benchmark-workspace/1"] = "synthaudit.benchmark-workspace/1"
    counterfactual_record_count: int = Field(ge=0)
    counterfactual_metrics_status: Literal["not_run"]
    prompt_case_count: int = Field(ge=0)
    prompt_variant_count: int = Field(ge=0)
    prompt_metrics_status: Literal["not_run"]
    reactseq: ReactSeqConformanceSummary
    route_prompt: RoutePromptContractSmokeV1
    research_calibration_results_available: Literal[False] = False
    high_novelty_false_rejection_available: Literal[False] = False
    interpretation: Literal[
        "Fixture counts and conformance observations are software checks, not population performance or experimental validation."
    ] = (
        "Fixture counts and conformance observations are software checks, not population "
        "performance or experimental validation."
    )
    provenance: tuple[ProvenanceRecord, ...] = Field(min_length=1)


def demo_reaction() -> ReactionIRV1:
    reaction = MappedReactionSmilesAdapter().to_reaction_ir(
        MappedReactionSmilesInput(
            reaction_smiles=DEMO_REACTION_SMILES,
            reaction_id="synthaudit-demo-substitution",
        )
    )
    return reaction


def demo_route() -> RouteIRV1:
    first = MappedReactionSmilesAdapter().to_reaction_ir(
        MappedReactionSmilesInput(
            reaction_smiles="[CH3:1][CH3:2]>>[CH3:1][CH2:2][Br:4]",
            reaction_id="synthaudit-demo-route-step-1",
        )
    )
    second = MappedReactionSmilesAdapter().to_reaction_ir(
        MappedReactionSmilesInput(
            reaction_smiles=("[CH3:1][CH2:2][Br:4].[OH-:3]>>[CH3:1][CH2:2][OH:3]"),
            reaction_id="synthaudit-demo-route-step-2",
        )
    )
    provenance = (
        ProvenanceRecord(
            source="synthaudit-authored-demo",
            source_version="1",
            adapter="demo_route",
            adapter_version=__version__,
            license="Apache-2.0 fixture; not experimental reaction evidence",
        ),
    )
    return RouteIRV1(
        route_id="synthaudit-demo-route",
        target=second.product.model_copy(update={"identifiers": {"route_node_id": "target"}}),
        starting_materials=(
            first.expected_precursors[0].model_copy(
                update={
                    "role": MoleculeRole.STARTING_MATERIAL,
                    "identifiers": {"route_node_id": "start-carbon"},
                }
            ),
            second.expected_precursors[1].model_copy(
                update={
                    "role": MoleculeRole.STARTING_MATERIAL,
                    "identifiers": {"route_node_id": "start-hydroxide"},
                }
            ),
        ),
        intermediates=(
            first.product.model_copy(
                update={
                    "role": MoleculeRole.INTERMEDIATE,
                    "identifiers": {"route_node_id": "bromo-intermediate"},
                }
            ),
        ),
        steps=(
            RouteStepIRV1(
                step_id="step-1",
                reaction=first,
                consumes=("start-carbon",),
                produces=("bromo-intermediate",),
                strategy_text="protection",
            ),
            RouteStepIRV1(
                step_id="step-2",
                reaction=second,
                depends_on=("step-1",),
                consumes=("bromo-intermediate", "start-hydroxide"),
                produces=("target",),
                strategy_text="deprotection",
                key_step=True,
            ),
        ),
        strategy_text="Authored two-step software demonstration; not a synthetic recommendation.",
        provenance=provenance,
    )


def edit_rows(reaction: ReactionIRV1) -> tuple[dict[str, JsonValue], ...]:
    rows: list[dict[str, JsonValue]] = []
    for stage, edits in (
        ("reaction_centre", reaction.core_edits),
        ("completion", reaction.attachment_edits),
        ("atom_state", reaction.atom_state_edits),
        ("stereo", reaction.stereo_edits),
    ):
        for index, edit in enumerate(edits):
            rows.append(
                {
                    "stage": stage,
                    "operation_index": index,
                    "operation": edit.edit_type,
                    "edit_id": edit.edit_id or "",
                    "payload": edit.model_dump(mode="json"),
                }
            )
    return tuple(rows)


def reaction_report_workspace(
    reaction: ReactionIRV1,
    *,
    reference_index: ReferenceIndex | None = None,
) -> ReactionReportV1:
    audit = ReactionAuditor().audit(reaction)
    novelty = MultiViewNoveltyEngine(reference_index).score(reaction) if reference_index else None
    precedents = PrecedentRetriever(reference_index).search(reaction) if reference_index else None
    corpus_versions = (
        (f"{reference_index.manifest.corpus_id}@{reference_index.manifest.corpus_version}",)
        if reference_index
        else ()
    )
    return ReactionReportV1(
        reaction=reaction,
        audit=audit,
        novelty=novelty,
        precedents=precedents,
        corpus_versions=corpus_versions,
        limitations=("No calibrated evidence model is bundled with the interactive demo.",),
        provenance=report_provenance("ui/reaction-workspace"),
    )


def route_report_workspace(
    route: RouteIRV1,
    *,
    step_evidence: tuple[RouteStepEvidenceV1, ...] = (),
) -> RouteReportV1:
    return RouteReportV1(
        route=route,
        audit=RouteAuditor().audit(route, step_evidence=step_evidence),
        step_evidence=step_evidence,
        limitations=(
            "Protection and condition checks use declared structured context, not exhaustive chemistry knowledge.",
        ),
        provenance=report_provenance("ui/route-workspace"),
    )


def build_benchmark_workspace(root: str | Path) -> BenchmarkWorkspaceV1:
    project = Path(root)
    counterfactual = validate_benchmark_artifacts(
        records_path=project / "benchmarks/counterfactual-v1/records.jsonl",
        manifest_path=project / "benchmarks/counterfactual-v1/manifest.json",
        splits_path=project / "benchmarks/counterfactual-v1/splits.json",
        human_review_path=project / "benchmarks/counterfactual-v1/human-review.csv",
    )
    prompt = validate_prompt_benchmark_artifacts(
        cases_path=project / "benchmarks/prompt-robustness-v1/cases.jsonl",
        manifest_path=project / "benchmarks/prompt-robustness-v1/manifest.json",
    )
    reactseq = run_reactseq_conformance(project / "tests/fixtures/reactseq/golden.json")
    route_prompt = run_route_prompt_contract_smoke()
    return BenchmarkWorkspaceV1(
        counterfactual_record_count=counterfactual.record_count,
        counterfactual_metrics_status=counterfactual.metrics_status,
        prompt_case_count=prompt.case_count,
        prompt_variant_count=prompt.variant_count,
        prompt_metrics_status=prompt.metrics_status,
        reactseq=reactseq,
        route_prompt=route_prompt,
        provenance=(
            ProvenanceRecord(
                source="synthaudit-committed-software-fixtures",
                source_version=__version__,
                adapter="build_benchmark_workspace",
                adapter_version="1",
                license="Apache-2.0 fixtures; not experimental evidence",
            ),
        ),
    )
