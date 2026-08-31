# ReactSeq semantics and integration boundary

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

The adapter has typed normalization hooks for bond break/order change, bond formation, tetrahedral change/clear, formal-charge/explicit-H changes, E/Z changes, and leaving-group attachment/completion. A grammar production is enabled only when covered by an upstream-derived golden fixture. Unknown tokens and conflicting edits produce structured parse errors with source ranges.

Tail completion retains the fragment structure, the fragment atom used for each connection, all synthon attachment maps, null completion, charge-only completion, and multi-attachment identity. New fragment atoms receive deterministic fresh maps after the current maximum.

## Semantic equality

Raw ReactSeq equality is never used as the primary equivalence check. `reaction_ir_semantic_hash` normalizes typed edits and, when execution succeeds, canonical mapped precursor components. Randomized product traversals may therefore normalize to one semantic result. Stereo/symmetry ambiguity prevents a forced equality result.

## Official bridge

The upstream converter is LGPL-2.1 and documents a legacy Python 3.7/RDKit 2019.03.2/Indigo conversion environment. SynthAudit does not copy it. `services/reactseq-legacy` defines a JSONL stdin/stdout boundary with request IDs, exact upstream SHA, tool versions, input, result/error, and no network calls. The bridge is optional and is the only accepted producer of fixtures labelled `official`.

## Model provider

`ReactSeqModelProvider` may return ranked candidates, prompts, token/header/tail/total log probabilities, optional MEO embeddings, and model/checkpoint provenance. Core code works without it. The checked repository contains embedding extraction scripts but no committed trained checkpoint; until an external checkpoint is checksum-pinned and reproduced, embedding/probability fields remain unavailable.

## Unsupported until upstream-conformant fixtures exist

- undocumented delimiter nesting or escaping;
- unresolvable traversal indexes;
- ambiguous symmetric attachment identities;
- cyclic stereo operations without enough neighbour identity;
- any attempt to infer an atom map from a token position;
- a claim that a locally accepted safe-subset string is official-converter compatible.
