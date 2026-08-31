from __future__ import annotations

import pytest

from synthaudit.adapters.mapped_reaction_smiles import (
    MappedReactionSmilesAdapter,
    MappedReactionSmilesInput,
)
from synthaudit.novelty import (
    CallableReactionClassProvider,
    MappingReactSeqMEOProvider,
    MultiViewNoveltyEngine,
    UnavailableReactionClassProvider,
    UnavailableReactSeqMEOProvider,
)
from synthaudit.precedent import ReferenceIndex, ReferenceReactionV1
from synthaudit.schema import ProvenanceRecord, ReactionIRV1
from synthaudit.schema.evidence import EvidenceAvailability


def _reaction(reaction_smiles: str) -> ReactionIRV1:
    return MappedReactionSmilesAdapter().to_reaction_ir(
        MappedReactionSmilesInput(reaction_smiles=reaction_smiles)
    )


def _fixture() -> tuple[ReactionIRV1, ReferenceIndex]:
    substitution = _reaction("[CH3:1][CH2:2][Br:3].[OH-:4]>>[CH3:1][CH2:2][OH:4]")
    reduction = _reaction("[CH3:1][CH3:2]>>[CH2:1]=[CH2:2]")
    records = (
        ReferenceReactionV1(
            source_dataset="fixture",
            source_reaction_id="substitution",
            data_license_status="CC0-fixture",
            reaction=substitution,
            reaction_class="substitution",
            reactseq_meo_embedding=(1.0, 0.0),
            reactseq_meo_provenance=(
                ProvenanceRecord(
                    source="fixture-embedding",
                    source_version="1",
                    license="fixture-only",
                ),
            ),
        ),
        ReferenceReactionV1(
            source_dataset="fixture",
            source_reaction_id="reduction",
            data_license_status="CC0-fixture",
            reaction=reduction,
            reaction_class="reduction",
            reactseq_meo_embedding=(0.0, 1.0),
            reactseq_meo_provenance=(
                ProvenanceRecord(
                    source="fixture-embedding",
                    source_version="1",
                    license="fixture-only",
                ),
            ),
        ),
    )
    return substitution, ReferenceIndex.build(records, corpus_id="fixture", corpus_version="v1")


def test_multiview_novelty_keeps_views_and_missing_providers_separate() -> None:
    query, index = _fixture()
    result = MultiViewNoveltyEngine(index).score(query, top_k_precedents=2)
    assert result.primary_baseline == "one_minus_maximum_reference_tanimoto"
    assert result.structure_novelty.product_morgan.novelty == 0.0
    assert result.structure_novelty.precursor_morgan.novelty == 0.0
    assert result.reaction_difference_novelty.reaction_difference.novelty == 0.0
    assert result.reaction_difference_novelty.changed_bond_and_atom.novelty == 0.0
    assert result.edit_semantic_novelty.normalized_edit_signature.novelty == 0.0
    assert result.reaction_difference_novelty.drfp.availability == EvidenceAvailability.UNAVAILABLE
    assert (
        result.learned_transformation_novelty.reactseq_meo.availability
        == EvidenceAvailability.UNAVAILABLE
    )
    assert result.taxonomy_recognition.availability == EvidenceAvailability.UNAVAILABLE
    assert result.interpretations == ("structurally familiar and transformation-familiar",)
    assert result.top_precedents[0].source_reaction_id == "substitution"
    assert "plausibility" not in type(result).model_fields


def test_explicit_meo_and_taxonomy_providers_preserve_raw_provenance() -> None:
    query, index = _fixture()
    provenance = (
        ProvenanceRecord(
            source="fixture-provider",
            source_version="1",
            artifact_sha256="0" * 64,
            license="fixture-only",
        ),
    )
    meo = MappingReactSeqMEOProvider(
        {query.reaction_id: (1.0, 0.0)},
        provider_id="fixture-meo/1",
        provenance=provenance,
    )
    taxonomy = CallableReactionClassProvider(
        lambda reaction: ("substitution", 0.87, True),
        provider_id="fixture-classifier/1",
        provenance=provenance,
    )
    result = MultiViewNoveltyEngine(index, meo_provider=meo, class_provider=taxonomy).score(query)
    assert result.learned_transformation_novelty.reactseq_meo.novelty == 0.0
    assert result.taxonomy_recognition.class_label == "substitution"
    assert result.taxonomy_recognition.class_frequency == 1
    assert result.taxonomy_recognition.provider_raw_score == 0.87
    assert (
        result.taxonomy_recognition.metadata["provider_raw_score_is_calibrated_probability"]
        is False
    )


def test_empty_reference_index_returns_unavailable_not_fake_scores() -> None:
    query, _ = _fixture()
    empty = ReferenceIndex.build((), corpus_id="empty", corpus_version="v1")
    result = MultiViewNoveltyEngine(empty).score(query)
    assert result.structure_novelty.product_morgan.availability == EvidenceAvailability.UNAVAILABLE
    assert result.structure_novelty.product_morgan.novelty is None
    assert result.interpretations == ("unavailable evidence",)
    assert result.top_precedents == ()


def test_provider_unavailable_and_threshold_validation_are_explicit() -> None:
    query, index = _fixture()
    assert (
        UnavailableReactSeqMEOProvider().embed(query).availability
        == EvidenceAvailability.UNAVAILABLE
    )
    assert (
        UnavailableReactionClassProvider().classify(query, index).availability
        == EvidenceAvailability.UNAVAILABLE
    )
    with pytest.raises(ValueError, match="familiarity"):
        MultiViewNoveltyEngine(index, familiarity_similarity_threshold=1.1)
    with pytest.raises(ValueError, match="close-centre"):
        MultiViewNoveltyEngine(index, close_centre_similarity_threshold=-0.1)


def test_missing_explicit_meo_vector_remains_unavailable() -> None:
    query, index = _fixture()
    provider = MappingReactSeqMEOProvider(
        {},
        provider_id="empty-explicit-provider",
        provenance=(),
    )
    result = MultiViewNoveltyEngine(index, meo_provider=provider).score(query)
    assert (
        result.learned_transformation_novelty.reactseq_meo.availability
        == EvidenceAvailability.UNAVAILABLE
    )
