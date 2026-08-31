from __future__ import annotations

import pytest
from pydantic import ValidationError

from synthaudit.models import (
    CalibrationMethod,
    EstimatorFamily,
    EvidenceExampleSplit,
    EvidenceExampleV1,
    EvidenceFeatureV1,
    EvidenceModelRole,
    EvidenceStage,
    FeatureGroup,
    fit_evidence_model,
)
from synthaudit.providers import (
    CriticSampleV1,
    DisabledIndependentCriticProvider,
    ForwardProductCandidateV1,
    ForwardReactionEvidenceV1,
    ForwardReactionRequestV1,
    IndependentCriticEvidenceV1,
    IndependentCriticRequestV1,
    InMemoryEvidenceModelRegistry,
    UnavailableForwardReactionProvider,
)
from synthaudit.schema import (
    EvidenceAvailability,
    MoleculeRecord,
    MoleculeRole,
    ProvenanceRecord,
    ReactionIRV1,
)

PROVENANCE = (
    ProvenanceRecord(source="fixture-provider", source_version="1", license="fixture-only"),
)


def _reaction() -> ReactionIRV1:
    return ReactionIRV1(
        reaction_id="provider-fixture",
        product=MoleculeRecord(mapped_smiles="[CH4:1]", role=MoleculeRole.PRODUCT),
    )


def test_optional_providers_fail_closed_by_default() -> None:
    forward_request = ForwardReactionRequestV1(
        request_id="forward-1",
        mapped_precursors=("[CH4:1]",),
    )
    forward = UnavailableForwardReactionProvider().predict(forward_request)
    critic_request = IndependentCriticRequestV1(
        request_id="critic-1",
        reaction=_reaction(),
        prompt_id="fixture-prompt",
        prompt_version="1",
    )
    critic = DisabledIndependentCriticProvider().review(critic_request)
    assert forward.availability == EvidenceAvailability.UNAVAILABLE
    assert not forward.candidates
    assert critic.availability == EvidenceAvailability.UNAVAILABLE
    assert not critic.samples
    assert not critic.sole_plausibility_source_permitted


def test_available_forward_and_critic_outputs_require_raw_provenance_and_accounting() -> None:
    forward = ForwardReactionEvidenceV1(
        request_id="forward-1",
        provider_id="fixture-forward",
        availability=EvidenceAvailability.AVAILABLE,
        candidates=(
            ForwardProductCandidateV1(
                rank=1,
                product_smiles="C",
                provider_raw_score=0.9,
            ),
        ),
        target_rank=1,
        target_similarity=1.0,
        model_uncertainty=0.1,
        provenance=PROVENANCE,
    )
    assert not forward.candidates[0].raw_score_is_calibrated_probability

    samples = (
        CriticSampleV1(
            sample_index=0,
            judgement="supported",
            rationale="fixture rationale A",
            raw_response="raw A",
            input_tokens=10,
            output_tokens=5,
            reported_cost_usd=0.01,
        ),
        CriticSampleV1(
            sample_index=1,
            judgement="indeterminate",
            rationale="fixture rationale B",
            raw_response="raw B",
            input_tokens=10,
            output_tokens=6,
            reported_cost_usd=0.02,
        ),
    )
    critic = IndependentCriticEvidenceV1(
        request_id="critic-1",
        provider_id="fixture-critic",
        availability=EvidenceAvailability.AVAILABLE,
        samples=samples,
        total_input_tokens=20,
        total_output_tokens=11,
        total_reported_cost_usd=0.03,
        provenance=PROVENANCE,
        independent_from_generation_provider=True,
    )
    assert len(critic.samples) == 2
    with pytest.raises(ValidationError, match="cost total"):
        IndependentCriticEvidenceV1.model_validate(
            {**critic.model_dump(mode="json"), "total_reported_cost_usd": 1.0}
        )
    with pytest.raises(ValidationError, match="independent from the generation provider"):
        IndependentCriticEvidenceV1.model_validate(
            {
                **critic.model_dump(mode="json"),
                "independent_from_generation_provider": False,
            }
        )


def test_model_registry_resolves_only_explicit_local_models() -> None:
    def examples(split: EvidenceExampleSplit, prefix: str) -> tuple[EvidenceExampleV1, ...]:
        return tuple(
            EvidenceExampleV1(
                example_id=f"{prefix}-{index}",
                parent_group_id=f"{prefix}-parent-{index}",
                split=split,
                stage=EvidenceStage.REACTION_CENTRE,
                target_label=index % 2,
                target_source="authored registry contract fixture",
                features=(
                    EvidenceFeatureV1(
                        feature_id="structural.valid",
                        group=FeatureGroup.STRUCTURAL,
                        availability=EvidenceAvailability.AVAILABLE,
                        value=float(index % 2),
                        interpretation="Software fixture only.",
                        provenance=PROVENANCE,
                    ),
                ),
                provenance=PROVENANCE,
            )
            for index in range(4)
        )

    model = fit_evidence_model(
        examples(EvidenceExampleSplit.TRAIN, "registry-train"),
        (),
        stage=EvidenceStage.REACTION_CENTRE,
        role=EvidenceModelRole.REACTION_CENTRE_MODEL,
        estimator_family=EstimatorFamily.LOGISTIC_REGRESSION,
        calibration_method=CalibrationMethod.NONE,
        random_seed=9,
        feature_groups={FeatureGroup.STRUCTURAL},
    )
    registry = InMemoryEvidenceModelRegistry()
    registry.register(model)
    assert (
        registry.resolve(
            model.manifest.model_id,
            expected_stage=EvidenceStage.REACTION_CENTRE,
            expected_configuration_sha256=model.manifest.configuration_sha256,
        )
        is model
    )
    assert registry.manifests() == (model.manifest,)
    with pytest.raises(LookupError, match="no artifact was downloaded"):
        registry.resolve("missing-model")
