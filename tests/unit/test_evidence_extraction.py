from __future__ import annotations

from synthaudit.adapters.mapped_reaction_smiles import (
    MappedReactionSmilesAdapter,
    MappedReactionSmilesInput,
)
from synthaudit.audit import ReactionAuditor
from synthaudit.models import FeatureGroup, extract_reaction_evidence_features
from synthaudit.novelty import MultiViewNoveltyEngine
from synthaudit.precedent import ReferenceIndex, ReferenceReactionV1
from synthaudit.providers import ForwardReactionRequestV1, UnavailableForwardReactionProvider
from synthaudit.schema import EvidenceAvailability


def test_audit_novelty_and_provider_evidence_remain_separate_feature_groups() -> None:
    reaction = MappedReactionSmilesAdapter().to_reaction_ir(
        MappedReactionSmilesInput(
            reaction_smiles="[CH3:1][CH2:2][Br:3].[OH-:4]>>[CH3:1][CH2:2][OH:4]"
        )
    )
    index = ReferenceIndex.build(
        (
            ReferenceReactionV1(
                source_dataset="fixture",
                source_reaction_id="reference",
                data_license_status="fixture-only",
                reaction=reaction,
            ),
        ),
        corpus_id="fixture",
        corpus_version="1",
    )
    audit = ReactionAuditor().audit(reaction)
    novelty = MultiViewNoveltyEngine(index).score(reaction)
    forward = UnavailableForwardReactionProvider().predict(
        ForwardReactionRequestV1(
            request_id="fixture-forward",
            mapped_precursors=("[CH4:1]",),
        )
    )
    features = extract_reaction_evidence_features(
        audit,
        novelty=novelty,
        forward=forward,
        provider_scores={"audit": 0.8, "precedent": 0.7},
    )
    by_id = {feature.feature_id: feature for feature in features}
    assert len(by_id) == len(features)
    assert by_id["corpus.product_nearest_similarity"].group == FeatureGroup.CORPUS_FAMILIARITY
    assert by_id["corpus.product_nearest_similarity"].value == 1.0
    assert by_id["structural.structurally_valid"].group == FeatureGroup.STRUCTURAL
    assert by_id["precedent.transformation_maximum_similarity"].group == FeatureGroup.PRECEDENT
    assert by_id["forward.target_similarity"].availability == EvidenceAvailability.UNAVAILABLE
    assert by_id["route.context_supported"].group == FeatureGroup.ROUTE
    assert by_id["route.context_supported"].availability == EvidenceAvailability.UNAVAILABLE
    assert by_id["providers.score_range"].value is not None
