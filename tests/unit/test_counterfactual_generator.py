from __future__ import annotations

from collections.abc import Callable

import pytest
from pydantic import ValidationError

from synthaudit.adapters.mapped_reaction_smiles import (
    MappedReactionSmilesAdapter,
    MappedReactionSmilesInput,
)
from synthaudit.counterfactuals import (
    BenchmarkLabel,
    CounterfactualCategory,
    CounterfactualGenerator,
    CounterfactualRecordV1,
    GenerationMethod,
)
from synthaudit.schema import (
    AttachFragmentEdit,
    FragmentConnection,
    MoleculeRecord,
    MoleculeRole,
    ReactionIRV1,
    RouteIRV1,
    RouteStepIRV1,
)


def _mapped(value: str, reaction_id: str) -> ReactionIRV1:
    reaction = MappedReactionSmilesAdapter().to_reaction_ir(
        MappedReactionSmilesInput(reaction_smiles=value)
    )
    return reaction.model_copy(update={"reaction_id": reaction_id})


def _substitution() -> ReactionIRV1:
    return _mapped(
        "[CH3:1][CH2:2][Br:3].[OH-:4]>>[CH3:1][CH2:2][OH:4]",
        "parent-substitution",
    )


def _ring() -> ReactionIRV1:
    return _mapped(
        "[CH2:1]=[CH:2][CH2:3][CH2:4][CH2:5][CH3:6]>>[CH2:1]1[CH2:2][CH2:3][CH2:4][CH2:5][CH2:6]1",
        "parent-ring",
    )


def _tetrahedral() -> ReactionIRV1:
    return _mapped(
        "[CH3:1][CH:2]([OH:3])[Cl:4]>>[CH3:1][C@@H:2]([OH:3])[Cl:4]",
        "parent-tetrahedral",
    )


def _alkene() -> ReactionIRV1:
    return _mapped(
        "[CH3:1][CH:2]=[CH:3][CH3:4]>>[CH3:1]/[CH:2]=[CH:3]/[CH3:4]",
        "parent-alkene",
    )


def _multi_attachment() -> ReactionIRV1:
    return ReactionIRV1(
        reaction_id="parent-multi",
        product=MoleculeRecord(
            mapped_smiles="[CH2:1][CH3:3].[CH2:2][CH3:4]",
            role=MoleculeRole.PRODUCT,
        ),
        attachment_edits=(
            AttachFragmentEdit(
                fragment_smiles="[O:5]",
                connections=(
                    FragmentConnection(product_atom_map=1, fragment_atom_map=5),
                    FragmentConnection(product_atom_map=2, fragment_atom_map=5),
                ),
            ),
        ),
    )


def _route() -> RouteIRV1:
    reactions = tuple(
        ReactionIRV1(
            reaction_id=f"route-reaction-{index}",
            product=MoleculeRecord(mapped_smiles=f"[CH4:{index}]", role=MoleculeRole.PRODUCT),
        )
        for index in (1, 2, 3)
    )
    return RouteIRV1(
        route_id="parent-route",
        target=reactions[-1].product,
        starting_materials=(
            MoleculeRecord(
                mapped_smiles="[CH4:10]",
                role=MoleculeRole.STARTING_MATERIAL,
                name="start",
                identifiers={"route_node_id": "start"},
            ),
        ),
        steps=(
            RouteStepIRV1(
                step_id="step-1",
                reaction=reactions[0],
                consumes=("start",),
                produces=("protected",),
                strategy_text="protection",
            ),
            RouteStepIRV1(
                step_id="step-2",
                reaction=reactions[1],
                depends_on=("step-1",),
                consumes=("protected",),
                produces=("fragile",),
                strategy_text="coupling",
            ),
            RouteStepIRV1(
                step_id="step-3",
                reaction=reactions[2],
                depends_on=("step-2",),
                consumes=("fragile",),
                produces=("target",),
                strategy_text="deprotection",
            ),
        ),
    )


def _recorded(reaction: ReactionIRV1, reaction_class: str) -> CounterfactualRecordV1:
    return CounterfactualGenerator().recorded_reaction(
        reaction,
        record_id=f"recorded-{reaction.reaction_id}",
        source_dataset="authored-test-fixture",
        source_version="v1",
        data_license_status="Apache-2.0 fixture",
        reaction_class=reaction_class,
    )


