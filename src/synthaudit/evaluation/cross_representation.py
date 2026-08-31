"""Cross-representation conformance classification over canonical ReactionIR."""

from __future__ import annotations

from typing import Literal

from synthaudit import __version__
from synthaudit.graph.comparison import compare_precursor_sets, compare_reaction_ir
from synthaudit.schema.common import ProvenanceRecord
from synthaudit.schema.reaction_ir import ReactionIRV1
from synthaudit.schema.results import (
    ComparisonState,
    RepresentationConformanceV1,
)

ConformanceClassification = Literal[
    "semantically_equivalent",
    "equivalent_except_atom_map_renumbering",
    "equivalent_except_unspecified_stereo",
    "partially_representable",
    "unsupported",
    "indeterminate",
    "different",
]


def compare_representations(
    left: ReactionIRV1,
    right: ReactionIRV1,
    *,
    left_representation: str,
    right_representation: str,
    information_lost: tuple[str, ...] = (),
    unsupported_cases: tuple[str, ...] = (),
) -> RepresentationConformanceV1:
    """Classify semantic agreement without claiming lossless conversion."""
    comparison = compare_reaction_ir(left, right)
    product = compare_precursor_sets((left.product.mapped_smiles,), (right.product.mapped_smiles,))
    product_equivalent = product.equivalent_precursor_set
    stereo_unspecified = bool(left.stereo_edits) != bool(right.stereo_edits)
    classification: ConformanceClassification
    if comparison.state == ComparisonState.INDETERMINATE:
        classification = "indeterminate"
    elif unsupported_cases and comparison.state != ComparisonState.EQUIVALENT:
        classification = "unsupported"
    elif (
        product_equivalent
        and comparison.equivalent_reaction_centre
        and comparison.equivalent_attachment_completion
        and comparison.equivalent_stereo_result is False
        and stereo_unspecified
        and "atom_state" not in comparison.mismatch_categories
    ):
        classification = "equivalent_except_unspecified_stereo"
    elif comparison.state == ComparisonState.EQUIVALENT:
        if comparison.exact_semantic_equivalence:
            classification = "semantically_equivalent"
        elif comparison.mismatch_categories == ("atom_map_renumbering",):
            classification = "equivalent_except_atom_map_renumbering"
        else:
            classification = "partially_representable"
    elif any(
        value is True
        for value in (
            product_equivalent,
            comparison.equivalent_precursor_set,
            comparison.equivalent_reaction_centre,
            comparison.equivalent_attachment_completion,
            comparison.equivalent_stereo_result,
        )
    ):
        classification = "partially_representable"
    else:
        classification = "different"
    return RepresentationConformanceV1(
        left_representation=left_representation,
        right_representation=right_representation,
        classification=classification,
        product_equivalent=product_equivalent,
        comparison=comparison,
        information_lost=information_lost,
        unsupported_cases=unsupported_cases,
        provenance=(
            ProvenanceRecord(
                source="synthaudit",
                source_version=__version__,
                adapter="cross-representation-conformance",
                adapter_version="1",
                license="Apache-2.0",
            ),
        ),
    )
