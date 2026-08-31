# ReactSeq legacy bridge

This directory is a process boundary, not a vendored ReactSeq implementation.
It runs the official converter only when the operator supplies a checkout at
`jiachengxiong/ReactSeq@9838a3058e32e1c0ee04b2bab0448104dc293384` and its
documented legacy dependencies (Python 3.7, RDKit 2019.03.2 and `epam.indigo`).

The worker reads one `synthaudit.reactseq-bridge/1` JSON object per stdin line
and writes exactly one response per stdout line. Supported operations are
`convert_reaction`, `reconstruct_precursors`, and `inspect_runtime`. It never
uses the network. The caller verifies request ID and exact upstream commit.

Example after preparing the isolated environment:

```console
REACTSEQ_SOURCE=/opt/ReactSeq \
REACTSEQ_UPSTREAM_COMMIT=9838a3058e32e1c0ee04b2bab0448104dc293384 \
python server.py
```

The core SynthAudit environment does not import this service or downgrade its
Python/RDKit versions. Outputs may be labelled `official` only after the worker
reports the pinned commit and the conformance request succeeds.
