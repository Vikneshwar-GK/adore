"""
LLM Repair Engine — Task 13b-4

Uses Anthropic's tool-use API to generate context-aware SQL fixes for detected
schema drift. Orchestrates the full repair flow:
    detect → investigate (tool calls) → propose fix → validate → queue for approval

No auto-deployment. Fixes are written to agents.agent_repairs with
status="pending" for human approval via the Agent Monitor dashboard (Task 15).

Import usage:
    from agents.repair_engine import run_repair
"""

import json
import logging
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(
    Path(__file__).parent.parent / "gcp-credentials.json"
)

sys.path.insert(0, str(Path(__file__).parent.parent))
from dags.utils.bigquery_client import query_bigquery, write_to_bigquery, insert_rows_sql
from agents.lineage_analyzer import get_impact_summary
from agents.data_assessor import assess_drift_damage
from agents.repair_validator import validate_sql_fix
from agents.notifications import send_repair_alert

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"
MAX_ITERATIONS = 10
PROJECT_ROOT = Path(__file__).parent.parent


# =============================================================================
# System prompt
# =============================================================================

SYSTEM_PROMPT = """\
You are a data engineering agent that fixes dbt staging models when upstream API schemas change.

You are given a schema drift event. Your job is to:
1. Understand what changed in the source schema
2. Read the current dbt model SQL
3. Assess the impact on downstream models
4. Examine sample raw data to understand the current structure
5. Generate a corrected SQL model that handles the new schema

Rules for SQL generation:
- Preserve ALL existing columns and their names — downstream models depend on them
- If a field was renamed, update the JSON extraction path but keep the output column name
- If a field was removed, handle it gracefully (COALESCE with NULL or a sensible default) — do NOT remove the column
- If a field was added, do NOT add new columns — just fix the breakage. New columns are a product decision.
- If a field type changed, add appropriate CAST or SAFE_CAST
- Preserve the deduplication logic (ROW_NUMBER window function)
- Preserve comments at the top of the file
- Return the COMPLETE SQL model, not a patch or diff

Call the available tools to gather the information you need, then call propose_sql_fix with your corrected SQL.\
"""


# =============================================================================
# Tool definitions (Anthropic tool-use format)
# =============================================================================

TOOLS = [
    {
        "name": "get_current_model_sql",
        "description": "Read the current dbt staging model SQL file for a given source.",
        "input_schema": {
            "type": "object",
            "properties": {
                "source_name": {
                    "type": "string",
                    "description": "The source name, e.g. 'weather_sf'",
                },
            },
            "required": ["source_name"],
        },
    },
    {
        "name": "get_schema_diff",
        "description": (
            "Get the detailed comparison between old and new schemas showing "
            "what fields were added, removed, or changed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "source_name": {
                    "type": "string",
                    "description": "The source name, e.g. 'weather_sf'",
                },
            },
            "required": ["source_name"],
        },
    },
    {
        "name": "get_downstream_impact",
        "description": (
            "Get the list of all downstream dbt models and dashboards affected "
            "by changes to a staging model."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "model_name": {
                    "type": "string",
                    "description": "The dbt model name, e.g. 'stg_weather_sf'",
                },
            },
            "required": ["model_name"],
        },
    },
    {
        "name": "get_sample_raw_data",
        "description": (
            "Fetch a sample of recent raw data from BigQuery to understand "
            "the current API response structure."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "source_name": {
                    "type": "string",
                    "description": "The source name, e.g. 'weather_sf'",
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of recent rows to fetch (max 5)",
                },
            },
            "required": ["source_name"],
        },
    },
    {
        "name": "propose_sql_fix",
        "description": (
            "Submit a proposed SQL fix for the staging model. "
            "This will be validated before being queued for human approval."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "source_name": {
                    "type": "string",
                    "description": "The source name, e.g. 'weather_sf'",
                },
                "new_sql": {
                    "type": "string",
                    "description": "The complete corrected SQL model",
                },
            },
            "required": ["source_name", "new_sql"],
        },
    },
]


# =============================================================================
# Tool implementations
# =============================================================================

