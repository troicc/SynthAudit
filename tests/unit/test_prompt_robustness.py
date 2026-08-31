from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from synthaudit.adapters.mapped_reaction_smiles import (
    MappedReactionSmilesAdapter,
    MappedReactionSmilesInput,
)
from synthaudit.prompting import (
    PromptCaseIneligible,
    PromptInstructionRelation,
    PromptModelOutputV1,
    PromptModelRequestV1,
    PromptRobustnessCaseGenerator,
    PromptVariantKind,
    UnavailablePromptModelProvider,
    build_prompt_benchmark_evaluation,
    build_prompt_dataset,
    evaluate_prompt_provider_case,
    load_prompt_dataset,
    validate_prompt_benchmark_artifacts,
    write_prompt_dataset,
)
from synthaudit.schema import MoleculeRecord, MoleculeRole, ProvenanceRecord, ReactionIRV1
from synthaudit.schema.evidence import EvidenceAvailability

PROVENANCE = (
    ProvenanceRecord(
        source="authored-prompt-provider-fixture",
        source_version="1",
        license="Apache-2.0 fixture; no experimental evidence",
    ),
)


def _reaction() -> ReactionIRV1:
    return MappedReactionSmilesAdapter().to_reaction_ir(
        MappedReactionSmilesInput(
            reaction_smiles=("[CH3:1][CH2:2][Br:3].[OH-:4]>>[CH3:1][CH2:2][OH:4]"),
            reaction_id="prompt-fixture-reaction",
        )
    )


def _case():
    return PromptRobustnessCaseGenerator().build_case(
        _reaction(),
        parent_group_id="prompt-fixture-parent",
        seed=41,
    )


def test_generator_creates_exactly_five_deterministic_traceable_variants() -> None:
    first = _case()
    second = _case()
    assert first == second
    assert {item.kind for item in first.variants} == set(PromptVariantKind)
    exact = next(item for item in first.variants if item.kind == PromptVariantKind.EXACT)
    partial = next(item for item in first.variants if item.kind == PromptVariantKind.PARTIAL)
    ambiguous = next(item for item in first.variants if item.kind == PromptVariantKind.AMBIGUOUS)
    incorrect = next(
        item
        for item in first.variants
        if item.kind == PromptVariantKind.INCORRECT_STRUCTURALLY_PLAUSIBLE
    )
    contradictory = next(
        item for item in first.variants if item.kind == PromptVariantKind.CONTRADICTORY
    )
    assert len(exact.instructions) == _reaction().edit_count
    assert partial.omitted_reference_instruction_ids
    assert ambiguous.instructions[0].atom_maps == ()
    assert incorrect.instructions[0].relation_to_reference == PromptInstructionRelation.INCORRECT
    assert incorrect.instructions[0].atom_maps == (1, 2)
    assert any(
        item.relation_to_reference == PromptInstructionRelation.CONTRADICTORY
        for item in contradictory.instructions
    )
    assert all(item.provider_neutral for item in first.variants)
    assert first.reference_semantics == "reference_representation_not_experimental_ground_truth"


def test_ineligible_reaction_fails_explicitly_instead_of_inventing_prompt_semantics() -> None:
    reaction = ReactionIRV1(
        reaction_id="no-edits",
        product=MoleculeRecord(mapped_smiles="[CH4:1]", role=MoleculeRole.PRODUCT),
    )
    with pytest.raises(PromptCaseIneligible, match="at least two"):
        PromptRobustnessCaseGenerator().build_case(
            reaction,
            parent_group_id="no-edits-parent",
            seed=1,
        )


def test_prompt_provider_is_optional_and_fails_closed() -> None:
    case = _case()
    request = PromptModelRequestV1(
        request_id="prompt-request-1",
        case_id=case.case_id,
        variant=case.variants[0],
        mapped_product_smiles=case.reference_reaction.product.mapped_smiles,
    )
    output = UnavailablePromptModelProvider().generate(request)
    assert output.availability == EvidenceAvailability.UNAVAILABLE
    assert output.candidate_reaction is None
    assert output.missing_reasons


def test_prompt_dataset_build_write_load_and_validation_round_trip(tmp_path: Path) -> None:
    dataset = build_prompt_dataset(
        (_case(),),
        dataset_id="authored-unit-prompt-dataset",
        dataset_version="1",
        purpose="software_verification_fixture",
        source_dataset_id="authored-unit-source",
        source_dataset_version="1",
        source_records_sha256="a" * 64,
        source_license_status="Apache-2.0 fixture; no experimental evidence",
    )
    cases_path = tmp_path / "cases.jsonl"
    manifest_path = tmp_path / "manifest.json"
    write_prompt_dataset(
        dataset,
        cases_path=cases_path,
        manifest_path=manifest_path,
    )
    assert (
        load_prompt_dataset(
            cases_path=cases_path,
            manifest_path=manifest_path,
        )
        == dataset
    )
    validation = validate_prompt_benchmark_artifacts(
        cases_path=cases_path,
        manifest_path=manifest_path,
    )
    assert validation.case_count == 1
    assert validation.variant_count == 5
    assert validation.metrics_status == "not_run"


