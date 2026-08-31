# Stage-specific audit methodology

> SynthAudit estimates representation validity, corpus novelty and evidence-based plausibility. It does not establish experimental feasibility, yield, selectivity, safety or scalability.

SynthAudit executes a canonical `ReactionIRV1` once and audits four evidence groups
independently. It does not collapse the groups into a feasibility score.

## Result protocol

Every check returns `check_id`, category, severity, status, message, affected atom maps,
machine-readable evidence, references, and a deterministic flag. Status values distinguish
`pass`, `fail`, `warning`, `indeterminate`, `unavailable`, and `unsupported`. A missing input or
provider is never converted to a pass.

`ReactionAuditResultV1` retains the complete staged execution result plus separate structural,
reaction-centre, completion, and stereo groups. A report is blocking only when a blocking-
severity check fails. Structural validity cannot exceed the underlying executor's sanitation
result.

## Structural audit

The structural stage checks complete and unique maps, ordered edit references, RDKit valence
and sanitation, formal charges, aromatic/Kekule consistency, connectivity, empty and
single-atom fragments, atom conservation, declared-versus-observed graph changes, operation
no-ops, and edit complexity. The default edit-count review threshold is 12 and is emitted with
the result. Per-atom absolute formal charge above 3 is a review warning, not a claim of chemical
impossibility. Single-heavy-atom precursor records are retained and flagged rather than
deleted.

## Reaction-centre audit

The reaction-centre stage checks product map references, the bond state at each sequential
operation, transactional core execution, exact explanation of the core graph diff, ring-count
change, real graph changes, symmetry-equivalent alternative sites, and reconstruction from an
expected mapped precursor set. Symmetric site identity is a warning or indeterminate outcome;
atom-map order is not used to force a choice.

## Synthon-completion audit

The completion stage validates attachment-point existence, fragment parsing, unique explicit
connection pairs, multi-attachment identity, transactional completion, post-completion
sanitation, expected precursor reconstruction with stereo intentionally deferred, external-
atom attribution, required-fragment retention, and atom accounting. A small transparent
element/size rule creates review warnings. Corpus-based leaving-group novelty is reported as
`unavailable` until a declared reference index is supplied.

## Stereo audit

The stereo stage checks target topology, CIP assignments before and after tetrahedral edits,
E/Z bond and neighbour references, unrequested stereo erasure, newly assigned stereocentres,
symmetric/pseudo-asymmetric targets, cyclic stereo paths, and transactional stereo execution.
CW/CCW is treated as local chiral-tag intent; R/S is checked against CIP when meaningful.
Cases without a stable CIP interpretation remain indeterminate.

## Standalone report

`render_reaction_audit_html` produces one offline document with embedded CSS and RDKit SVG for
the product, synthons, completed precursors, and final stereo result. Every check and its
evidence remain visible. `write_reaction_audit_report` writes the HTML plus a JSON sidecar using
the versioned result schema. Neither artifact needs a server or external asset.
