"""
Agent Monitor Dashboard — Task 15a

Displays Schema Guardian activity and lets the user approve or reject
repair packages. Runs locally via:
    streamlit run dashboards/agent_monitor.py

Does NOT run inside Docker — queries BigQuery directly from the host.
"""

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Bootstrap — must happen before any other project imports
# ---------------------------------------------------------------------------
_project_root = Path(__file__).parent.parent
load_dotenv(_project_root / ".env")
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(_project_root / "gcp-credentials.json")
sys.path.insert(0, str(_project_root))

import streamlit as st
from dags.utils.bigquery_client import query_bigquery
from agents.repair_engine import deploy_repair, reject_repair

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(page_title="ADORE Agent Monitor", layout="wide")
st.title("ADORE — Agent Monitor")

# ---------------------------------------------------------------------------
# Sidebar — filters + refresh
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Filters")

    source_filter = st.selectbox(
        "Source",
        ["All", "weather_sf", "transit_sf", "incidents_sf"],
    )

    event_filter = st.selectbox(
        "Event type",
        [
            "All",
            "schema_drift_detected",
            "schema_stable",
            "repair_proposed",
            "repair_deployed",
            "repair_rejected",
            "notification_sent",
            "repair_failed",
        ],
    )

    if st.button("Refresh"):
        st.rerun()


# ---------------------------------------------------------------------------
# Helper: parse JSON fields safely
# ---------------------------------------------------------------------------
def _parse(val, default=None):
    if not val:
        return default
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return default


# ---------------------------------------------------------------------------
# Helper: severity badge color
# ---------------------------------------------------------------------------
def _severity_color(severity: str) -> str:
    return {"critical": "🔴", "warning": "🟡", "info": "🔵", "error": "🔴"}.get(
        (severity or "").lower(), "⚪"
    )


# ---------------------------------------------------------------------------
# SECTION 1 — Pending Approvals
# ---------------------------------------------------------------------------
st.header("Pending Approvals")

pending_rows = list(query_bigquery(
    "SELECT * FROM `agents.agent_repairs` WHERE status = 'pending' ORDER BY proposed_at DESC"
))

if not pending_rows:
    st.info("No repairs awaiting approval.")
else:
    st.warning(f"{len(pending_rows)} repair(s) awaiting approval")

    for repair in pending_rows:
        repair_id   = repair.repair_id
        source_name = repair.source_name
        proposed_at = str(repair.proposed_at)[:19]

        # Pull severity from the linked event if available
        event_rows = list(query_bigquery(
            f"SELECT severity FROM `agents.agent_events` "
            f"WHERE event_id = '{repair.event_id}' LIMIT 1"
        ))
        severity = event_rows[0].severity if event_rows else "critical"

        with st.expander(
            f"{source_name} — Schema Drift ({severity.upper()})  ·  proposed {proposed_at}",
            expanded=True,
        ):
            # 1. Changes
            st.subheader("Changes")
            old_schema = _parse(repair.old_schema, {})
            new_schema = _parse(repair.new_schema, {})
            old_fields = set(old_schema.keys())
            new_fields = set(new_schema.keys())
            removed = old_fields - new_fields
            added   = new_fields - old_fields
            changed = {f for f in old_fields & new_fields if old_schema[f] != new_schema[f]}

            if removed:
                for f in sorted(removed):
                    st.error(f"❌ Removed: `{f}` (was {old_schema[f]})")
            if changed:
                for f in sorted(changed):
                    st.warning(f"⚠️ Type changed: `{f}` ({old_schema[f]} → {new_schema[f]})")
            if added:
                for f in sorted(added):
                    st.success(f"➕ Added: `{f}` ({new_schema[f]})")
            if not (removed or changed or added):
                st.write("(schema diff unavailable)")

            st.divider()

            # 2. Impact Analysis
            st.subheader("Impact Analysis")
            impact = _parse(repair.impact_analysis, {})
            if impact:
                col1, col2 = st.columns(2)
                col1.metric("Downstream models", impact.get("total_affected", 0))
                dashboards = impact.get("affected_dashboards", [])
                col2.metric("Affected dashboards", len(dashboards))
                if dashboards:
                    st.write("Dashboards: " + ", ".join(dashboards))
                tree = impact.get("impact_tree_text", "")
                if tree:
                    st.code(tree, language=None)
            else:
                st.write("(impact analysis unavailable)")

            st.divider()

            # 3. Data Assessment
            st.subheader("Data Assessment")
            assessment = _parse(repair.data_assessment, {})
            if assessment:
                corrupted = assessment.get("corrupted_rows_estimate", 0)
                total     = assessment.get("total_rows_in_window", 0)
                if corrupted > 0:
                    st.error(f"⚠️ ~{corrupted} corrupted rows (of {total} in drift window)")
                else:
                    st.success(f"✅ No corrupted rows detected ({total} rows in drift window)")
                st.write(assessment.get("recommendation", ""))
            else:
                st.write("(data assessment unavailable)")

            st.divider()

            # 4. SQL Diff
            st.subheader("SQL Diff")
            col_old, col_new = st.columns(2)
            with col_old:
                st.caption("Current SQL")
                st.code(repair.old_sql or "(unavailable)", language="sql")
            with col_new:
                st.caption("Proposed Fix")
                st.code(repair.new_sql or "(unavailable)", language="sql")

            st.divider()

            # 5. Validation Results
            st.subheader("Validation Results")
            val = _parse(repair.validation_result, {})
            checks = val.get("checks", {})
            if checks:
                for check_name, check_data in checks.items():
                    passed = check_data.get("passed", False)
                    err    = check_data.get("error") or ""
                    label  = check_name.replace("_", " ").title()
                    if passed:
                        st.success(f"✅ {label}")
                    else:
                        st.error(f"❌ {label}: {err}")
                st.caption(val.get("summary", ""))
            else:
                st.write("(validation results unavailable)")

            st.divider()

            # 6. Action buttons
            st.subheader("Action")

            # Initialise session state for rejection notes toggle
            notes_key = f"show_notes_{repair_id}"
            if notes_key not in st.session_state:
                st.session_state[notes_key] = False

            btn_col1, btn_col2 = st.columns(2)

            with btn_col1:
                if st.button("✅ Approve", key=f"approve_{repair_id}", type="primary"):
                    with st.spinner("Deploying repair — running dbt rebuild inside container..."):
                        result = deploy_repair(repair_id)
                    if result["status"] == "deployed":
                        st.success(f"Repair deployed successfully!")
                        with st.expander("dbt output"):
                            st.code(result.get("dbt_output", ""), language=None)
                        st.rerun()
                    else:
                        st.error(f"Deployment failed: {result.get('reason')} — {result.get('error', '')}")

            with btn_col2:
                if st.button("❌ Reject", key=f"reject_{repair_id}"):
                    st.session_state[notes_key] = True

            if st.session_state.get(notes_key):
                notes = st.text_area(
                    "Rejection reason (optional)",
                    key=f"notes_{repair_id}",
                    placeholder="Describe why this repair is being rejected...",
                )
                if st.button("Confirm rejection", key=f"confirm_reject_{repair_id}"):
                    result = reject_repair(repair_id, notes)
                    if result["status"] == "rejected":
                        st.success("Repair rejected.")
                        st.rerun()
                    else:
                        st.error(f"Rejection failed: {result.get('reason')}")