def _outputs(provider_id: str, model_id: str, *, calibrated: bool):
    case = _case()
    confidence = {
        PromptVariantKind.EXACT: 0.9,
        PromptVariantKind.PARTIAL: 0.8,
        PromptVariantKind.AMBIGUOUS: 0.7,
        PromptVariantKind.INCORRECT_STRUCTURALLY_PLAUSIBLE: 0.6,
        PromptVariantKind.CONTRADICTORY: 0.2,
    }
    outputs = []
    for variant in case.variants:
        abstained = variant.kind == PromptVariantKind.CONTRADICTORY
        common = {
            "request_id": f"{provider_id}:{variant.variant_id}",
            "case_id": case.case_id,
            "variant_id": variant.variant_id,
            "provider_id": provider_id,
            "model_id": model_id,
            "availability": EvidenceAvailability.AVAILABLE,
            "candidate_reaction": None if abstained else case.reference_reaction,
            "abstained": abstained,
            "raw_response": f"authored fixture response for {variant.kind.value}",
            "provenance": PROVENANCE,
        }
        if calibrated:
            common.update(
                {
                    "calibrated_evidence_confidence": confidence[variant.kind],
                    "calibration_method": "authored-fixture-calibrator",
                }
            )
        else:
            common["raw_model_confidence"] = confidence[variant.kind]
        outputs.append(PromptModelOutputV1.model_validate(common))
    return tuple(outputs)


def test_prompt_metrics_cover_obedience_recovery_abstention_and_contradiction_drop() -> None:
    case = _case()
    result = evaluate_prompt_provider_case(
        case,
        _outputs("fixture-provider-a", "fixture-model-a", calibrated=False),
    )
    exact = next(
        item for item in result.evaluations if item.variant_kind == PromptVariantKind.EXACT
    )
    incorrect = next(
        item
        for item in result.evaluations
        if item.variant_kind == PromptVariantKind.INCORRECT_STRUCTURALLY_PLAUSIBLE
    )
    contradictory = next(
        item for item in result.evaluations if item.variant_kind == PromptVariantKind.CONTRADICTORY
    )
    assert exact.reaction_centre_accuracy == 1.0
    assert exact.precursor_exact_match
    assert exact.completion_accuracy == 1.0
    assert exact.stereo_accuracy == 1.0
    assert exact.structural_validity
    assert exact.prompt_obedience
    assert exact.confidence_semantics == "raw_uncalibrated_provider_score"
    assert incorrect.recovery_from_incorrect_prompt
    assert incorrect.prompt_obedience is False
    assert contradictory.abstained
    assert contradictory.confidence_drop_under_contradiction == pytest.approx(0.7)


def test_multiple_models_are_compared_independently_and_calibration_is_reference_based() -> None:
    case = _case()
    first = evaluate_prompt_provider_case(
        case,
        _outputs("fixture-provider-a", "fixture-model-a", calibrated=False),
    )
    second = evaluate_prompt_provider_case(
        case,
        _outputs("fixture-provider-b", "fixture-model-b", calibrated=True),
    )
    result = build_prompt_benchmark_evaluation(
        (first, second),
        evaluation_id="authored-prompt-evaluation",
        scope="software_verification_fixture",
    )
    assert result.provider_count == 2
    assert len(result.provider_calibration) == 2
    assert not result.single_provider_as_ground_truth_permitted
    assert result.metrics_status == "computed_software_fixture"
    assert any("not scientific results" in item for item in result.limitations)


def test_prompt_output_accounting_and_alignment_fail_closed() -> None:
    case = _case()
    with pytest.raises(ValidationError, match="raw response and provenance"):
        PromptModelOutputV1(
            request_id="bad",
            case_id=case.case_id,
            variant_id=case.variants[0].variant_id,
            provider_id="provider",
            model_id="model",
            availability=EvidenceAvailability.AVAILABLE,
            candidate_reaction=case.reference_reaction,
        )
    outputs = list(_outputs("fixture-provider", "fixture-model", calibrated=False))
    outputs[0] = outputs[0].model_copy(update={"variant_id": "unknown"})
    with pytest.raises(ValueError, match="do not match"):
        evaluate_prompt_provider_case(case, outputs)


@pytest.mark.parametrize(
    "script",
    [
        (
            "import synthaudit.calibration.metrics; "
            "from synthaudit.models import CalibrationMethod; "
            "import synthaudit.prompting"
        ),
        (
            "import synthaudit.prompting; "
            "from synthaudit.calibration import reliability_summary; "
            "from synthaudit.models import fit_evidence_model"
        ),
    ],
)
def test_prompt_calibration_and_model_packages_are_import_order_independent(script: str) -> None:
    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
