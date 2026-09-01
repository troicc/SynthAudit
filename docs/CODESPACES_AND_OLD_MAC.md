# Codespaces and older macOS

> SynthAudit estimates representation validity, corpus novelty and evidence-based plausibility. It does not establish experimental feasibility, yield, selectivity, safety or scalability.


SynthAudit's reference runtime is Python 3.11 with a recent RDKit build. On an older macOS release,
local wheels or Docker Desktop may be unavailable even when the source code is correct. Do not
weaken the package requirements or downgrade RDKit solely to force an unsupported local install.

## Recommended fallback: GitHub Codespaces

1. Open the repository on GitHub.
2. Select **Code → Codespaces → Create codespace on main**.
3. Wait for the dev container to run its `postCreateCommand`.
4. In the terminal run:

```bash
uv run synthaudit-easy doctor
uv run synthaudit-easy audit \
  --input examples/mapped-reaction.smi \
  --output-dir synthaudit-output
uv run synthaudit ui
```

Port 8501 is forwarded automatically for the Streamlit workspace.

## Linux machine or VPS

```bash
git clone https://github.com/troicc/SynthAudit.git
cd SynthAudit
uv sync --frozen --all-extras --dev
make doctor
make easy-smoke
```

## Older local Mac

Try the normal source setup first. If Python 3.11 or RDKit cannot be installed for the operating
system, use Codespaces or a Linux machine. A failed wheel installation is an environment-support
problem; it should not be “fixed” by silently changing chemistry-library versions without rerunning
the full test and conformance suites.
