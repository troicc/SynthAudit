"""Normalize source-verified ReactSeq header operations into typed IR edits."""

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
    ReactSeqTraversalContext,
)
from synthaudit.adapters.reactseq.tokenizer import atom_tokens
from synthaudit.graph.atom_maps import parse_mapped_molecule
from synthaudit.schema.edits import (
    AddBondEdit,
    BreakBondEdit,
    ChangeBondOrderEdit,
    ClearBondStereoEdit,
    ClearTetrahedralStereoEdit,
    SetAtomStateEdit,
    SetBondStereoEdit,
    SetExplicitHydrogenEdit,
    SetTetrahedralStereoEdit,
    SourceRange,
)

_SINGLE_BOND_MARKERS = frozenset("!_;^&{}")
_COMBINED_BOND_MARKERS = (";&", ";{", ";}")
_ALPHA = "\N{GREEK SMALL LETTER ALPHA}"
_BETA = "\N{GREEK SMALL LETTER BETA}"
_GAMMA = "\N{GREEK SMALL LETTER GAMMA}"
_DELTA = "\N{GREEK SMALL LETTER DELTA}"
_ATOM_MARKER_GROUP = frozenset(f"~rs?{_ALPHA}{_BETA}{_GAMMA}{_DELTA}")


@dataclass(frozen=True)
class _AtomMarker:
    reactseq_index: int
    source_range: SourceRange
    direct_hydrogen: bool = False
    tetrahedral: str | None = None
    formal_charge: int | None = None
    add_bond_endpoint: bool = False


@dataclass(frozen=True)
class _BondMarker:
    value: str
    source_range: SourceRange


def _decode_prefix(content: str) -> tuple[str, str]:
    """Decode the exact `~` + `r/s/?` + Greek group order used upstream."""
    position = 0
    if content.startswith("~"):
        position += 1
    if position < len(content) and content[position] in "rs?":
        position += 1
    for group in (
        _ALPHA + _DELTA,
        _BETA + _DELTA,
        _GAMMA + _DELTA,
        _ALPHA,
        _BETA,
        _GAMMA,
        _DELTA,
    ):
        if content.startswith(group, position):
            position += len(group)
            break
    prefix = content[:position]
    if not prefix or any(char not in _ATOM_MARKER_GROUP for char in prefix):
        return "", content
    return prefix, content[position:]


def _atomic_number_from_bracket(text: str) -> int | None:
    molecule = Chem.MolFromSmiles(text, sanitize=False)
    if molecule is None or molecule.GetNumAtoms() != 1:
        return None
    return molecule.GetAtomWithIdx(0).GetAtomicNum()


def _strip_atom_markers(
    document: ReactSeqDocument,
    context: ReactSeqTraversalContext,
    mapped_product: Chem.Mol,
) -> tuple[str, tuple[_AtomMarker, ...]]:
    header = document.header
    tokens = atom_tokens(header, source_offset=document.header_range.start)
    replacements: list[tuple[int, int, str]] = []
    markers: list[_AtomMarker] = []
    for token in tokens:
        if not token.text.startswith("["):
            continue
        content = token.text[1:-1]
        prefix, remainder = _decode_prefix(content)
        if not prefix:
            continue
        cleaned = f"[{remainder}]"
        mapped_index = context.reactseq_atom_index_to_rdkit_index[token.reactseq_atom_index]
        expected_atomic_number = mapped_product.GetAtomWithIdx(mapped_index).GetAtomicNum()
        if _atomic_number_from_bracket(cleaned) != expected_atomic_number:
            # `s` is also aromatic sulfur. Treat it as chemistry when marker stripping
            # would change the element identity, rather than guessing stereo syntax.
            continue
        local_start = token.source_range.start - document.header_range.start
        local_end = token.source_range.end - document.header_range.start
        replacements.append((local_start, local_end, cleaned))
        greek = prefix[-2:] if prefix.endswith(_DELTA) and len(prefix) >= 2 else prefix[-1:]
        formal_charge = {_ALPHA: 1, _BETA: 0, _GAMMA: -1}.get(greek[0] if greek else "")
        tetrahedral = next((value for value in "rs?" if value in prefix), None)
        markers.append(
            _AtomMarker(
                reactseq_index=token.reactseq_atom_index,
                source_range=token.source_range,
                direct_hydrogen="~" in prefix,
                tetrahedral=tetrahedral,
                formal_charge=formal_charge,
                add_bond_endpoint=_DELTA in prefix,
            )
        )

    cleaned_header = header
    for start, end, replacement in reversed(replacements):
        cleaned_header = cleaned_header[:start] + replacement + cleaned_header[end:]
    return cleaned_header, tuple(markers)


