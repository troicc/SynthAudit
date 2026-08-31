from __future__ import annotations

import json
import subprocess

import pytest

from synthaudit.adapters.reactseq import (
    REACTSEQ_UPSTREAM_COMMIT,
    ReactSeqAdapter,
    ReactSeqAdapterInput,
    ReactSeqOfficialBridge,
    ReactSeqOfficialBridgeError,
    ReactSeqSyntaxError,
    ReactSeqUnsupportedError,
)
from synthaudit.graph.executor import ReactionExecutor
from synthaudit.graph.semantic_hash import reaction_ir_semantic_hash
from synthaudit.schema.edits import (
    AddBondEdit,
    AttachFragmentEdit,
    BreakBondEdit,
    ClearBondStereoEdit,
    SetAtomStateEdit,
    SetBondStereoEdit,
    SetTetrahedralStereoEdit,
)


def test_break_tail_and_source_ranges_normalize_to_stable_maps() -> None:
    source = "CC>>>C!C<><[Br:1]>"
    result = ReactSeqAdapter().normalize(
        ReactSeqAdapterInput(reactseq=source, mapped_product_smiles="[CH3:7][CH3:9]")
    )

    edit = result.reaction_ir.core_edits[0]
    assert isinstance(edit, BreakBondEdit)
    assert {edit.map_a, edit.map_b} == {7, 9}
    assert source[edit.source_range.start : edit.source_range.end] == "!"
    assert result.traversal_context.attachment_point_order == (1, 2)
    assert result.reaction_ir.attachment_edits[1].connections[0].product_atom_map == 9


def test_atom_marker_categories_map_to_charge_chirality_and_add_bond() -> None:
    charge = ReactSeqAdapter().to_reaction_ir(
        ReactSeqAdapterInput(
            reactseq="CN>>>C[\N{GREEK SMALL LETTER ALPHA}NH2]",
            mapped_product_smiles="[CH3:1][NH2:2]",
        )
    )
    assert isinstance(charge.atom_state_edits[0], SetAtomStateEdit)
    assert charge.atom_state_edits[0].to_value == 1

    stereo = ReactSeqAdapter().to_reaction_ir(
        ReactSeqAdapterInput(
            reactseq="[C@H](F)(Cl)Br>>>[rC@H](F)(Cl)Br",
            mapped_product_smiles="[C@H:1]([F:2])([Cl:3])[Br:4]",
        )
    )
    assert isinstance(stereo.stereo_edits[0], SetTetrahedralStereoEdit)
    assert stereo.stereo_edits[0].configuration == "R"

    add_bond = ReactSeqAdapter().to_reaction_ir(
        ReactSeqAdapterInput(
            reactseq="CC.CC>>>[δCH3]C.[δCH3]C",
            mapped_product_smiles="[CH3:1][CH3:2].[CH3:3][CH3:4]",
        )
    )
    assert isinstance(add_bond.core_edits[0], AddBondEdit)
    assert {add_bond.core_edits[0].map_a, add_bond.core_edits[0].map_b} == {1, 3}


def test_chirality_and_charge_can_coexist_on_one_atom_token() -> None:
    reaction = ReactSeqAdapter().to_reaction_ir(
        ReactSeqAdapterInput(
            reactseq=("[C@H](F)(Cl)Br>>>[r\N{GREEK SMALL LETTER ALPHA}C@H](F)(Cl)Br"),
            mapped_product_smiles="[C@H:1]([F:2])([Cl:3])[Br:4]",
        )
    )
    assert isinstance(reaction.atom_state_edits[0], SetAtomStateEdit)
    assert reaction.atom_state_edits[0].to_value == 1
    assert isinstance(reaction.stereo_edits[0], SetTetrahedralStereoEdit)


def test_bond_order_decrease_creates_two_completion_points() -> None:
    reaction = ReactSeqAdapter().to_reaction_ir(
        ReactSeqAdapterInput(
            reactseq="C=C>>>C_C<><>",
            mapped_product_smiles="[CH2:1]=[CH2:2]",
        )
    )
    assert reaction.stage_metadata["attachment_reactseq_indexes"] == [1, 2]
    execution = ReactionExecutor().execute(reaction)
    assert execution.success
    assert execution.mapped_structures == ("[CH3:1][CH3:2]",)


def test_bond_stereo_and_combined_order_marker_are_separate_stages() -> None:
    reaction = ReactSeqAdapter().to_reaction_ir(
        ReactSeqAdapterInput(
            reactseq="CC>>>C;&C",
            mapped_product_smiles="[CH3:1][CH3:2]",
        )
    )
    assert reaction.core_edits[0].edit_type == "change_bond_order"
    assert isinstance(reaction.stereo_edits[0], ClearBondStereoEdit)

    ez = ReactSeqAdapter().to_reaction_ir(
        ReactSeqAdapterInput(
            reactseq="CC>>>C;{C",
            mapped_product_smiles="[CH3:1][CH3:2]",
        )
    )
    assert isinstance(ez.stereo_edits[0], SetBondStereoEdit)
    assert ez.stereo_edits[0].stereo == "E"


