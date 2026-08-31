# Offline product examples

> SynthAudit estimates representation validity, corpus novelty and evidence-based plausibility. It does not establish experimental feasibility, yield, selectivity, safety or scalability.

These authored files exercise the public CLI, direct-use CLI, Streamlit workspace, and standalone report renderers without a network service, external corpus, paid provider, or model checkpoint.

Files:

- `reaction-ir.json`: canonical single-reaction input;
- `route-ir.json`: canonical two-step route input;
- `mapped-reaction.smi`: small mapped reaction for `synthaudit-easy audit`;
- `reactions.csv`: one-row batch-input example.

Regenerate the canonical product examples with:

```bash
make product-examples
```

Run the beginner-facing direct workflow with:

```bash
synthaudit-easy doctor
synthaudit-easy audit --input examples/mapped-reaction.smi --output-dir synthaudit-output
synthaudit-easy batch --input examples/reactions.csv --output-dir synthaudit-batch-output
```

Run the canonical CLI workflow with:

```bash
synthaudit execute-reaction --input examples/reaction-ir.json --json /tmp/execution.json
synthaudit audit-reaction --input examples/reaction-ir.json --html /tmp/reaction.html --json /tmp/audit.json
synthaudit audit-route --input examples/route-ir.json --html /tmp/route.html --json /tmp/route-audit.json
```

The files are software demonstrations, not evidence that any laboratory reaction will succeed.
