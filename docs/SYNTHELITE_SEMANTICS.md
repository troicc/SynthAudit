# Synthelite export semantics

Compatibility target: `schwallergroup/synthelite@45168f8a5846c2fd15a833eddc88bac843b5bbee`.

SynthAudit supports the inspected nested dictionary emitted by Synthelite's
`ReactionTree.to_dict`. This is a version-pinned implementation export, not a stable public
RouteJSON specification.

## Supported tree shape

- The root and material nodes have `type: "mol"`, a `smiles` value, and zero or one reaction
  child for a fixed route.
- Reaction nodes have `type: "reaction"`, metadata, and precursor molecule children.
- Traversal is post-order so every producing step precedes the step that consumes its product.
- Parent step dependencies reference the child steps that produce intermediate precursors.
- Route metadata, language-model metadata, reaction metadata, and unknown source paths are
  preserved.

Every reaction node must contain an explicit atom-mapped reaction in
`metadata.mapped_reaction_smiles`, or in the reaction node's own `smiles` field. SynthAudit
does not invoke an atom mapper and raises `AtomMappingRequired` if this evidence is absent.
The mapped reaction product must be chemically equivalent to its surrounding molecule node.

Leaf molecules matched to mapped precursors become starting materials; products of child
steps become intermediates. Missing tree leaves and mapped precursors absent from the tree are
reported as separate warnings. Synthelite scores are preserved only as upstream metadata and
are not interpreted as calibrated probabilities or route-success probabilities.

## Unsupported cases

The adapter rejects route sets, molecule nodes with multiple alternative reaction children,
unmapped reaction nodes, malformed node types, and source-product disagreement. Unknown
fields are retained in the original payload and listed by path instead of being silently
discarded. Live planner execution, provider credentials, Hugging Face route downloads, and
Synthelite policy-model inference are outside the offline adapter.
