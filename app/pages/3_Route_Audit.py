from __future__ import annotations

import streamlit as st

from synthaudit.reports import render_route_report_html, route_svg
from synthaudit.schema.route_ir import RouteIRV1
from synthaudit.ui.components import configure_page
from synthaudit.ui.workspace import demo_route, route_report_workspace

configure_page(st, title="Route Audit")
st.write(
    "Audit declared strategy, dependency order, intermediate and atom-map continuity, "
    "condition conflicts, and expert-review priority."
)

with st.form("route-audit"):
    payload = st.text_area(
        "RouteIR JSON",
        value=demo_route().model_dump_json(indent=2),
        height=390,
    )
    submitted = st.form_submit_button("Run route audit", use_container_width=True)

if submitted:
    try:
        route = RouteIRV1.model_validate_json(payload)
        report = route_report_workspace(route)
    except Exception as exc:
        st.error(f"Route audit failed explicitly: {type(exc).__name__}: {exc}")
    else:
        st.session_state["route_report"] = report

report = st.session_state.get("route_report")
if report is None:
    st.info("Run the authored two-step software example or paste a strict RouteIR document.")
else:
    audit = report.audit
    columns = st.columns(5)
    columns[0].metric("Status", audit.status.value)
    columns[1].metric("Steps", len(report.route.steps))
    columns[2].metric("Blocking steps", len(audit.structural_blocking_steps))
    columns[3].metric("Min support", audit.minimum_step_support or "unavailable")
    columns[4].metric("Max uncertainty", audit.maximum_uncertainty or "unavailable")

    st.subheader("Strategy and dependency graph")
    st.caption(report.route.strategy_text or "No strategy text was declared.")
    st.html(route_svg(report.route))

    st.subheader("Dependency, continuity, and condition checks")
    st.dataframe(
        [
            {
                "check": item.check_id,
                "status": item.status.value,
                "severity": item.severity.value,
                "message": item.message,
                "deterministic": item.deterministic,
            }
            for item in audit.checks
        ],
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("Per-step alerts")
    st.dataframe(
        [
            {
                "step": item.step_id,
                "structural": item.reaction_audit.structural_audit.status.value,
                "reaction centre": item.reaction_audit.reaction_centre_audit.status.value,
                "completion": item.reaction_audit.completion_audit.status.value,
                "stereo": item.reaction_audit.stereo_audit.status.value,
                "blocking": item.reaction_audit.blocking,
            }
            for item in audit.step_audits
        ],
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("Key-step novelty, conditions, and uncertainty")
    st.write("High-novelty key steps", audit.high_novelty_key_steps or "unavailable")
    st.write("Critical condition conflicts", audit.critical_condition_conflicts or "none declared")
    st.write("Maximum-uncertainty steps", audit.maximum_uncertainty_steps or "unavailable")
    st.caption("Novelty remains independent of plausibility. No route success probability exists.")

    st.subheader("Expert-review queue")
    if audit.expert_review_queue:
        st.dataframe(
            [item.model_dump(mode="json") for item in audit.expert_review_queue],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No review item was produced from the currently declared evidence.")

    html_report = render_route_report_html(report)
    downloads = st.columns(2)
    downloads[0].download_button(
        "Download standalone HTML",
        data=html_report,
        file_name=f"{report.route.route_id}.html",
        mime="text/html",
        use_container_width=True,
    )
    downloads[1].download_button(
        "Download JSON sidecar",
        data=report.model_dump_json(indent=2) + "\n",
        file_name=f"{report.route.route_id}.json",
        mime="application/json",
        use_container_width=True,
    )
