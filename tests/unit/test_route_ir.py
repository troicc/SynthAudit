from __future__ import annotations

import pytest
from pydantic import ValidationError

from synthaudit.schema import (
    MoleculeRecord,
    MoleculeRole,
    ReactionIRV1,
    RouteIRV1,
    RouteStepIRV1,
)


def _reaction(reaction_id: str) -> ReactionIRV1:
    return ReactionIRV1(
        reaction_id=reaction_id,
        product=MoleculeRecord(mapped_smiles="[CH3:1][OH:2]", role=MoleculeRole.PRODUCT),
    )


def test_route_round_trip_and_dependency_references() -> None:
    route = RouteIRV1(
        route_id="route-1",
        target=MoleculeRecord(mapped_smiles="[CH3:1][OH:2]", role=MoleculeRole.PRODUCT),
        steps=(
            RouteStepIRV1(step_id="s1", reaction=_reaction("r1")),
            RouteStepIRV1(step_id="s2", reaction=_reaction("r2"), depends_on=("s1",)),
        ),
    )
    assert RouteIRV1.model_validate_json(route.model_dump_json()) == route


def test_route_rejects_unknown_dependency() -> None:
    with pytest.raises(ValidationError, match="unknown route dependency"):
        RouteIRV1(
            route_id="bad-route",
            target=MoleculeRecord(mapped_smiles="[CH3:1][OH:2]", role=MoleculeRole.PRODUCT),
            steps=(RouteStepIRV1(step_id="s1", reaction=_reaction("r1"), depends_on=("x",)),),
        )


def test_route_rejects_duplicate_step_ids() -> None:
    with pytest.raises(ValidationError, match="step IDs must be unique"):
        RouteIRV1(
            route_id="bad-route",
            target=MoleculeRecord(mapped_smiles="[CH3:1][OH:2]", role=MoleculeRole.PRODUCT),
            steps=(
                RouteStepIRV1(step_id="s1", reaction=_reaction("r1")),
                RouteStepIRV1(step_id="s1", reaction=_reaction("r2")),
            ),
        )
