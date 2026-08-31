from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from synthaudit.adapters.mapped_reaction_smiles import (
    MappedReactionSmilesAdapter,
    MappedReactionSmilesInput,
)
from synthaudit.precedent import (
    IndexConditionEvidenceProvider,
    LocalPrecedentEvidenceProvider,
    MappingProcedureEvidenceProvider,
    PrecedentRetriever,
    ReferenceIndex,
    ReferenceReactionV1,
    UnavailableConditionEvidenceProvider,
    UnavailableProcedureEvidenceProvider,
)
from synthaudit.schema import ProvenanceRecord, ReactionConditions, ReactionIRV1
from synthaudit.schema.evidence import EvidenceAvailability


def _reaction(reaction_smiles: str) -> ReactionIRV1:
    return MappedReactionSmilesAdapter().to_reaction_ir(
        MappedReactionSmilesInput(reaction_smiles=reaction_smiles)
    )


def _records() -> tuple[ReferenceReactionV1, ...]:
    substitution = _reaction("[CH3:1][CH2:2][Br:3].[OH-:4]>>[CH3:1][CH2:2][OH:4]")
    reduction = _reaction("[CH3:1][CH3:2]>>[CH2:1]=[CH2:2]")
    return (
        ReferenceReactionV1(
            source_dataset="fixture-corpus",
            source_reaction_id="ref-substitution",
            data_license_status="CC0-fixture",
            reaction=substitution,
            reaction_class="substitution",
            conditions=ReactionConditions(solvents=("water",), source_text="fixture only"),
            reported_yield=80.0,
        ),
        ReferenceReactionV1(
            source_dataset="fixture-corpus",
            source_reaction_id="ref-reduction",
            data_license_status="CC0-fixture",
            reaction=reduction,
            reaction_class="reduction",
        ),
    )


def test_reference_index_is_deterministic_and_verifies_hash(tmp_path: Path) -> None:
    index = ReferenceIndex.build(
        tuple(reversed(_records())), corpus_id="fixture", corpus_version="2026-08-31"
    )
    assert [item.source_reaction_id for item in index.records] == [
        "ref-reduction",
        "ref-substitution",
    ]
    assert index.class_frequency("substitution") == 1
    target = index.save(tmp_path / "index.json")
    loaded = ReferenceIndex.load(target)
    assert loaded.manifest.records_sha256 == index.manifest.records_sha256
    assert loaded.manifest.record_count == 2

    payload = json.loads(target.read_text(encoding="utf-8"))
    payload["records"][0]["source_dataset"] = "tampered"
    target.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="SHA-256"):
        ReferenceIndex.load(target)


def test_precedent_retrieval_separates_six_similarity_axes() -> None:
    index = ReferenceIndex.build(_records(), corpus_id="fixture", corpus_version="v1")
    query = _records()[0].reaction
    result = PrecedentRetriever(index).search(query, top_k=2)
    assert result.hits[0].source_reaction_id == "ref-substitution"
    assert result.hits[0].substrate_similarity == 1.0
    assert result.hits[0].product_similarity == 1.0
    assert result.hits[0].transformation_similarity == 1.0
    assert result.hits[0].reaction_centre_similarity == 1.0
    assert result.hits[0].leaving_group_similarity == 1.0
    assert result.hits[0].stereo_similarity is None
    assert "missing stereo precedent" in result.hits[0].missing_evidence
    assert "not experimental validation" in result.notice
    assert result.hits[0].reported_yield == 80.0
    assert result.hits[0].conditions is not None
    assert result.hits[0].similarity_methods["transformation"].endswith("Tanimoto")
    assert result.hits[0].fingerprint_specification.radius == 2

    local = LocalPrecedentEvidenceProvider(PrecedentRetriever(index))
    assert local.search(query, top_k=1).hits[0].source_reaction_id == "ref-substitution"
    with pytest.raises(ValueError, match="positive"):
        local.search(query, top_k=0)


def test_procedure_and_condition_providers_fail_explicitly_closed() -> None:
    procedure = UnavailableProcedureEvidenceProvider().retrieve("ref-1")
    conditions = UnavailableConditionEvidenceProvider().retrieve("ref-1")
    assert procedure.availability == EvidenceAvailability.UNAVAILABLE
    assert conditions.availability == EvidenceAvailability.UNAVAILABLE
    assert procedure.procedure_text is None
    assert conditions.conditions is None


def test_explicit_procedure_and_index_condition_providers_preserve_terms() -> None:
    index = ReferenceIndex.build(_records(), corpus_id="fixture", corpus_version="v1")
    provenance = (ProvenanceRecord(source="fixture", source_version="v1", license="CC0-fixture"),)
    procedures = MappingProcedureEvidenceProvider(
        {"ref-substitution": ("Fixture procedure text.", "CC0-fixture", provenance)}
    )
    procedure = procedures.retrieve("ref-substitution")
    missing = procedures.retrieve("missing")
    condition = IndexConditionEvidenceProvider(index).retrieve("ref-substitution")
    no_condition = IndexConditionEvidenceProvider(index).retrieve("ref-reduction")
    assert procedure.availability == EvidenceAvailability.AVAILABLE
    assert procedure.data_license_status == "CC0-fixture"
    assert missing.availability == EvidenceAvailability.UNAVAILABLE
    assert condition.availability == EvidenceAvailability.AVAILABLE
    assert condition.conditions is not None
    assert "not validated" in condition.transfer_interpretation
    assert no_condition.availability == EvidenceAvailability.UNAVAILABLE


@pytest.mark.parametrize(
    "statement",
    [
        "from synthaudit.precedent import ReferenceIndex; "
        "from synthaudit.novelty import MultiViewNoveltyEngine",
        "from synthaudit.novelty import MultiViewNoveltyEngine; "
        "from synthaudit.precedent import ReferenceIndex",
    ],
)
def test_public_packages_import_in_either_order(statement: str) -> None:
    completed = subprocess.run(
        [sys.executable, "-c", statement],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
