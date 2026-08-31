"""Provider-neutral precedent, procedure, and condition evidence boundaries."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from synthaudit.precedent.index import ReferenceIndex
from synthaudit.precedent.models import (
    ConditionEvidenceV1,
    PrecedentSearchResultV1,
    ProcedureEvidenceV1,
)
from synthaudit.precedent.retrieval import PrecedentRetriever
from synthaudit.schema.common import ProvenanceRecord
from synthaudit.schema.evidence import EvidenceAvailability
from synthaudit.schema.reaction_ir import ReactionIRV1


class PrecedentEvidenceProvider(Protocol):
    def search(self, reaction: ReactionIRV1, *, top_k: int = 10) -> PrecedentSearchResultV1: ...


class ProcedureEvidenceProvider(Protocol):
    def retrieve(self, source_reaction_id: str) -> ProcedureEvidenceV1: ...


class ConditionEvidenceProvider(Protocol):
    def retrieve(self, source_reaction_id: str) -> ConditionEvidenceV1: ...


class LocalPrecedentEvidenceProvider:
    def __init__(self, retriever: PrecedentRetriever) -> None:
        self.retriever = retriever

    def search(
        self,
        reaction: ReactionIRV1,
        *,
        top_k: int = 10,
    ) -> PrecedentSearchResultV1:
        return self.retriever.search(reaction, top_k=top_k)


class UnavailableProcedureEvidenceProvider:
    def retrieve(self, source_reaction_id: str) -> ProcedureEvidenceV1:
        return ProcedureEvidenceV1(
            source_reaction_id=source_reaction_id,
            availability=EvidenceAvailability.UNAVAILABLE,
            missing_reasons=("no licensed procedure corpus was configured",),
        )


class UnavailableConditionEvidenceProvider:
    def retrieve(self, source_reaction_id: str) -> ConditionEvidenceV1:
        return ConditionEvidenceV1(
            source_reaction_id=source_reaction_id,
            availability=EvidenceAvailability.UNAVAILABLE,
            transfer_interpretation="Condition-transfer evidence is unavailable.",
            missing_reasons=("no licensed condition corpus was configured",),
        )


class MappingProcedureEvidenceProvider:
    """Return explicitly supplied licensed text; never scrape a procedure source."""

    def __init__(
        self,
        procedures: Mapping[str, tuple[str, str, tuple[ProvenanceRecord, ...]]],
    ) -> None:
        self._procedures = dict(procedures)

    def retrieve(self, source_reaction_id: str) -> ProcedureEvidenceV1:
        record = self._procedures.get(source_reaction_id)
        if record is None:
            return UnavailableProcedureEvidenceProvider().retrieve(source_reaction_id)
        text, license_status, provenance = record
        return ProcedureEvidenceV1(
            source_reaction_id=source_reaction_id,
            availability=EvidenceAvailability.AVAILABLE,
            procedure_text=text,
            data_license_status=license_status,
            provenance=provenance,
        )


class IndexConditionEvidenceProvider:
    """Expose conditions already present in a declared local reference index."""

    def __init__(self, reference_index: ReferenceIndex) -> None:
        self.reference_index = reference_index

    def retrieve(self, source_reaction_id: str) -> ConditionEvidenceV1:
        record = next(
            (
                item
                for item in self.reference_index.records
                if item.source_reaction_id == source_reaction_id
            ),
            None,
        )
        if record is None or record.conditions is None:
            return UnavailableConditionEvidenceProvider().retrieve(source_reaction_id)
        return ConditionEvidenceV1(
            source_reaction_id=source_reaction_id,
            availability=EvidenceAvailability.AVAILABLE,
            conditions=record.conditions,
            transfer_interpretation=(
                "Conditions are precedent context only; transfer to the query is not validated."
            ),
            provenance=(
                ProvenanceRecord(
                    source=record.source_dataset,
                    source_version=self.reference_index.manifest.corpus_version,
                    adapter="IndexConditionEvidenceProvider",
                    adapter_version="1",
                    license=record.data_license_status,
                ),
            ),
        )
