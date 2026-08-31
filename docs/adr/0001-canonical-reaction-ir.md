# ADR 0001: Canonical ReactionIR instead of an upstream format

- Status: Accepted
- Date: 2026-08-31

## Context

ReactSeq is traversal-specific and decomposes centre edits from completion. SynthEx's named ReactionJSON/RouteJSON schemas are not currently published. Mapped reaction SMILES describes endpoint graphs rather than ordered intent. Making any one of these the domain model would leak unstable syntax and erase stage distinctions.

## Decision

Use versioned Pydantic `ReactionIRV1` and `RouteIRV1` models. Every edit references stable atom-map numbers and belongs to core, attachment, atom-state, or stereo stages. Source payload/provenance and source token ranges remain attached without controlling semantics. New versions are additive or explicitly migrated; in-place semantic redefinition is prohibited.

## Consequences

Adapters are explicit, comparison is graph-semantic, and unsupported source fields can be reported. More conversion code is required, but core execution and auditing remain reproducible when upstream formats change.
