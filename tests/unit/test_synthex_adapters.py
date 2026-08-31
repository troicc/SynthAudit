from __future__ import annotations

import pytest

from synthaudit.adapters.errors import (
    UnsupportedAdapterOperation,
    UpstreamSpecificationUnavailable,
)
from synthaudit.adapters.synthex import (
    SYNTHEX_DRAFT_ID,
    SYNTHEX_DRAFT_ROUTE_ID,
    SynthExOfficialAdapter,
    SynthExPaperDraftAdapter,
    SynthExPaperDraftInput,
    SynthExPaperDraftRouteAdapter,
    SynthExPaperDraftRouteInput,
)
from synthaudit.graph.executor import ReactionExecutor


def test_official_adapter_fails_closed_without_calling_draft() -> None:
    adapter = SynthExOfficialAdapter()
    with pytest.raises(UpstreamSpecificationUnavailable, match="ReactionJSON"):
        adapter.to_reaction_ir({"operations": []})
    with pytest.raises(UpstreamSpecificationUnavailable, match="RouteJSON"):
        adapter.to_route_ir({"steps": []})


def _completion_payload() -> dict[str, object]:
    return {
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
        "expected_precursors": ["[CH3:1][CH2:2][Br:5]", "[OH-:4]"],
    }


def test_draft_adapter_is_visibly_unofficial_and_executes_declared_operations() -> None:
    result = SynthExPaperDraftAdapter().normalize(
        SynthExPaperDraftInput(payload=_completion_payload())
    )
    assert result.adapter_id == SYNTHEX_DRAFT_ID
    assert result.reaction_ir.stage_metadata["official_compatibility"] is False
    assert result.warnings[0].code == "unofficial_paper_draft"
    execution = ReactionExecutor().execute(result.reaction_ir)
    assert execution.success
    assert execution.mapped_structures == (
        "[CH3:1][CH2:2][Br:5]",
        "[OH-:4]",
    )


def test_readme_delta_assumption_is_explicit_and_source_order_is_validated() -> None:
    result = SynthExPaperDraftAdapter().normalize(
        SynthExPaperDraftInput(
            mapped_product_smiles="[CH3:8][CH3:16]",
            payload=[
                {
                    "op": "change_bond_order",
                    "map_a": 8,
                    "map_b": 16,
                    "delta": 1,
                    "future_field": "preserved",
                }
            ],
        )
    )
    edit = result.reaction_ir.core_edits[0]
    assert edit.from_order == 1.0
    assert edit.to_order == 2.0
    assert "bond-order delta is added" in result.reaction_ir.stage_metadata["assumptions"][1]
    assert result.unsupported_fields == ("operations[0].future_field",)


def test_draft_supports_remove_group_hydrogen_and_stereo_operations() -> None:
    payload = {
        "schema": SYNTHEX_DRAFT_ID,
        "mapped_product_smiles": "[C@H:1]([F:2])([Cl:3])[CH2:4][CH:5]=[CH:6][Br:7]",
        "operations": [
            {"op": "set_explicit_h", "atom_map": 4, "count": 1},
            {"op": "invert_stereocenter", "atom_map": 1},
            {"op": "clear_stereocenter", "atom_map": 1},
            {"op": "set_bond_stereo", "map_a": 5, "map_b": 6, "stereo": "E"},
            {
                "op": "remove_group",
                "fragment_atom_maps": [7],
                "attachment_bonds": [[6, 7]],
            },
        ],
    }
    reaction = SynthExPaperDraftAdapter().to_reaction_ir(SynthExPaperDraftInput(payload=payload))
    assert reaction.atom_state_edits[0].edit_type == "set_explicit_hydrogen"
    assert [edit.edit_type for edit in reaction.stereo_edits] == [
        "invert_tetrahedral_stereo",
        "clear_tetrahedral_stereo",
        "set_bond_stereo",
    ]
    assert reaction.attachment_edits[0].edit_type == "detach_fragment"


@pytest.mark.parametrize(
    "payload,match",
    [
        (
            {
                "schema": SYNTHEX_DRAFT_ID,
                "mapped_product_smiles": "[CH3:1]",
                "operations": [{"op": "invented"}],
            },
            "unsupported draft operation",
        ),
        (
            {
                "schema": SYNTHEX_DRAFT_ID,
                "mapped_product_smiles": "[CH3:1]",
                "operations": [
                    {
                        "op": "add_group",
                        "fragment_smiles": "[Br:1]",
                        "connections": [{"product_atom_map": 1, "fragment_atom_map": 1}],
                    }
                ],
            },
            "collide",
        ),
    ],
)
def test_unknown_or_ambiguous_draft_semantics_are_rejected(
    payload: dict[str, object], match: str
) -> None:
    with pytest.raises((UnsupportedAdapterOperation, ValueError), match=match):
        SynthExPaperDraftAdapter().normalize(SynthExPaperDraftInput(payload=payload))


def test_paper_draft_route_has_explicit_namespace_and_dependencies() -> None:
    payload = {
        "schema": SYNTHEX_DRAFT_ROUTE_ID,
        "route_id": "draft-route",
        "target": "[CH3:1][OH:2]",
        "starting_materials": ["[CH3:1][Br:3]"],
        "intermediates": ["[CH3:1][OH:2]"],
        "steps": [
            {
                "step_id": "s1",
                "reaction": {
                    "schema": SYNTHEX_DRAFT_ID,
                    "operations": [],
                },
                "mapped_product_smiles": "[CH3:1][Br:3]",
            },
            {
                "step_id": "s2",
                "depends_on": ["s1"],
                "reaction": {
                    "schema": SYNTHEX_DRAFT_ID,
                    "operations": [],
                },
                "mapped_product_smiles": "[CH3:1][OH:2]",
            },
        ],
    }
    result = SynthExPaperDraftRouteAdapter().normalize(SynthExPaperDraftRouteInput(payload=payload))
    assert result.adapter_id == SYNTHEX_DRAFT_ROUTE_ID
    assert result.route_ir.steps[1].depends_on == ("s1",)
    assert result.route_ir.metadata["official_compatibility"] is False
