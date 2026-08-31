"""ReactSeq tail normalization with explicit attachment-point identity."""

from __future__ import annotations

from dataclasses import dataclass

from rdkit import Chem

from synthaudit.adapters.reactseq.errors import (
    ReactSeqSyntaxError,
    ReactSeqUnsupportedError,
)
from synthaudit.adapters.reactseq.models import (
    ReactSeqDocument,
    ReactSeqHeaderParseResult,
    ReactSeqTailParseResult,
    ReactSeqTraversalContext,
)
from synthaudit.graph.atom_maps import atom_map_index, parse_mapped_molecule
from synthaudit.schema.edits import (
    AttachFragmentEdit,
    BreakBondEdit,
    ChangeBondOrderEdit,
    FragmentConnection,
    SetExplicitHydrogenEdit,
    SourceRange,
)


@dataclass(frozen=True)
class _TailItem:
    tail_index: int
    value: str
    source_range: SourceRange


def _tail_items(document: ReactSeqDocument) -> tuple[tuple[_TailItem, ...], ...]:
    records: list[tuple[_TailItem, ...]] = []
    for tail_index, tail in enumerate(document.tails):
        if tail.raw == "":
            records.append(())
            continue
        items: list[_TailItem] = []
        cursor = 0
        for value in tail.raw.split(","):
            if value == "":
                raise ReactSeqSyntaxError(
                    "empty item inside a non-empty ReactSeq tail",
                    source_range=tail.source_range,
                )
            start = tail.source_range.start + 1 + cursor
            items.append(
                _TailItem(
                    tail_index=tail_index,
                    value=value,
                    source_range=SourceRange(start=start, end=start + len(value)),
                )
            )
            cursor += len(value) + 1
        records.append(tuple(items))
    return tuple(records)


def _attachment_order(
    header: ReactSeqHeaderParseResult,
    context: ReactSeqTraversalContext,
) -> tuple[tuple[int, int], ...]:
    return tuple(
        (reactseq_index, context.stable_map(reactseq_index))
        for reactseq_index in header.attachment_reactseq_indexes
    )


def _infer_attachment_order(atom: Chem.Atom, *, shared_attachment_atom: bool) -> float:
    """Mirror the pinned upstream converter's documented valence decision path."""
    if shared_attachment_atom:
        return 1.0
    symbol = atom.GetSymbol()
    valence = atom.GetTotalValence()
    charge = atom.GetFormalCharge()
    double_cases = {
        ("O", 0, 0),
        ("S", 0, 0),
        ("S", 2, 0),
        ("S", 4, 0),
        ("S", 1, 1),
        ("P", 3, 0),
        ("C", 2, 0),
        ("N", 2, 1),
        ("N", 1, 0),
        ("N", 0, -1),
        ("Se", 2, 0),
        ("Si", 2, 0),
        ("Mn", 5, 0),
        ("Cr", 4, 0),
        ("O", 1, 1),
    }
    triple_cases = {("N", 0, 0), ("C", 1, 0), ("C", 0, -1)}
    if (symbol, valence, charge) in double_cases:
        return 2.0
    if (symbol, valence, charge) in triple_cases:
        return 3.0
    return 1.0


