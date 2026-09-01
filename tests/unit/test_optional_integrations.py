from __future__ import annotations

from pathlib import Path

from synthaudit.integrations.reactionclassifier import reaction_ir_to_forward_smiles
from synthaudit.integrations.rxnmapper import _split_reaction
from synthaudit.schema.reaction_ir import ReactionIRV1


def test_mapper_split_preserves_reagent_field() -> None:
    assert _split_reaction("CC>O>CO") == ("CC", "O", "CO")
    assert _split_reaction("CC>>CO") == ("CC", "", "CO")


def test_reaction_ir_can_be_prepared_for_classifier() -> None:
    reaction = ReactionIRV1.model_validate_json(
        Path("examples/reaction-ir.json").read_text(encoding="utf-8")
    )
    forward = reaction_ir_to_forward_smiles(reaction)
    assert forward.count(">>") == 1
    assert ":" not in forward
