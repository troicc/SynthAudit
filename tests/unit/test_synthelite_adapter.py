from __future__ import annotations

import pytest

from synthaudit.adapters.errors import AtomMappingRequired
from synthaudit.adapters.synthelite import SyntheliteRouteAdapter, SyntheliteRouteInput


def _mol(smiles: str, *, children: list[dict[str, object]] | None = None) -> dict[str, object]:
    value: dict[str, object] = {
        "type": "mol",
        "hide": False,
        "smiles": smiles,
        "is_chemical": True,
        "in_stock": children is None,
    }
    if children is not None:
        value["children"] = children
    return value


def _reaction(
    smiles: str,
    mapped: str | None,
    children: list[dict[str, object]],
) -> dict[str, object]:
    metadata: dict[str, object] = {"classification": "inspected-test-fixture"}
    if mapped is not None:
        metadata["mapped_reaction_smiles"] = mapped
    return {
        "type": "reaction",
        "hide": False,
        "smiles": smiles,
        "is_reaction": True,
        "metadata": metadata,
        "children": children,
    }


def test_inspected_nested_reaction_tree_normalizes_to_route_ir() -> None:
    child_reaction = _reaction(
        "CC>>CCBr",
        "[CH3:1][CH3:2]>>[CH3:1][CH2:2][Br:4]",
        [_mol("CC")],
    )
    root_reaction = _reaction(
        "CCBr.[OH-]>>CCO",
        "[CH3:1][CH2:2][Br:4].[OH-:3]>>[CH3:1][CH2:2][OH:3]",
        [_mol("CCBr", children=[child_reaction]), _mol("[OH-]")],
    )
    payload = _mol("CCO", children=[root_reaction])
    payload["lmdata"] = {"strategy": "test strategy"}
    payload["route_metadata"] = {"rank": 1}

    result = SyntheliteRouteAdapter().normalize(
        SyntheliteRouteInput(payload=payload, route_id="synthelite-route")
    )
    route = result.route_ir
    assert [step.step_id for step in route.steps] == ["step-0-0", "step-0"]
    assert route.steps[1].depends_on == ("step-0-0",)
    assert route.strategy_text == "test strategy"
    assert len(route.intermediates) == 1
    assert {item.role.value for item in route.starting_materials} == {"starting_material"}
    assert route.metadata["score_semantics"] == (
        "preserved_upstream_metadata_not_calibrated_probability"
    )


def test_synthelite_never_maps_an_unmapped_tree_implicitly() -> None:
    payload = _mol(
        "CO",
        children=[_reaction("CBr.[OH-]>>CO", None, [_mol("CBr"), _mol("[OH-]")])],
    )
    with pytest.raises(AtomMappingRequired, match="mapped_reaction_smiles"):
        SyntheliteRouteAdapter().normalize(SyntheliteRouteInput(payload=payload))


def test_unknown_synthelite_fields_are_preserved_as_unsupported_paths() -> None:
    payload = _mol(
        "CO",
        children=[
            _reaction(
                "CBr.[OH-]>>CO",
                "[CH3:1][Br:3].[OH-:2]>>[CH3:1][OH:2]",
                [_mol("CBr"), _mol("[OH-]")],
            )
        ],
    )
    payload["future_route_field"] = {"value": 1}
    result = SyntheliteRouteAdapter().normalize(SyntheliteRouteInput(payload=payload))
    assert "0.future_route_field" in result.unsupported_fields