def _mapped_fragment(
    raw_fragment: str,
    *,
    next_atom_map: int,
) -> tuple[str, tuple[int, ...], tuple[Chem.Atom, ...], int]:
    molecule = Chem.MolFromSmiles(raw_fragment)
    if molecule is None:
        raise ReactSeqSyntaxError(f"ReactSeq leaving group is not valid SMILES: {raw_fragment!r}")
    source_maps = tuple(atom.GetAtomMapNum() for atom in molecule.GetAtoms())
    unsupported_maps = sorted({value for value in source_maps if value not in {0, 1}})
    if unsupported_maps:
        raise ReactSeqUnsupportedError(
            "ReactSeq leaving-group atoms may only use attachment annotation ':1'",
            details={"unsupported_annotations": unsupported_maps},
        )
    attachment_indices = tuple(
        atom.GetIdx() for atom in molecule.GetAtoms() if atom.GetAtomMapNum() == 1
    )
    if not attachment_indices:
        raise ReactSeqSyntaxError(
            "ReactSeq leaving group has no ':1' attachment atom",
        )
    attachment_atoms = tuple(molecule.GetAtomWithIdx(index) for index in attachment_indices)
    assigned_maps: list[int] = []
    for offset, atom in enumerate(molecule.GetAtoms()):
        assigned_map = next_atom_map + offset
        assigned_maps.append(assigned_map)
        atom.SetAtomMapNum(assigned_map)
    mapped_smiles = Chem.MolToSmiles(
        molecule,
        canonical=False,
        isomericSmiles=True,
        kekuleSmiles=True,
    )
    attachment_maps = tuple(assigned_maps[index] for index in attachment_indices)
    return mapped_smiles, attachment_maps, attachment_atoms, next_atom_map + len(assigned_maps)


