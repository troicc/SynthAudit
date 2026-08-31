from __future__ import annotations

from synthaudit.adapters.mapped_reaction_smiles import (
    MappedReactionSmilesAdapter,
    MappedReactionSmilesInput,
)
from synthaudit.adapters.synthex import (
    SYNTHEX_DRAFT_ID,
    SynthExPaperDraftAdapter,
    SynthExPaperDraftInput,
)
from synthaudit.evaluation.cross_representation import compare_representations
from synthaudit.graph.comparison import (
    compare_execution_results,
    compare_precursor_sets,
    compare_reaction_ir,
)
from synthaudit.graph.executor import ReactionExecutor
from synthaudit.schema.common import MoleculeRecord, MoleculeRole
from synthaudit.schema.edits import ClearTetrahedralStereoEdit, SetAtomStateEdit
from synthaudit.schema.reaction_ir import ReactionIRV1
from synthaudit.schema.results import ComparisonState, ExecutionErrorV1


def _mapped_reaction() -> ReactionIRV1:
    return MappedReactionSmilesAdapter().to_reaction_ir(
        MappedReactionSmilesInput(
            reaction_smiles="[CH3:1][CH2:2][Br:3].[OH-:4]>>[CH3:1][CH2:2][OH:4]"
        )
    )


def _draft_reaction() -> ReactionIRV1:
    return SynthExPaperDraftAdapter().to_reaction_ir(
        SynthExPaperDraftInput(
            payload={
                "schema": SYNTHEX_DRAFT_ID,
                "mapped_product_smiles": "[CH3:1][CH2:2][OH:4]",
                "operations": [
                    {"op": "break_bond", "map_a": 2, "map_b": 4},
                    {
                        "op": "change_atom",
                        "atom_map": 4,
                        "property": "formal_charge",
                        "value": -1,
                    },
                    {
                        "op": "add_group",
                        "fragment_smiles": "[Br]",
                        "connections": [{"product_atom_map": 2, "fragment_atom_index": 0}],
                    },
                ],
            }
        )
    )


def test_precursor_comparison_distinguishes_map_renumbering_from_chemistry() -> None:
    result = compare_precursor_sets(
        ("[CH3:1][Br:2]",),
        ("[CH3:8][Br:9]",),
    )
    assert result.state == ComparisonState.EQUIVALENT
    assert result.exact_semantic_equivalence is False
    assert result.mismatch_categories == ("atom_map_renumbering",)


def test_cross_representation_reactions_are_semantically_equivalent() -> None:
    left = _mapped_reaction()
    right = _draft_reaction()
    result = compare_reaction_ir(left, right)
    assert result.state == ComparisonState.EQUIVALENT
    assert result.exact_semantic_equivalence is True
    assert result.equivalent_reaction_centre is True
    assert result.equivalent_attachment_completion is True

    conformance = compare_representations(
        left,
        right,
        left_representation="mapped-reaction-smiles",
        right_representation=SYNTHEX_DRAFT_ID,
    )
    assert conformance.product_equivalent is True
    assert conformance.classification == "semantically_equivalent"


def test_cross_representation_aligns_atom_map_renumbering_by_product_graph() -> None:
    left = _mapped_reaction()
    right = MappedReactionSmilesAdapter().to_reaction_ir(
        MappedReactionSmilesInput(
            reaction_smiles=("[CH3:11][CH2:12][Br:13].[OH-:14]>>[CH3:11][CH2:12][OH:14]")
        )
    )
    result = compare_representations(
        left,
        right,
        left_representation="mapped-reaction-smiles-a",
        right_representation="mapped-reaction-smiles-b",
    )
    assert result.comparison.state == ComparisonState.EQUIVALENT
    assert result.comparison.exact_semantic_equivalence is False
    assert "atom_map_renumbering" in result.comparison.mismatch_categories
    assert result.classification == "equivalent_except_atom_map_renumbering"


def test_cross_representation_marks_symmetric_map_alignment_indeterminate() -> None:
    left = ReactionIRV1(
        reaction_id="symmetric-left",
        product=MoleculeRecord(mapped_smiles="[CH3:1][CH3:2]", role=MoleculeRole.PRODUCT),
        atom_state_edits=(
            SetAtomStateEdit(
                atom_map=1,
                property="formal_charge",
                from_value=0,
                to_value=1,
            ),
        ),
    )
    right = ReactionIRV1(
        reaction_id="symmetric-right",
        product=MoleculeRecord(mapped_smiles="[CH3:10][CH3:11]", role=MoleculeRole.PRODUCT),
        atom_state_edits=(
            SetAtomStateEdit(
                atom_map=10,
                property="formal_charge",
                from_value=0,
                to_value=1,
            ),
        ),
    )
    result = compare_representations(
        left,
        right,
        left_representation="left",
        right_representation="right",
    )
    assert result.classification == "indeterminate"
    assert "symmetric product graph" in result.comparison.reasons[0]


def test_cross_representation_classifies_unspecified_stereo_separately() -> None:
    product = MoleculeRecord(
        mapped_smiles="[C@@H:1]([F:2])([Cl:3])[Br:4]",
        role=MoleculeRole.PRODUCT,
    )
    specified = ReactionIRV1(reaction_id="specified", product=product)
    unspecified = ReactionIRV1(
        reaction_id="unspecified",
        product=product,
        stereo_edits=(ClearTetrahedralStereoEdit(atom_map=1),),
    )
    result = compare_representations(
        specified,
        unspecified,
        left_representation="specified",
        right_representation="unspecified",
        information_lost=("tetrahedral configuration",),
    )
    assert result.classification == "equivalent_except_unspecified_stereo"
    assert result.information_lost == ("tetrahedral configuration",)


def test_cross_representation_reports_unsupported_and_invalid_inputs() -> None:
    left = _mapped_reaction()
    partial = _draft_reaction().model_copy(update={"attachment_edits": ()})
    unsupported = compare_representations(
        left,
        partial,
        left_representation="mapped",
        right_representation="limited-format",
        unsupported_cases=("external fragments",),
    )
    assert unsupported.classification == "unsupported"

    invalid_product = left.product.model_copy(update={"mapped_smiles": "[C:1"})
    invalid = left.model_copy(update={"product": invalid_product})
    indeterminate = compare_representations(
        invalid,
        left,
        left_representation="invalid",
        right_representation="mapped",
    )
    assert indeterminate.classification == "indeterminate"


def test_execution_comparison_reports_graph_difference_mismatch() -> None:
    left = _mapped_reaction()
    right = _draft_reaction()
    left_execution = ReactionExecutor().execute(left)
    right_execution = ReactionExecutor().execute(right)
    result = compare_execution_results(left_execution, right_execution)
    assert result.state == ComparisonState.EQUIVALENT


def test_failed_execution_makes_comparison_indeterminate() -> None:
    reaction = _draft_reaction()
    execution = ReactionExecutor().execute(reaction)
    failed = execution.model_copy(
        update={
            "success": False,
            "structurally_valid": False,
            "error": ExecutionErrorV1(error_type="SyntheticFailure", message="test failure"),
        }
    )
    result = compare_execution_results(failed, execution)
    assert result.state == ComparisonState.INDETERMINATE
