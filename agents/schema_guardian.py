"""
Schema Guardian — Detection Layer (Task 13a)

Rule-based agent that fingerprints raw API schemas, detects drift,
and logs events to BigQuery. No LLM calls in this file.

Standalone usage:
    python3 agents/schema_guardian.py
"""

import json
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(
    Path(__file__).parent.parent / "gcp-credentials.json"
)

sys.path.insert(0, str(Path(__file__).parent.parent))
from dags.utils.bigquery_client import query_bigquery, write_to_bigquery

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# =============================================================================
# Schema fingerprinting
# =============================================================================

def _json_type(value) -> str:
    """Return the JSON type name for a Python value."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "unknown"


def _walk(obj, prefix: str, result: dict) -> None:
    """
    Recursively walk a parsed JSON object, recording every field path and type.

    Args:
        obj:    The current node (dict, list, or primitive).
        prefix: Dot-notation path to this node (empty string at root).
        result: Accumulator dict — mutated in place.
    """
    if isinstance(obj, dict):
        for key, value in obj.items():
            path = f"{prefix}.{key}" if prefix else key
            result[path] = _json_type(value)
            # Recurse into objects and arrays
            if isinstance(value, (dict, list)):
                _walk(value, path, result)

    elif isinstance(obj, list):
        if not obj:
            return
        first = obj[0]
        # Only recurse if the first element is an object — primitive arrays
        # (e.g. temperature arrays) are already captured as "array" by the
        # parent dict walk and don't have named sub-fields to track.
        if isinstance(first, dict):
            # Use [] notation to signal "path passes through an array"
            array_prefix = f"{prefix}[]"
            _walk(first, array_prefix, result)


def extract_schema(raw_data_json: str) -> dict:
    """
    Fingerprint a raw JSON string.

    Walks the full structure recursively — including nested objects inside
    arrays — and returns a flat dict of {field_path: field_type}.

    Dot notation for nested objects:  "hourly.temperature_2m"
    Bracket notation for array items: "Entities[].TripUpdate.Trip.RouteId"

    Args:
        raw_data_json: The raw_data string from a BigQuery raw table row.

    Returns:
        dict mapping field path -> JSON type string
        e.g. {"latitude": "number", "hourly.time": "array", ...}
        Returns empty dict if raw_data is an empty array (no records yet).
    """
    parsed = json.loads(raw_data_json)
    result = {}
    # SF 311 raw data is a top-level array — treat the first element as root.
    # If the array is empty (no data yet), return {} so callers can skip
    # baseline creation rather than storing a schema of 0 fields.
    if isinstance(parsed, list):
        parsed = parsed[0] if parsed else {}
    _walk(parsed, "", result)
    return result


# =============================================================================
# Schema storage (BigQuery agents.schema_metadata)
# =============================================================================

def get_stored_schema(source_name: str) -> dict:
    """
    Retrieve the current active schema for a source from schema_metadata.

    Uses a window function to get the latest row per field_path, then
    filters to is_active=TRUE. This handles the append-only design —
    fields that were deactivated (is_active=FALSE) in their latest row
    are excluded, as if they no longer exist.

    Args:
        source_name: e.g. "weather_sf"

    Returns:
        dict of {field_path: field_type} for all currently active fields.
        Returns empty dict if no schema has been stored yet (first run).
    """
    sql = f"""
        SELECT field_path, field_type
        FROM (
            SELECT
                field_path,
                field_type,
                is_active,
                ROW_NUMBER() OVER (
                    PARTITION BY field_path
                    ORDER BY detected_at DESC
                ) AS rn
            FROM `agents.schema_metadata`
            WHERE source_name = '{source_name}'
        )
        WHERE rn = 1
          AND is_active = TRUE
    """
    rows = list(query_bigquery(sql))
    return {row.field_path: row.field_type for row in rows}


def store_schema(source_name: str, schema: dict) -> None:
    """
    Write the current schema to schema_metadata (append-only).

    For every field in the new schema, inserts a row with is_active=TRUE.
    For every field in the previously stored schema that is no longer in
    the new schema, inserts a row with is_active=FALSE (deactivation marker).

    Never updates or deletes existing rows — history is preserved.

    Args:
        source_name: e.g. "weather_sf"
        schema:      dict of {field_path: field_type} from extract_schema()
    """
    now = datetime.now(timezone.utc).isoformat()
    old_schema = get_stored_schema(source_name)
    rows_to_write = []

    # Active fields — everything in the new schema
    for field_path, field_type in schema.items():
        rows_to_write.append({
            "source_name": source_name,
            "field_path":  field_path,
            "field_type":  field_type,
            "detected_at": now,
            "is_active":   True,
        })

    # Deactivation markers — fields present before but now missing
    for field_path, field_type in old_schema.items():
        if field_path not in schema:
            rows_to_write.append({
                "source_name": source_name,
                "field_path":  field_path,
                "field_type":  field_type,
                "detected_at": now,
                "is_active":   False,
            })

    write_to_bigquery("agents", "schema_metadata", rows_to_write)
    logger.info(
        "Stored schema for %s: %d active fields, %d deactivated",
        source_name, len(schema), len(rows_to_write) - len(schema)
    )


# =============================================================================
# Schema comparison
# =============================================================================

def compare_schemas(old_schema: dict, new_schema: dict) -> list[dict]:
    """
    Compare two schema fingerprints and return a list of changes.

    Pure function — no I/O, no side effects.

    Change types:
        field_added   — in new, not in old  (severity: warning)
        field_removed — in old, not in new  (severity: critical)
        type_changed  — in both, type differs (severity: critical)

    Args:
        old_schema: {field_path: field_type} — the stored baseline
        new_schema: {field_path: field_type} — the freshly extracted schema

    Returns:
        List of change dicts, each with keys:
            change_type, field_path, old_value, new_value
        Empty list if schemas are identical.
    """
    changes = []

    old_fields = set(old_schema.keys())
    new_fields = set(new_schema.keys())

    for field_path in new_fields - old_fields:
        changes.append({
            "change_type": "field_added",
            "field_path":  field_path,
            "old_value":   None,
            "new_value":   new_schema[field_path],
        })

    for field_path in old_fields - new_fields:
        changes.append({
            "change_type": "field_removed",
            "field_path":  field_path,
            "old_value":   old_schema[field_path],
            "new_value":   None,
        })

    for field_path in old_fields & new_fields:
        if old_schema[field_path] != new_schema[field_path]:
            changes.append({
                "change_type": "type_changed",
                "field_path":  field_path,
                "old_value":   old_schema[field_path],
                "new_value":   new_schema[field_path],
            })

    return changes


# =============================================================================
# Detection entry point
# =============================================================================

def _log_event(event_type: str, source_name: str, severity: str, details: dict) -> str:
    """Write one row to agents.agent_events. Returns the event_id."""
    event_id = str(uuid.uuid4())
    write_to_bigquery("agents", "agent_events", [{
        "event_id":           event_id,
        "agent_name":         "schema_guardian",
        "event_type":         event_type,
        "source_name":        source_name,
        "severity":           severity,
        "details":            json.dumps(details),
        "detected_at":        datetime.now(timezone.utc).isoformat(),
        "resolved_at":        None,
        "notification_sent":  None,
    }])
    return event_id


def _log_changes(source_name: str, changes: list[dict]) -> None:
    """Write one row per change to agents.schema_change_log."""
    now = datetime.now(timezone.utc).isoformat()
    rows = [
        {
            "change_id":   str(uuid.uuid4()),
            "source_name": source_name,
            "change_type": c["change_type"],
            "field_path":  c["field_path"],
            "old_value":   c["old_value"],
            "new_value":   c["new_value"],
            "detected_at": now,
            "repair_id":   None,
        }
        for c in changes
    ]
    write_to_bigquery("agents", "schema_change_log", rows)


def run_detection(source_name: str) -> dict:
    """
    Main entry point for schema drift detection.

    Fetches the latest raw row, fingerprints it, compares against the stored
    baseline, and logs the result to BigQuery. No LLM calls, no repairs.

    Args:
        source_name: Table name in the raw dataset — "weather_sf",
                     "transit_sf", or "incidents_sf".

    Returns:
        dict with "status" key, one of:
            {"status": "skipped",          "reason": "empty_raw_data"}
            {"status": "baseline_created", "field_count": N}
            {"status": "stable",           "field_count": N}
            {"status": "drift_detected",   "changes": [...]}
    """
    logger.info("Running detection for %s", source_name)

    # 1. Fetch latest raw row
    rows = list(query_bigquery(
        f"SELECT raw_data FROM `raw.{source_name}` "
        f"ORDER BY ingested_at DESC LIMIT 1"
    ))
    if not rows:
        logger.warning("No raw data found for %s — skipping", source_name)
        return {"status": "skipped", "reason": "no_raw_rows"}

    # 2. Fingerprint
    new_schema = extract_schema(rows[0].raw_data)
    if not new_schema:
        logger.warning("Empty schema extracted for %s (empty raw data) — skipping", source_name)
        return {"status": "skipped", "reason": "empty_raw_data"}

    # 3. Get stored baseline
    old_schema = get_stored_schema(source_name)

    # 4. First run — create baseline
    if not old_schema:
        store_schema(source_name, new_schema)
        _log_event(
            event_type="schema_baseline_created",
            source_name=source_name,
            severity="info",
            details={"field_count": len(new_schema), "fields": list(new_schema.keys())},
        )
        logger.info("Baseline created for %s: %d fields", source_name, len(new_schema))
        return {"status": "baseline_created", "field_count": len(new_schema)}

    # 5. Compare
    changes = compare_schemas(old_schema, new_schema)

    # 6. No changes — stable
    if not changes:
        _log_event(
            event_type="schema_stable",
            source_name=source_name,
            severity="info",
            details={"field_count": len(new_schema)},
        )
        logger.info("Schema stable for %s: %d fields", source_name, len(new_schema))
        return {"status": "stable", "field_count": len(new_schema)}

    # 7. Drift detected
    critical_types = {"field_removed", "type_changed"}
    severity = "critical" if any(c["change_type"] in critical_types for c in changes) else "warning"

    _log_changes(source_name, changes)
    event_id = _log_event(
        event_type="schema_drift_detected",
        source_name=source_name,
        severity=severity,
        details={"change_count": len(changes), "changes": changes},
    )
    # Update stored baseline to reflect current reality
    store_schema(source_name, new_schema)

    logger.warning(
        "Drift detected for %s: %d change(s) [%s] event_id=%s",
        source_name, len(changes), severity, event_id,
    )
    return {"status": "drift_detected", "changes": changes, "event_id": event_id}