# ---------------------------------------------------------------------------
# SECTION 2 — Recent Agent Events
# ---------------------------------------------------------------------------
st.header("Recent Agent Events")

event_sql = (
    "SELECT event_id, agent_name, event_type, source_name, severity, "
    "details, detected_at "
    "FROM `agents.agent_events` "
    "WHERE 1=1 "
)
if source_filter != "All":
    event_sql += f"AND source_name = '{source_filter}' "
if event_filter != "All":
    event_sql += f"AND event_type = '{event_filter}' "
event_sql += "ORDER BY detected_at DESC LIMIT 50"

event_rows = list(query_bigquery(event_sql))

if not event_rows:
    st.info("No events found.")
else:
    for ev in event_rows:
        badge  = _severity_color(ev.severity)
        ts     = str(ev.detected_at)[:19]
        etype  = ev.event_type or ""
        source = ev.source_name or ""

        with st.container():
            col_ts, col_badge, col_type, col_source = st.columns([2, 0.5, 3, 2])
            col_ts.caption(ts)
            col_badge.write(badge)
            col_type.write(f"**{etype}**")
            col_source.write(source)

            details = _parse(ev.details, {})
            if details:
                # Show a one-line summary of key fields
                summary_parts = []
                if "changes" in details:
                    summary_parts.append(f"{len(details['changes'])} change(s)")
                if "repair_id" in details:
                    summary_parts.append(f"repair={details['repair_id'][:8]}…")
                if "field_count" in details:
                    summary_parts.append(f"{details['field_count']} fields")
                if "reason" in details:
                    summary_parts.append(f"reason={details['reason']}")
                if summary_parts:
                    st.caption("  " + "  ·  ".join(summary_parts))

        st.divider()


# ---------------------------------------------------------------------------
# SECTION 3 — Repair History
# ---------------------------------------------------------------------------
st.header("Repair History")

history_sql = (
    "SELECT repair_id, source_name, status, proposed_at, approved_at, "
    "validation_result, impact_analysis "
    "FROM `agents.agent_repairs` "
    "WHERE status != 'pending' "
    "ORDER BY proposed_at DESC LIMIT 20"
)
if source_filter != "All":
    history_sql = history_sql.replace(
        "WHERE status != 'pending'",
        f"WHERE status != 'pending' AND source_name = '{source_filter}'"
    )

history_rows = list(query_bigquery(history_sql))

if not history_rows:
    st.info("No completed repairs yet.")
else:
    for r in history_rows:
        status_icon = {"approved": "✅", "rejected": "❌", "failed": "🔴"}.get(r.status, "⚪")
        proposed    = str(r.proposed_at)[:19]
        approved    = str(r.approved_at)[:19] if r.approved_at else "—"

        with st.expander(
            f"{status_icon} {r.source_name}  ·  {r.status.upper()}  ·  proposed {proposed}"
        ):
            st.write(f"**Repair ID:** `{r.repair_id}`")
            st.write(f"**Proposed:** {proposed}  |  **Resolved:** {approved}")

            impact = _parse(r.impact_analysis, {})
            if impact:
                st.write(f"**Affected models:** {impact.get('total_affected', 0)}")
                tree = impact.get("impact_tree_text", "")
                if tree:
                    st.code(tree, language=None)

            val = _parse(r.validation_result, {})
            if val:
                all_passed = val.get("valid", False)
                if all_passed:
                    st.success("Validation passed")
                else:
                    st.error(f"Validation failed: {val.get('summary', '')}")
