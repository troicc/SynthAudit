# ReactSeq semantics and integration boundary

> SynthAudit estimates representation validity, corpus novelty and evidence-based plausibility. It does not establish experimental feasibility, yield, selectivity, safety or scalability.

Status: source-inspected at `jiachengxiong/ReactSeq@9838a3058e32e1c0ee04b2bab0448104dc293384`. This document describes the subset SynthAudit can defend from upstream source and fixtures; it is not a replacement specification for ReactSeq.

## Two-stage meaning

ReactSeq combines a product traversal and molecular-edit tokens. SynthAudit retains the scientifically important stages:

```text
product --header/core and atom edits--> synthons
synthons --tail/attachment completion--> precursors
```

Upstream `e_smiles.py` represents bond edits internally as four-part records (`a1:a2:old_order:new_order`), detects atom-map-based graph differences, handles hydrogen/charge completion, applies tetrahedral and double-bond stereo edits, and aligns Kekulé forms. The public example uses `!` inside the edited product and `<...>` tail records containing attachment annotations such as `[O:1]`.

## Traversal identity

ReactSeq atom references are tied to a particular explicit-bond/Kekulé product SMILES traversal. They are not atom-map numbers. `ReactSeqTraversalContext` therefore stores:

- original and explicit-bond product SMILES;
- atom-token and header/tail source spans;
- ReactSeq index -> RDKit atom index;
- RDKit atom index -> stable atom-map number;
- ordered attachment points.

Parsing resolves this chain before constructing `ReactionIRV1`. Traversal references that cannot be resolved to unique mapped atoms fail; symmetric ambiguity is `indeterminate`, not guessed.

## Source-verified categories and safe normalization

The adapter implements the symbols observed in pinned `e_smiles.py`, rather than deriving a grammar from the paper alone:

| Public symbol | Pinned upstream meaning | ReactionIR stage |
|---|---|---|
| `!`, `_`, `;`, `^` | bond target order 0, 1, 2, 3 | break/change core edit |
| `&`, `{`, `}` | clear, set E, set Z | bond-stereo edit |
| `;&`, `;{`, `;}` | change to double plus clear/E/Z | separate core and stereo edits |
| bracket prefix `~` | product-atom–hydrogen bond removal / direct attachment capacity | explicit-H edit when present plus ordered completion point |
| bracket prefix `r`, `s`, `?` | precursor R, S, or cleared tetrahedral state | tetrahedral stereo edit |
| bracket prefix `α`, `β`, `γ` | target formal charge +1, 0, -1 | atom-state edit |
| bracket prefix `δ` on exactly two atoms | form one single bond between product atoms | add-bond core edit |

The upstream encoder combines bracket symbols in the order hydrogen, tetrahedral, then charge/add-bond. SynthAudit decodes combined cases without collapsing their execution stages. Unknown, no-op, conflicting, or ambiguously paired tokens raise structured errors with half-open source ranges.

The tail is aligned to the sorted, unique ReactSeq traversal indexes whose bond order decreased, plus `~` direct-attachment sites. Each `<...>` record belongs to one entry in that order. Within a leaving-group SMILES, atom-map annotation `:1` marks the leaving-group attachment atom; it is **not** a product traversal index or stable atom map. `-1`, `1`, and `2` are charge-only completion deltas. Empty records are null completions. A terminal `*` repeats and reunifies one leaving group across tail positions. One annotated fragment atom may connect to several points, while a group with a matching number of annotated atoms is paired in source order. Other arities are rejected as ambiguous.

All leaving-group atoms receive fresh sequential stable maps after the product maximum. Null completion is materialized as explicit hydrogen only when an integral lost bond-order capacity determines the count; this inference is emitted as a warning. The pinned upstream valence path is used for non-single attachment bonds and is likewise disclosed.

The committed golden set uses lines 1–3 of upstream `demo_tgt.txt` and `demo_output_smiles.txt` at the pinned commit. Product atom maps were added locally by deterministic RDKit traversal order and are labelled as such. The three-fixture result is a regression check, not a population-level ReactSeq benchmark.

## Semantic equality

Raw ReactSeq equality is never used as the primary equivalence check. `reaction_ir_semantic_hash` normalizes typed edits and, when execution succeeds, canonical mapped precursor components. Randomized product traversals may therefore normalize to one semantic result. Stereo/symmetry ambiguity prevents a forced equality result.

## Official bridge

The upstream converter is LGPL-2.1 and documents a legacy Python 3.7/RDKit 2019.03.2/Indigo conversion environment. SynthAudit does not copy it. `services/reactseq-legacy` defines a JSONL stdin/stdout boundary with request IDs, exact upstream SHA, tool versions, input, result/error, and no network calls. The bridge is optional and is the only accepted producer of fixtures labelled `official`.

## Model provider

`ReactSeqModelProvider` may return ranked candidates, prompts, token/header/tail/total log probabilities, optional MEO embeddings, and model/checkpoint provenance. Core code works without it. The checked repository contains embedding extraction scripts but no committed trained checkpoint; until an external checkpoint is checksum-pinned and reproduced, embedding/probability fields remain unavailable.

## Unsupported or intentionally conservative

- undocumented delimiter nesting or escaping;
- unresolvable traversal indexes;
- ambiguous symmetric traversal-to-map identities;
- cyclic or pseudo-asymmetric absolute stereo operations without enough neighbour identity;
- multi-attachment fragment arities that cannot be paired uniquely;
- official compatibility labels for locally authored safe-subset strings;
- any attempt to infer an atom map from a token position;
- a claim that a locally accepted safe-subset string is official-converter compatible.