def parse_tails(
    document: ReactSeqDocument,
    context: ReactSeqTraversalContext,
    header: ReactSeqHeaderParseResult,
    mapped_product_smiles: str,
) -> ReactSeqTailParseResult:
    """Map ordered tail records to null, charge, and fragment completions."""
    attachment_order = _attachment_order(header, context)
    if len(document.tails) != len(attachment_order):
        raise ReactSeqSyntaxError(
            "ReactSeq tail count does not match its ordered attachment-point count",
            details={
                "tail_count": len(document.tails),
                "attachment_count": len(attachment_order),
            },
        )
    items_by_tail = _tail_items(document)
    product = parse_mapped_molecule(mapped_product_smiles)
    next_atom_map = max(atom_map_index(product)) + 1
    edits: list[AttachFragmentEdit] = []
    atom_state_edits: list[SetExplicitHydrogenEdit] = []
    warnings: list[str] = []

    capacity_by_map: dict[int, float] = {}
    for core_edit in header.core_edits:
        if isinstance(core_edit, BreakBondEdit):
            lost_order = core_edit.expected_order or 1.0
        elif isinstance(core_edit, ChangeBondOrderEdit):
            lost_order = max(0.0, core_edit.from_order - core_edit.to_order)
        else:
            continue
        if lost_order > 0:
            capacity_by_map[core_edit.map_a] = (
                capacity_by_map.get(core_edit.map_a, 0.0) + lost_order
            )
            capacity_by_map[core_edit.map_b] = (
                capacity_by_map.get(core_edit.map_b, 0.0) + lost_order
            )

    for tail_index, items in enumerate(items_by_tail):
        _source_index, product_atom_map = attachment_order[tail_index]
        if not items:
            edits.append(
                AttachFragmentEdit(
                    edit_id=f"reactseq:tail:{tail_index}:null",
                    attachment_kind="null",
                    target_atom_map=product_atom_map,
                    source_range=document.tails[tail_index].source_range,
                    metadata={"attachment_ordinal": tail_index},
                )
            )
            capacity = capacity_by_map.get(product_atom_map, 0.0)
            if capacity > 0 and capacity.is_integer():
                product_index = atom_map_index(product)[product_atom_map]
                atom = product.GetAtomWithIdx(product_index)
                explicit_hydrogens = atom.GetNumExplicitHs()
                atom_state_edits.append(
                    SetExplicitHydrogenEdit(
                        edit_id=f"reactseq:tail:{tail_index}:hydrogen",
                        atom_map=product_atom_map,
                        from_count=explicit_hydrogens,
                        to_count=explicit_hydrogens + int(capacity),
                        source_range=document.tails[tail_index].source_range,
                        metadata={
                            "attachment_ordinal": tail_index,
                            "null_completion_inference": "hydrogen",
                        },
                    )
                )
                warnings.append(
                    "null ReactSeq completion was materialized as explicit hydrogen "
                    "from the lost bond-order capacity"
                )
            elif capacity > 0:
                warnings.append(
                    "fractional aromatic capacity at a null completion was left explicit "
                    "for downstream review"
                )

    all_items = tuple(item for record in items_by_tail for item in record)
    processed_starred: set[str] = set()
    fragment_counter = 0
    for item in all_items:
        _source_index, product_atom_map = attachment_order[item.tail_index]
        if item.value in {"-1", "1", "2"}:
            edits.append(
                AttachFragmentEdit(
                    edit_id=f"reactseq:tail:{item.tail_index}:charge:{item.source_range.start}",
                    attachment_kind="charge_only",
                    target_atom_map=product_atom_map,
                    charge_delta=int(item.value),
                    source_range=item.source_range,
                    metadata={"attachment_ordinal": item.tail_index},
                )
            )
            continue
        if "*" in item.value and not item.value.endswith("*"):
            raise ReactSeqSyntaxError(
                "ReactSeq multi-attachment marker '*' must terminate a tail item",
                source_range=item.source_range,
            )
        starred = item.value.endswith("*")
        raw_fragment = item.value[:-1] if starred else item.value
        if not raw_fragment:
            raise ReactSeqSyntaxError("empty starred leaving group", source_range=item.source_range)
        if starred:
            if raw_fragment in processed_starred:
                continue
            occurrences = tuple(
                candidate for candidate in all_items if candidate.value == f"{raw_fragment}*"
            )
            processed_starred.add(raw_fragment)
        else:
            occurrences = (item,)

        occurrence_maps = tuple(
            attachment_order[candidate.tail_index][1] for candidate in occurrences
        )
        mapped_fragment, fragment_maps, attachment_atoms, next_atom_map = _mapped_fragment(
            raw_fragment,
            next_atom_map=next_atom_map,
        )
        if len(fragment_maps) == 1:
            connection_pairs = tuple((value, fragment_maps[0]) for value in occurrence_maps)
            connection_atoms = tuple(attachment_atoms[0] for _ in occurrence_maps)
            shared = len(occurrence_maps) > 1
        elif starred and len(fragment_maps) == len(occurrence_maps):
            connection_pairs = tuple(zip(occurrence_maps, fragment_maps, strict=True))
            connection_atoms = attachment_atoms
            shared = False
        elif not starred:
            connection_pairs = tuple(
                (product_atom_map, fragment_map) for fragment_map in fragment_maps
            )
            connection_atoms = attachment_atoms
            shared = False
        else:
            raise ReactSeqUnsupportedError(
                "multi-attachment leaving group cannot be paired unambiguously",
                source_range=item.source_range,
                details={
                    "tail_occurrences": len(occurrence_maps),
                    "fragment_attachment_atoms": len(fragment_maps),
                },
            )

        connections = tuple(
            FragmentConnection(
                product_atom_map=pair[0],
                fragment_atom_map=pair[1],
                order=_infer_attachment_order(atom, shared_attachment_atom=shared),
            )
            for pair, atom in zip(connection_pairs, connection_atoms, strict=True)
        )
        edits.append(
            AttachFragmentEdit(
                edit_id=f"reactseq:tail:fragment:{fragment_counter}",
                attachment_kind="fragment",
                fragment_smiles=mapped_fragment,
                connections=connections,
                source_range=item.source_range,
                metadata={
                    "source_fragment": raw_fragment,
                    "starred_multi_attachment": starred,
                    "attachment_ordinals": [value.tail_index for value in occurrences],
                },
            )
        )
        fragment_counter += 1
        if any(connection.order != 1.0 for connection in connections):
            warnings.append(
                "a leaving-group bond order was inferred using the pinned upstream valence rules"
            )

    edits.sort(key=lambda edit: edit.source_range.start if edit.source_range else -1)
    return ReactSeqTailParseResult(
        attachment_edits=tuple(edits),
        atom_state_edits=tuple(atom_state_edits),
        warnings=tuple(dict.fromkeys(warnings)),
    )
