# Offline product examples

These authored files exercise the public CLI, Streamlit workspace, and standalone report
renderers without a network service, external corpus, paid provider, or model checkpoint.

Regenerate them with:

```bash
make product-examples
```

Run the CLI workflow with:

```bash
synthaudit execute-reaction --input examples/reaction-ir.json --json /tmp/execution.json
synthaudit audit-reaction --input examples/reaction-ir.json --html /tmp/reaction.html --json /tmp/audit.json
synthaudit audit-route --input examples/route-ir.json --html /tmp/route.html --json /tmp/route-audit.json
```

SynthAudit estimates representation validity, corpus novelty and evidence-based plausibility. It
does not establish experimental feasibility, yield, selectivity, safety or scalability.