def _tool_get_current_model_sql(source_name: str) -> str:
    sql_path = PROJECT_ROOT / "dbt" / "models" / "staging" / f"stg_{source_name}.sql"
    try:
        return sql_path.read_text()
    except FileNotFoundError:
        return f"Error: SQL file not found at {sql_path}"


def _tool_get_schema_diff(source_name: str, changes: list[dict]) -> str:
    """Return the pre-computed schema changes as formatted JSON."""
    return json.dumps({
        "source_name":  source_name,
        "change_count": len(changes),
        "changes":      changes,
    }, indent=2)


def _tool_get_downstream_impact(model_name: str) -> str:
    try:
        summary = get_impact_summary(model_name)
        return json.dumps(summary, indent=2)
    except Exception as e:
        return f"Error fetching downstream impact: {e}"


def _tool_get_sample_raw_data(source_name: str, limit: int = 3) -> str:
    limit = min(limit or 3, 5)
    try:
        rows = list(query_bigquery(
            f"SELECT raw_data FROM `raw.{source_name}` "
            f"ORDER BY ingested_at DESC LIMIT {limit}"
        ))
        samples = [row.raw_data for row in rows]
        return json.dumps(samples, indent=2)
    except Exception as e:
        return f"Error fetching sample raw data: {e}"


def _dispatch_tool(
    name: str,
    inputs: dict,
    changes: list[dict],
) -> str:
    """Route a tool call to its implementation. Returns a string result."""
    try:
        if name == "get_current_model_sql":
            return _tool_get_current_model_sql(inputs["source_name"])
        elif name == "get_schema_diff":
            return _tool_get_schema_diff(inputs["source_name"], changes)
        elif name == "get_downstream_impact":
            return _tool_get_downstream_impact(inputs["model_name"])
        elif name == "get_sample_raw_data":
            return _tool_get_sample_raw_data(
                inputs.get("source_name"), inputs.get("limit", 3)
            )
        elif name == "propose_sql_fix":
            # Terminal tool — just confirm receipt; the caller captures the SQL
            return json.dumps({"status": "received", "message": "Fix submitted for validation."})
        else:
            return f"Unknown tool: {name}"
    except Exception as e:
        logger.error("Tool %s failed: %s", name, e)
        return f"Tool error: {e}"


# =============================================================================
# Internal event logger
# =============================================================================

def _write_event(event_type: str, source_name: str, severity: str, details: dict) -> str:
    """Write one row to agents.agent_events. Returns the new event_id."""
    event_id = str(uuid.uuid4())
    write_to_bigquery("agents", "agent_events", [{
        "event_id":          event_id,
        "agent_name":        "schema_guardian",
        "event_type":        event_type,
        "source_name":       source_name,
        "severity":          severity,
        "details":           json.dumps(details),
        "detected_at":       datetime.now(timezone.utc).isoformat(),
        "resolved_at":       None,
        "notification_sent": None,
    }])
    return event_id


# =============================================================================
# Main repair entry point
# =============================================================================