def test_direct_hydrogen_completion_executes_official_demo_case() -> None:
    product = "COC1=CC(C(=O)OC2=C(Br)C=C(Br)C=C2OC)=CC=C1O"
    header = "COC1=CC(C(=O)OC2=C(Br)C=C(Br)C=C2OC)=CC=C1[~OH]<[CH3:1]>"
    mapped = (
        "[CH3:1][O:2][C:3]1=[CH:4][C:5]([C:6](=[O:7])[O:8][C:9]2="
        "[C:10]([Br:11])[CH:12]=[C:13]([Br:14])[CH:15]=[C:16]2[O:17]"
        "[CH3:18])=[CH:19][CH:20]=[C:21]1[OH:22]"
    )
    reaction = ReactSeqAdapter().to_reaction_ir(
        ReactSeqAdapterInput(reactseq=f"{product}>>>{header}", mapped_product_smiles=mapped)
    )
    execution = ReactionExecutor().execute(reaction)
    assert execution.success
    assert "[O:22][CH3:23]" in execution.mapped_structures[0]


def test_starred_multi_attachment_group_is_not_duplicated() -> None:
    reaction = ReactSeqAdapter().to_reaction_ir(
        ReactSeqAdapterInput(
            reactseq="CC>>>C!C<[O:1]C[O:1]*><[O:1]C[O:1]*>",
            mapped_product_smiles="[CH3:1][CH3:2]",
        )
    )
    fragments = [
        edit
        for edit in reaction.attachment_edits
        if isinstance(edit, AttachFragmentEdit) and edit.attachment_kind == "fragment"
    ]
    assert len(fragments) == 1
    assert {
        (item.product_atom_map, item.fragment_atom_map) for item in fragments[0].connections
    } == {
        (1, 3),
        (2, 5),
    }


def test_one_fragment_atom_can_be_referenced_by_multiple_attachment_points() -> None:
    reaction = ReactSeqAdapter().to_reaction_ir(
        ReactSeqAdapterInput(
            reactseq="CC>>>C!C<[O:1]*><[O:1]*>",
            mapped_product_smiles="[CH3:1][CH3:2]",
        )
    )
    fragment = next(
        edit
        for edit in reaction.attachment_edits
        if isinstance(edit, AttachFragmentEdit) and edit.attachment_kind == "fragment"
    )
    assert {(item.product_atom_map, item.fragment_atom_map) for item in fragment.connections} == {
        (1, 3),
        (2, 3),
    }


def test_cyclic_stereo_clear_is_preserved_for_dedicated_audit_path() -> None:
    reaction = ReactSeqAdapter().to_reaction_ir(
        ReactSeqAdapterInput(
            reactseq="C1[C@H](F)CCC1>>>C1[?C@H](F)CCC1",
            mapped_product_smiles="[CH2:1]1[C@H:2]([F:3])[CH2:4][CH2:5][CH2:6]1",
        )
    )
    assert reaction.stereo_edits[0].edit_type == "clear_tetrahedral_stereo"


def test_charge_only_and_null_tail_records_are_explicit() -> None:
    reaction = ReactSeqAdapter().to_reaction_ir(
        ReactSeqAdapterInput(
            reactseq="C[NH2+]>>>C![NH2+]<-1><>",
            mapped_product_smiles="[CH3:1][NH2+:2]",
        )
    )
    assert reaction.attachment_edits[0].attachment_kind == "charge_only"
    assert reaction.attachment_edits[0].charge_delta == -1
    assert reaction.attachment_edits[1].attachment_kind == "null"


def test_different_product_traversals_have_same_semantic_hash() -> None:
    mapped_product = "[CH3:1][CH2:2][OH:3]"
    first = ReactSeqAdapter().to_reaction_ir(
        ReactSeqAdapterInput(reactseq="CCO>>>C!CO<><[Br:1]>", mapped_product_smiles=mapped_product)
    )
    second = ReactSeqAdapter().to_reaction_ir(
        ReactSeqAdapterInput(reactseq="OCC>>>OC!C<[Br:1]><>", mapped_product_smiles=mapped_product)
    )
    assert reaction_ir_semantic_hash(first) == reaction_ir_semantic_hash(second)


def test_tail_count_and_ambiguous_add_bond_fail_closed() -> None:
    with pytest.raises(ReactSeqSyntaxError):
        ReactSeqAdapter().normalize(
            ReactSeqAdapterInput(reactseq="CC>>>C!C<>", mapped_product_smiles="[CH3:1][CH3:2]")
        )
    with pytest.raises(ReactSeqUnsupportedError):
        ReactSeqAdapter().normalize(
            ReactSeqAdapterInput(
                reactseq="CCC>>>[δCH3][δCH2][δCH3]",
                mapped_product_smiles="[CH3:1][CH2:2][CH3:3]",
            )
        )


def test_official_bridge_validates_protocol_and_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(command: tuple[str, ...], **kwargs: object) -> subprocess.CompletedProcess[str]:
        request = json.loads(str(kwargs["input"]))
        response = {
            "protocol_version": "synthaudit.reactseq-bridge/1",
            "request_id": request["request_id"],
            "success": True,
            "upstream_commit": REACTSEQ_UPSTREAM_COMMIT,
            "result": {"reactseq": "CC>>>C!C<><>"},
            "error": None,
            "runtime": {"python": "3.7.17"},
        }
        return subprocess.CompletedProcess(command, 0, json.dumps(response) + "\n", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    response = ReactSeqOfficialBridge(("python3.7", "server.py")).convert_reaction(
        "[CH3:1]>>[CH3:1][CH3:2]"
    )
    assert response.result["reactseq"] == "CC>>>C!C<><>"


def test_official_bridge_rejects_non_jsonl_output(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args, 0, "noise\nnoise\n", ""),
    )
    with pytest.raises(ReactSeqOfficialBridgeError):
        ReactSeqOfficialBridge(("worker",)).inspect_runtime()