REACTION_METHODS: tuple[tuple[GenerationMethod, Callable[[], ReactionIRV1]], ...] = (
    *(
        (method, _substitution)
        for method in (
            GenerationMethod.DUPLICATE_ATOM_MAPS,
            GenerationMethod.DANGLING_ATOM_MAPS,
            GenerationMethod.MALFORMED_EDIT,
            GenerationMethod.MISSING_ATTACHMENT_REFERENCE,
            GenerationMethod.IMPOSSIBLE_OPERATION_ORDERING,
            GenerationMethod.INVALID_LEAVING_GROUP_SYNTAX,
            GenerationMethod.WRONG_BOND_BREAK,
            GenerationMethod.WRONG_BOND_ORDER_CHANGE,
            GenerationMethod.ALTERNATIVE_SITE_SWAP,
            GenerationMethod.CLASS_PRESERVING_CENTRE_DECOY,
            GenerationMethod.UNEXPLAINED_GRAPH_CHANGE,
            GenerationMethod.WRONG_LEAVING_GROUP,
            GenerationMethod.WRONG_ATTACHMENT_ATOM,
            GenerationMethod.MISSING_LEAVING_GROUP,
            GenerationMethod.DUPLICATE_LEAVING_GROUP,
            GenerationMethod.PRECURSOR_ANALOG_MISSING_HANDLE,
            GenerationMethod.CHARGE_ONLY_COMPLETION_ERROR,
            GenerationMethod.INVALID_CHIRAL_CENTRE_OPERATION,
        )
    ),
    (GenerationMethod.WRONG_RING_CLOSURE_ATOM, _ring),
    (GenerationMethod.CYCLIC_STEREOCHEMISTRY_CORRUPTION, _ring),
    (GenerationMethod.UNINTENDED_INVERSION, _tetrahedral),
    (GenerationMethod.OMITTED_STEREOCHEMISTRY, _tetrahedral),
    (GenerationMethod.INCORRECT_E_Z, _alkene),
    (GenerationMethod.MULTI_ATTACHMENT_TOPOLOGY_ERROR, _multi_attachment),
)


@pytest.mark.parametrize(("method", "factory"), REACTION_METHODS)
def test_every_reaction_counterfactual_method_is_seeded_and_traced(
    method: GenerationMethod,
    factory: Callable[[], ReactionIRV1],
) -> None:
    parent = _recorded(factory(), "fixture-class")
    generated = CounterfactualGenerator().generate_reaction(parent, method=method, seed=41)
    repeated = CounterfactualGenerator().generate_reaction(parent, method=method, seed=41)
    assert generated == repeated
    assert generated.label == BenchmarkLabel.GENERATED_COUNTERFACTUAL
    assert generated.parent_reaction_id == parent.reaction.reaction_id  # type: ignore[union-attr]
    assert generated.generation_method == method
    assert generated.category in CounterfactualCategory
    assert generated.seed == 41
    assert generated.changed_fields
    assert generated.changed_fields[0].json_pointer.startswith("/")
    assert generated.structural_validity.structurally_valid is not None
    assert (generated.reaction is None) != (generated.raw_candidate_payload is None)


@pytest.mark.parametrize(
    "method",
    [
        GenerationMethod.DEPENDENCY_VIOLATING_STEP_SWAP,
        GenerationMethod.DEPROTECTION_TOO_EARLY,
        GenerationMethod.PROTECTION_TOO_LATE,
        GenerationMethod.FRAGILE_INTERMEDIATE_INCOMPATIBLE_CONDITIONS,
        GenerationMethod.PRECURSOR_NOT_PRODUCED,
    ],
)
def test_every_route_counterfactual_method_preserves_parent_and_route(
    method: GenerationMethod,
) -> None:
    generator = CounterfactualGenerator()
    parent = generator.recorded_route(
        _route(),
        record_id="recorded-route",
        source_dataset="authored-test-fixture",
        source_version="v1",
        data_license_status="Apache-2.0 fixture",
        reaction_class="route-fixture",
    )
    generated = generator.generate_route(parent, method=method, seed=17)
    assert generated.category == CounterfactualCategory.ROUTE
    assert generated.parent_reaction_id == "route-reaction-3"
    assert generated.parent_route_id == "parent-route"
    assert generated.changed_fields
    assert generated.structural_validity.evaluation_scope == "route"


def test_record_model_rejects_outcome_language_and_incomplete_generation_metadata() -> None:
    parent = _recorded(_substitution(), "fixture-class")
    payload = parent.model_dump(mode="json")
    payload["label"] = "failure"
    with pytest.raises(ValidationError):
        CounterfactualRecordV1.model_validate(payload)

    payload["label"] = "generated_counterfactual"
    with pytest.raises(ValidationError, match="generated counterfactuals require"):
        CounterfactualRecordV1.model_validate(payload)