def _scan_bond_markers(text: str, *, source_offset: int) -> tuple[_BondMarker, ...]:
    markers: list[_BondMarker] = []
    in_bracket = False
    position = 0
    while position < len(text):
        char = text[position]
        if char == "[":
            in_bracket = True
            position += 1
            continue
        if char == "]":
            in_bracket = False
            position += 1
            continue
        if in_bracket:
            position += 1
            continue
        combined = next(
            (value for value in _COMBINED_BOND_MARKERS if text.startswith(value, position)),
            None,
        )
        if combined is not None:
            markers.append(
                _BondMarker(
                    value=combined,
                    source_range=SourceRange(
                        start=source_offset + position,
                        end=source_offset + position + len(combined),
                    ),
                )
            )
            position += len(combined)
            continue
        if char in _SINGLE_BOND_MARKERS:
            markers.append(
                _BondMarker(
                    value=char,
                    source_range=SourceRange(
                        start=source_offset + position, end=source_offset + position + 1
                    ),
                )
            )
        position += 1
    return tuple(markers)


def _replace_markers(text: str, selected: int) -> str:
    """Replace one marked bond by `~` so RDKit reveals its graph endpoints."""
    replacements = {
        "!": "-",
        "_": "-",
        ";": "=",
        "^": "#",
        "&": "=",
        "{": "=",
        "}": "=",
        ";&": "=",
        ";{": "=",
        ";}": "=",
    }
    output: list[str] = []
    in_bracket = False
    position = 0
    marker_index = 0
    while position < len(text):
        char = text[position]
        if char == "[":
            in_bracket = True
            output.append(char)
            position += 1
            continue
        if char == "]":
            in_bracket = False
            output.append(char)
            position += 1
            continue
        marker: str | None = None
        if not in_bracket:
            marker = next(
                (value for value in _COMBINED_BOND_MARKERS if text.startswith(value, position)),
                None,
            )
            if marker is None and char in _SINGLE_BOND_MARKERS:
                marker = char
        if marker is None:
            output.append(char)
            position += 1
            continue
        output.append("~" if marker_index == selected else replacements[marker])
        marker_index += 1
        position += len(marker)
    return "".join(output)


def _marker_endpoints(cleaned_header: str, marker_count: int) -> tuple[tuple[int, int], ...]:
    endpoints: list[tuple[int, int]] = []
    for selected in range(marker_count):
        molecule = Chem.MolFromSmiles(_replace_markers(cleaned_header, selected), sanitize=False)
        if molecule is None:
            raise ReactSeqSyntaxError("ReactSeq header cannot be parsed after marker normalization")
        unspecified = [
            bond for bond in molecule.GetBonds() if bond.GetBondType() == Chem.BondType.UNSPECIFIED
        ]
        if len(unspecified) != 1:
            raise ReactSeqUnsupportedError(
                "could not uniquely resolve a marked ReactSeq bond",
                details={"marker_index": selected, "candidate_bonds": len(unspecified)},
            )
        bond = unspecified[0]
        endpoints.append((bond.GetBeginAtomIdx() + 1, bond.GetEndAtomIdx() + 1))
    return tuple(endpoints)