def run_repair(
    source_name: str,
    event_id: str,
    changes: list[dict],
    old_schema: dict,
    new_schema: dict,
) -> dict:
    """
    Run the full LLM-driven repair flow for a detected schema drift event.

    Uses Anthropic tool-use API to let the LLM investigate the drift and
    propose a SQL fix. Validates the fix, assesses data damage, then writes
    the repair package to agents.agent_repairs with status="pending" for
    human approval.

    Args:
        source_name: e.g. "weather_sf"
        event_id:    UUID from the drift detection event in agent_events
        changes:     List of change dicts from compare_schemas()
        old_schema:  The baseline schema dict before drift
        new_schema:  The new schema dict after drift

    Returns:
        On success:
            {"status": "repair_proposed", "repair_id": str,
             "validation_passed": bool, "notification_sent": bool,
             "impact_summary": dict}
        On failure:
            {"status": "failed", "reason": str}
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY not set — cannot run repair engine")
        return {"status": "failed", "reason": "missing_api_key"}

    client = anthropic.Anthropic(api_key=api_key)

    # -------------------------------------------------------------------------
    # a. Read current staging SQL from disk
    # -------------------------------------------------------------------------
    current_sql = _tool_get_current_model_sql(source_name)
    if current_sql.startswith("Error:"):
        logger.error("Cannot read staging SQL for %s: %s", source_name, current_sql)
        return {"status": "failed", "reason": "sql_file_not_found"}

    # -------------------------------------------------------------------------
    # b. Build initial user message describing the drift event
    # -------------------------------------------------------------------------
    changes_text = "\n".join(
        f"  - {c['change_type']}: {c['field_path']} "
        f"(was: {c['old_value']}, now: {c['new_value']})"
        for c in changes
    )
    initial_message = (
        f"Schema drift has been detected in the '{source_name}' data source.\n\n"
        f"Changes detected ({len(changes)} total):\n{changes_text}\n\n"
        f"Please investigate using the available tools and generate a corrected SQL model."
    )

    # -------------------------------------------------------------------------
    # c. Tool-use loop
    # -------------------------------------------------------------------------
    messages = [{"role": "user", "content": initial_message}]
    proposed_sql = None

    logger.info(
        "Starting repair tool-use loop for %s (event_id=%s)", source_name, event_id
    )

    for iteration in range(MAX_ITERATIONS):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=messages,
            )
        except Exception as e:
            logger.error("Anthropic API error on iteration %d: %s", iteration + 1, e)
            return {"status": "failed", "reason": f"api_error: {e}"}

        logger.info(
            "Iteration %d/%d — stop_reason=%s blocks=%d",
            iteration + 1, MAX_ITERATIONS,
            response.stop_reason, len(response.content),
        )

        # Append assistant turn to conversation history
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            logger.info("LLM finished without calling propose_sql_fix")
            break

        if response.stop_reason != "tool_use":
            logger.warning("Unexpected stop_reason: %s", response.stop_reason)
            break

        # Execute all tool_use blocks in this response
        tool_results = []
        terminal = False

        for block in response.content:
            if block.type != "tool_use":
                continue

            logger.info("Tool call: %s  inputs=%s", block.name, block.input)
            result = _dispatch_tool(block.name, block.input, changes)

            if block.name == "propose_sql_fix":
                proposed_sql = block.input.get("new_sql", "")
                terminal = True
                logger.info("LLM proposed SQL fix (%d chars)", len(proposed_sql))

            tool_results.append({
                "type":        "tool_result",
                "tool_use_id": block.id,
                "content":     result,
            })

        messages.append({"role": "user", "content": tool_results})

        if terminal:
            break
    else:
        logger.error(
            "Max iterations (%d) reached without a proposed fix for %s",
            MAX_ITERATIONS, source_name,
        )

    # -------------------------------------------------------------------------
    # d. No fix proposed
    # -------------------------------------------------------------------------
    if not proposed_sql:
        _write_event("repair_failed", source_name, "error", {
            "event_id": event_id,
            "reason":   "no_fix_proposed",
        })
        return {"status": "failed", "reason": "no_fix_proposed"}

    # -------------------------------------------------------------------------
    # e. Validate the proposed fix
    # -------------------------------------------------------------------------
    logger.info("Validating proposed SQL fix for %s", source_name)
    validation_result = validate_sql_fix(source_name, proposed_sql, current_sql)
    logger.info(
        "Validation: valid=%s — %s",
        validation_result["valid"], validation_result["summary"],
    )

    # -------------------------------------------------------------------------
    # f. Assess data damage in the drift window
    # -------------------------------------------------------------------------
    now_dt = datetime.now(timezone.utc)
    now = now_dt.isoformat()
    damage_assessment = assess_drift_damage(source_name, changes, now)

    # -------------------------------------------------------------------------
    # g. Get downstream impact analysis
    # -------------------------------------------------------------------------
    staging_model = f"stg_{source_name}"
    try:
        impact_summary = get_impact_summary(staging_model)
    except Exception as e:
        logger.warning("Could not get impact summary for %s: %s", staging_model, e)
        impact_summary = {
            "source_model":       staging_model,
            "downstream_models":  [],
            "total_affected":     0,
            "affected_dashboards": [],
            "impact_tree_text":   "",
        }

    # -------------------------------------------------------------------------
    # h. Write repair package to BigQuery via DML INSERT (not streaming insert).
    #    DML INSERT rows are immediately DML-updatable — required for the
    #    UPDATE on approval in deploy_repair(). See Critical Rule in CLAUDE.md.
    # -------------------------------------------------------------------------
    repair_id = str(uuid.uuid4())
    insert_rows_sql("agents", "agent_repairs", [{
        "repair_id":         repair_id,
        "event_id":          event_id,
        "source_name":       source_name,
        "old_sql":           current_sql,
        "new_sql":           proposed_sql,
        "old_schema":        json.dumps(old_schema),
        "new_schema":        json.dumps(new_schema),
        "impact_analysis":   json.dumps(impact_summary),
        "data_assessment":   json.dumps(damage_assessment),
        "validation_result": json.dumps(validation_result),
        "status":            "pending",
        "proposed_at":       now_dt,
        "approved_at":       None,
        "deployed_at":       None,
        "user_notes":        None,
    }])
    logger.info("Repair package written: repair_id=%s", repair_id)

    # -------------------------------------------------------------------------
    # i. Log repair_proposed event
    # -------------------------------------------------------------------------
    _write_event("repair_proposed", source_name, "info", {
        "repair_id":         repair_id,
        "event_id":          event_id,
        "validation_passed": validation_result["valid"],
        "affected_models":   impact_summary.get("total_affected", 0),
    })

    # -------------------------------------------------------------------------
    # j. Send email notification
    # -------------------------------------------------------------------------
    change_summary = "; ".join(
        f"{c['change_type']}: {c['field_path']}" for c in changes
    )
    severity = (
        "critical"
        if any(c["change_type"] in ("field_removed", "type_changed") for c in changes)
        else "warning"
    )
    repair_summary_for_email = {
        "source_name":             source_name,
        "severity":                severity,
        "change_summary":          change_summary,
        "affected_models_count":   impact_summary.get("total_affected", 0),
        "affected_dashboards":     impact_summary.get("affected_dashboards", []),
        "validation_passed":       validation_result["valid"],
        "impact_tree_text":        impact_summary.get("impact_tree_text", ""),
        "repair_id":               repair_id,
        "corrupted_rows_estimate": damage_assessment.get("corrupted_rows_estimate", 0),
    }
    notification_sent = send_repair_alert(repair_summary_for_email)

    if notification_sent:
        _write_event("notification_sent", source_name, "info", {"repair_id": repair_id})

    # -------------------------------------------------------------------------
    # k. Return result
    # -------------------------------------------------------------------------
    return {
        "status":            "repair_proposed",
        "repair_id":         repair_id,
        "validation_passed": validation_result["valid"],
        "notification_sent": notification_sent,
        "impact_summary":    impact_summary,
    }


# =============================================================================
# Deployment (called from dashboard on human approval)
# =============================================================================

def deploy_repair(repair_id: str) -> dict:
    """
    Execute an approved repair: write new SQL to disk and run dbt rebuild.

    Called from the Agent Monitor dashboard when a user clicks "Approve".
    Never called automatically — human approval required.

    Flow:
        fetch repair → backup current SQL → write new SQL → dbt run inside
        container → update BigQuery status → log event

    Args:
        repair_id: UUID from agents.agent_repairs

    Returns:
        {"status": "deployed",  "repair_id": ..., "source_name": ..., "dbt_output": ...}
        {"status": "failed",    "reason": ..., "error": ...}
    """
    # a. Fetch repair from BigQuery
    rows = list(query_bigquery(
        f"SELECT repair_id, source_name, new_sql, status "
        f"FROM `agents.agent_repairs` "
        f"WHERE repair_id = '{repair_id}' LIMIT 1"
    ))
    if not rows:
        return {"status": "failed", "reason": "repair_not_found"}

    repair = rows[0]
    if repair.status != "pending":
        return {"status": "failed", "reason": f"repair is {repair.status}, not pending"}

    source_name = repair.source_name
    new_sql      = repair.new_sql
    sql_path     = PROJECT_ROOT / "dbt" / "models" / "staging" / f"stg_{source_name}.sql"
    backup_path  = sql_path.with_suffix(".sql.backup")

    # b. Backup current staging model
    if sql_path.exists():
        backup_path.write_text(sql_path.read_text())
        logger.info("Backup written to %s", backup_path)
    else:
        logger.warning("Staging SQL not found at %s — proceeding without backup", sql_path)

    # c. Write new SQL to disk
    sql_path.write_text(new_sql)
    logger.info("New SQL written to %s", sql_path)

    # d. Run dbt rebuild inside the Airflow container
    dbt_cmd = (
        f"cd /opt/airflow/dbt && "
        f"dbt run --select stg_{source_name}+"
    )
    try:
        proc = subprocess.run(
            ["docker", "compose", "exec", "-T", "airflow-webserver", "bash", "-c", dbt_cmd],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=300,
        )
        stdout = proc.stdout
        stderr = proc.stderr
        logger.info("dbt run exit code: %d", proc.returncode)

        if proc.returncode != 0:
            logger.error("dbt run failed:\n%s", stderr)
            # Restore from backup
            if backup_path.exists():
                sql_path.write_text(backup_path.read_text())
                backup_path.unlink()
                logger.info("Restored SQL from backup after dbt failure")
            return {"status": "failed", "reason": "dbt_run_failed", "error": stderr}

        # dbt succeeded — remove backup
        if backup_path.exists():
            backup_path.unlink()

    except subprocess.TimeoutExpired:
        if backup_path.exists():
            sql_path.write_text(backup_path.read_text())
            backup_path.unlink()
        return {"status": "failed", "reason": "dbt_run_timeout", "error": "dbt run timed out after 300s"}
    except Exception as e:
        if backup_path.exists():
            sql_path.write_text(backup_path.read_text())
            backup_path.unlink()
        return {"status": "failed", "reason": "subprocess_error", "error": str(e)}

    # e. Update repair status in BigQuery (DML — safe, repair was proposed minutes/hours ago)
    try:
        list(query_bigquery(
            f"UPDATE `agents.agent_repairs` "
            f"SET status = 'approved', "
            f"    approved_at = CURRENT_TIMESTAMP(), "
            f"    deployed_at = CURRENT_TIMESTAMP() "
            f"WHERE repair_id = '{repair_id}'"
        ))
    except Exception as e:
        logger.error("Failed to update repair status in BigQuery: %s", e)

    # f. Log deployment event
    _write_event("repair_deployed", source_name, "info", {
        "repair_id":   repair_id,
        "dbt_command": f"dbt run --select stg_{source_name}+",
    })

    logger.info("Repair deployed successfully: repair_id=%s source=%s", repair_id, source_name)
    return {
        "status":      "deployed",
        "repair_id":   repair_id,
        "source_name": source_name,
        "dbt_output":  stdout,
    }


def reject_repair(repair_id: str, user_notes: str = "") -> dict:
    """
    Reject a pending repair package.

    Updates the repair status to 'rejected' and logs the event.
    Called from the Agent Monitor dashboard when the user clicks "Reject".

    Args:
        repair_id:  UUID from agents.agent_repairs
        user_notes: Optional rejection reason from the user

    Returns:
        {"status": "rejected", "repair_id": repair_id}
        {"status": "failed",   "reason": ...}
    """
    rows = list(query_bigquery(
        f"SELECT source_name, status FROM `agents.agent_repairs` "
        f"WHERE repair_id = '{repair_id}' LIMIT 1"
    ))
    if not rows:
        return {"status": "failed", "reason": "repair_not_found"}
    if rows[0].status != "pending":
        return {"status": "failed", "reason": f"repair is {rows[0].status}, not pending"}

    source_name = rows[0].source_name

    # Escape single quotes in user_notes to prevent SQL injection
    safe_notes = user_notes.replace("'", "\\'")
    try:
        list(query_bigquery(
            f"UPDATE `agents.agent_repairs` "
            f"SET status = 'rejected', user_notes = '{safe_notes}' "
            f"WHERE repair_id = '{repair_id}'"
        ))
    except Exception as e:
        logger.error("Failed to update repair status: %s", e)
        return {"status": "failed", "reason": str(e)}

    _write_event("repair_rejected", source_name, "info", {
        "repair_id":  repair_id,
        "user_notes": user_notes,
    })

    logger.info("Repair rejected: repair_id=%s", repair_id)
    return {"status": "rejected", "repair_id": repair_id}
