"""Multi-axis local precedent retrieval without an opaque aggregate score."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from synthaudit import __version__
from synthaudit.novelty.fingerprints import (
    attachment_fingerprint,
    morgan_fingerprint,
    precursor_structures,
    reaction_centre_fingerprint,
    reaction_difference_fingerprint,
    stereo_fingerprint,
    tanimoto,
)
from synthaudit.precedent.index import ReferenceIndex
from synthaudit.precedent.models import PrecedentHitV1, PrecedentSearchResultV1, ReferenceReactionV1
from synthaudit.schema.common import ProvenanceRecord
from synthaudit.schema.reaction_ir import ReactionIRV1


def _optional_similarity(
    left_factory: Callable[[], Any | None],
    right_factory: Callable[[], Any | None],
) -> float | None:
    try:
        left = left_factory()
        right = right_factory()
    except Exception:
        return None
    if left is None or right is None:
        return None
    return tanimoto(left, right)


def _interpret_hit(
    *,
    substrate: float | None,
    transformation: float | None,
    centre: float | None,
    leaving_group: float | None,
    stereo: float | None,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    interpretation: list[str] = []
    missing: list[str] = []
    if transformation is not None and transformation >= 0.7:
        interpretation.append("transformation precedent")
    if (
        transformation is not None
        and transformation >= 0.7
        and (substrate is None or substrate < 0.4)
    ):
        interpretation.append("strong transformation match with weak substrate-context match")
    if centre is not None and centre >= 0.7:
        interpretation.append("close reaction-centre precedent")
    if leaving_group is not None and leaving_group >= 0.7:
        interpretation.append("leaving-group precedent")
    if stereo is None:
        missing.append("missing stereo precedent")
    elif stereo >= 0.7:
        interpretation.append("stereo-edit precedent")
    if substrate is None:
        missing.append("substrate similarity unavailable")
    if transformation is None:
        missing.append("transformation similarity unavailable")
    if centre is None:
        missing.append("reaction-centre similarity unavailable")
    if leaving_group is None:
        missing.append("leaving-group similarity unavailable")
    return tuple(interpretation or ("distant or incomplete precedent evidence",)), tuple(missing)


class PrecedentRetriever:
    """Retrieve and rank by a declared lexicographic set of six similarities."""

    def __init__(self, reference_index: ReferenceIndex) -> None:
        self.reference_index = reference_index

    def _hit(self, query: ReactionIRV1, reference: ReferenceReactionV1) -> PrecedentHitV1:
        target = reference.reaction
        substrate = _optional_similarity(
            lambda: morgan_fingerprint(precursor_structures(query)),
            lambda: morgan_fingerprint(precursor_structures(target)),
        )
        product = _optional_similarity(
            lambda: morgan_fingerprint(query.product.mapped_smiles),
            lambda: morgan_fingerprint(target.product.mapped_smiles),
        )
        transformation = _optional_similarity(
            lambda: reaction_difference_fingerprint(query),
            lambda: reaction_difference_fingerprint(target),
        )
        centre = _optional_similarity(
            lambda: reaction_centre_fingerprint(query),
            lambda: reaction_centre_fingerprint(target),
        )
        leaving_group = _optional_similarity(
            lambda: attachment_fingerprint(query),
            lambda: attachment_fingerprint(target),
        )
        stereo = _optional_similarity(
            lambda: stereo_fingerprint(query),
            lambda: stereo_fingerprint(target),
        )
        interpretation, missing = _interpret_hit(
            substrate=substrate,
            transformation=transformation,
            centre=centre,
            leaving_group=leaving_group,
            stereo=stereo,
        )
        return PrecedentHitV1(
            source_dataset=reference.source_dataset,
            source_reaction_id=reference.source_reaction_id,
            data_license_status=reference.data_license_status,
            substrate_similarity=substrate,
            product_similarity=product,
            transformation_similarity=transformation,
            reaction_centre_similarity=centre,
            leaving_group_similarity=leaving_group,
            stereo_similarity=stereo,
            similarity_methods={
                "substrate": "Morgan Tanimoto",
                "product": "Morgan Tanimoto",
                "transformation": "SynthAudit reaction-difference Tanimoto",
                "reaction_centre": "reaction-centre Morgan Tanimoto",
                "leaving_group": "attachment-semantic Tanimoto",
                "stereo": "stereo-edit semantic Tanimoto",
            },
            fingerprint_specification=self.reference_index.manifest.fingerprint_specification,
            reaction_class=reference.reaction_class,
            conditions=reference.conditions,
            reported_yield=reference.reported_yield,
            interpretation=interpretation,
            missing_evidence=missing,
            provenance=(
                ProvenanceRecord(
                    source=reference.source_dataset,
                    source_version=self.reference_index.manifest.corpus_version,
                    adapter="PrecedentRetriever",
                    adapter_version=__version__,
                    license=reference.data_license_status,
                    metadata={"source_reaction_id": reference.source_reaction_id},
                ),
            ),
        )

    @staticmethod
    def _rank_key(hit: PrecedentHitV1) -> tuple[float, ...]:
        values = (
            hit.transformation_similarity,
            hit.reaction_centre_similarity,
            hit.product_similarity,
            hit.substrate_similarity,
            hit.leaving_group_similarity,
            hit.stereo_similarity,
        )
        numeric = tuple(-1.0 if value is None else value for value in values)
        return numeric

    def search(self, reaction: ReactionIRV1, *, top_k: int = 10) -> PrecedentSearchResultV1:
        if top_k < 1:
            raise ValueError("top_k must be positive")
        hits = [self._hit(reaction, item) for item in self.reference_index.records]
        hits.sort(key=lambda item: item.source_reaction_id)
        hits.sort(key=self._rank_key, reverse=True)
        return PrecedentSearchResultV1(
            query_reaction_id=reaction.reaction_id,
            corpus_id=self.reference_index.manifest.corpus_id,
            corpus_version=self.reference_index.manifest.corpus_version,
            hits=tuple(hits[:top_k]),
            provenance=(
                ProvenanceRecord(
                    source="synthaudit",
                    source_version=__version__,
                    adapter="PrecedentRetriever",
                    adapter_version="1",
                    artifact_sha256=self.reference_index.manifest.records_sha256,
                    license="Apache-2.0",
                ),
            ),
        )