def parse_header(
    document: ReactSeqDocument,
    context: ReactSeqTraversalContext,
    mapped_product_smiles: str,
) -> ReactSeqHeaderParseResult:
    """Parse the seven source-verified ReactSeq molecular edit categories."""
    mapped_product = parse_mapped_molecule(mapped_product_smiles)
    cleaned_header, atom_markers = _strip_atom_markers(document, context, mapped_product)
    bond_markers = _scan_bond_markers(document.header, source_offset=document.header_range.start)
    endpoints = _marker_endpoints(cleaned_header, len(bond_markers))

    core_edits: list[AddBondEdit | BreakBondEdit | ChangeBondOrderEdit] = []
    atom_edits: list[SetAtomStateEdit | SetExplicitHydrogenEdit] = []
    stereo_edits: list[
        SetTetrahedralStereoEdit
        | ClearTetrahedralStereoEdit
        | SetBondStereoEdit
        | ClearBondStereoEdit
    ] = []
    attachment_indexes: set[int] = set()

    for marker_index, (marker, (source_a, source_b)) in enumerate(
        zip(bond_markers, endpoints, strict=True)
    ):
        mapped_a = context.reactseq_atom_index_to_rdkit_index[source_a]
        mapped_b = context.reactseq_atom_index_to_rdkit_index[source_b]
        atom_map_a = context.rdkit_index_to_atom_map[mapped_a]
        atom_map_b = context.rdkit_index_to_atom_map[mapped_b]
        bond = mapped_product.GetBondBetweenAtoms(mapped_a, mapped_b)
        if bond is None:
            raise ReactSeqSyntaxError(
                "marked ReactSeq bond does not exist in the supplied product",
                source_range=marker.source_range,
            )
        current_order = bond.GetBondTypeAsDouble()
        core_marker = marker.value[0]
        target_order = {"!": 0.0, "_": 1.0, ";": 2.0, "^": 3.0}.get(core_marker)
        if target_order is not None:
            if target_order == current_order:
                raise ReactSeqSyntaxError(
                    "ReactSeq bond edit is a no-op",
                    source_range=marker.source_range,
                )
            if target_order == 0:
                core_edits.append(
                    BreakBondEdit(
                        edit_id=f"reactseq:bond:{marker_index}",
                        map_a=atom_map_a,
                        map_b=atom_map_b,
                        expected_order=current_order,
                        source_range=marker.source_range,
                        metadata={"reactseq_marker": marker.value},
                    )
                )
            else:
                core_edits.append(
                    ChangeBondOrderEdit(
                        edit_id=f"reactseq:bond:{marker_index}",
                        map_a=atom_map_a,
                        map_b=atom_map_b,
                        from_order=current_order,
                        to_order=target_order,
                        source_range=marker.source_range,
                        metadata={"reactseq_marker": marker.value},
                    )
                )
            if current_order - target_order > 0:
                attachment_indexes.update((source_a, source_b))

        stereo_marker = marker.value[-1]
        if stereo_marker == "&":
            stereo_edits.append(
                ClearBondStereoEdit(
                    edit_id=f"reactseq:bond-stereo:{marker_index}",
                    map_a=atom_map_a,
                    map_b=atom_map_b,
                    source_range=marker.source_range,
                    metadata={"reactseq_marker": marker.value},
                )
            )
        elif stereo_marker in "{}":
            stereo_edits.append(
                SetBondStereoEdit(
                    edit_id=f"reactseq:bond-stereo:{marker_index}",
                    map_a=atom_map_a,
                    map_b=atom_map_b,
                    stereo="E" if stereo_marker == "{" else "Z",
                    source_range=marker.source_range,
                    metadata={"reactseq_marker": marker.value},
                )
            )

    add_bond_markers = [item for item in atom_markers if item.add_bond_endpoint]
    if add_bond_markers:
        if len(add_bond_markers) != 2:
            raise ReactSeqUnsupportedError(
                "ReactSeq add-bond encoding requires exactly two δ-marked atoms",
                details={"marked_atoms": len(add_bond_markers)},
            )
        left, right = add_bond_markers
        map_left = context.stable_map(left.reactseq_index)
        map_right = context.stable_map(right.reactseq_index)
        left_idx = context.reactseq_atom_index_to_rdkit_index[left.reactseq_index]
        right_idx = context.reactseq_atom_index_to_rdkit_index[right.reactseq_index]
        if mapped_product.GetBondBetweenAtoms(left_idx, right_idx) is not None:
            raise ReactSeqSyntaxError(
                "δ-marked ReactSeq add-bond endpoints are already connected",
                source_range=left.source_range,
            )
        core_edits.append(
            AddBondEdit(
                edit_id="reactseq:add-bond:0",
                map_a=map_left,
                map_b=map_right,
                order=1.0,
                source_range=SourceRange(
                    start=min(left.source_range.start, right.source_range.start),
                    end=max(left.source_range.end, right.source_range.end),
                ),
                metadata={"reactseq_marker": _DELTA},
            )
        )

    hydrogen_indexes: set[int] = set()
    for marker_index, atom_marker in enumerate(atom_markers):
        atom_map = context.stable_map(atom_marker.reactseq_index)
        mapped_index = context.reactseq_atom_index_to_rdkit_index[atom_marker.reactseq_index]
        product_atom = mapped_product.GetAtomWithIdx(mapped_index)
        if atom_marker.direct_hydrogen:
            hydrogen_indexes.add(atom_marker.reactseq_index)
            attachment_indexes.add(atom_marker.reactseq_index)
            explicit_hydrogens = product_atom.GetNumExplicitHs()
            if explicit_hydrogens > 0:
                atom_edits.append(
                    SetExplicitHydrogenEdit(
                        edit_id=f"reactseq:explicit-h:{marker_index}",
                        atom_map=atom_map,
                        from_count=explicit_hydrogens,
                        to_count=explicit_hydrogens - 1,
                        source_range=atom_marker.source_range,
                        metadata={"reactseq_atom_marker": "~"},
                    )
                )
        if atom_marker.formal_charge is not None:
            current_charge = product_atom.GetFormalCharge()
            if current_charge == atom_marker.formal_charge:
                raise ReactSeqSyntaxError(
                    "ReactSeq formal-charge edit is a no-op",
                    source_range=atom_marker.source_range,
                )
            atom_edits.append(
                SetAtomStateEdit(
                    edit_id=f"reactseq:charge:{marker_index}",
                    atom_map=atom_map,
                    property="formal_charge",
                    from_value=current_charge,
                    to_value=atom_marker.formal_charge,
                    source_range=atom_marker.source_range,
                    metadata={"reactseq_atom_marker": "formal_charge"},
                )
            )
        if atom_marker.tetrahedral == "?":
            stereo_edits.append(
                ClearTetrahedralStereoEdit(
                    edit_id=f"reactseq:tetrahedral:{marker_index}",
                    atom_map=atom_map,
                    source_range=atom_marker.source_range,
                    metadata={"reactseq_atom_marker": "?"},
                )
            )
        elif atom_marker.tetrahedral in {"r", "s"}:
            stereo_edits.append(
                SetTetrahedralStereoEdit(
                    edit_id=f"reactseq:tetrahedral:{marker_index}",
                    atom_map=atom_map,
                    configuration="R" if atom_marker.tetrahedral == "r" else "S",
                    source_range=atom_marker.source_range,
                    metadata={"reactseq_atom_marker": atom_marker.tetrahedral},
                )
            )

    return ReactSeqHeaderParseResult(
        core_edits=tuple(core_edits),
        atom_state_edits=tuple(atom_edits),
        stereo_edits=tuple(stereo_edits),
        attachment_reactseq_indexes=tuple(sorted(attachment_indexes)),
        hydrogen_attachment_reactseq_indexes=tuple(sorted(hydrogen_indexes)),
    )
