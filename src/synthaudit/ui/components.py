"""Thin Streamlit presentation helpers; all chemistry stays in package workflows."""

from __future__ import annotations

from typing import Any

from synthaudit import SCIENTIFIC_NOTICE
from synthaudit.schema.results import StageAuditResultV1

_THEME = """
<style>
:root { --sa-primary:#1e3a5f; --sa-secondary:#60a5fa; --sa-accent:#22c55e;
  --sa-surface:#111827; --sa-border:#334155; --sa-muted:#cbd5e1; }
[data-testid="stAppViewContainer"] { background:linear-gradient(145deg,#08111f 0%,#0f172a 55%,#111827 100%); }
[data-testid="stHeader"] { background:rgba(8,17,31,.88); }
.sa-kicker { color:#93c5fd; font:600 .78rem/1.4 ui-monospace,SFMono-Regular,Menlo,monospace;
  letter-spacing:.09em; text-transform:uppercase; }
.sa-notice { border:1px solid #60a5fa; border-left:5px solid #60a5fa; border-radius:8px;
  background:#0b2542; color:#f8fafc; padding:14px 16px; margin:12px 0 22px; font-weight:600; }
.sa-card { border:1px solid var(--sa-border); border-radius:12px; background:rgba(17,24,39,.82);
  padding:16px; min-height:112px; }
.sa-card strong { color:#93c5fd; display:block; font-size:.78rem; text-transform:uppercase;
  letter-spacing:.06em; margin-bottom:8px; }
.sa-empty { border:1px dashed #64748b; border-radius:8px; color:#cbd5e1; padding:14px; }
button, [role="button"] { min-height:44px; }
:focus-visible { outline:3px solid #93c5fd!important; outline-offset:2px!important; }
@media (prefers-reduced-motion:reduce) { *,*::before,*::after { scroll-behavior:auto!important;
  animation-duration:.01ms!important; animation-iteration-count:1!important; transition-duration:.01ms!important; } }
@media (max-width:600px) { .block-container { padding-left:1rem!important; padding-right:1rem!important; } }
</style>
"""


def configure_page(st: Any, *, title: str) -> None:
    st.set_page_config(page_title=f"{title} · SynthAudit", layout="wide")
    st.markdown(_THEME, unsafe_allow_html=True)
    st.markdown(
        '<div class="sa-kicker">SynthAudit · evidence workspace</div>', unsafe_allow_html=True
    )
    st.title(title)
    st.markdown(f'<div class="sa-notice">{SCIENTIFIC_NOTICE}</div>', unsafe_allow_html=True)


def render_stage(st: Any, stage: StageAuditResultV1, *, title: str) -> None:
    st.subheader(title)
    st.caption(f"Status: {stage.status.value}")
    st.dataframe(
        [
            {
                "check": item.check_id,
                "status": item.status.value,
                "severity": item.severity.value,
                "message": item.message,
                "atom maps": ", ".join(map(str, item.affected_atom_maps)) or "—",
                "deterministic": item.deterministic,
            }
            for item in stage.checks
        ],
        use_container_width=True,
        hide_index=True,
    )
