"""
Data Assessor — Task 13b-2

Checks whether corrupted data has already landed in staging during the drift
window (the gap between when the API schema changed and when Schema Guardian
detected it).

No LLM calls, no BigQuery writes — read-only queries via query_bigquery.

Import usage:
    from agents.data_assessor import assess_drift_damage
"""

import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(
    Path(__file__).parent.parent / "gcp-credentials.json"
)

sys.path.insert(0, str(Path(__file__).parent.parent))
from dags.utils.bigquery_client import query_bigquery

logger = logging.getLogger(__name__)

# =============================================================================
# Field mapping — fingerprint path → staging column name
# Based on Task 11 staging models. Verify against actual SQL if in doubt.
# =============================================================================

STAGING_FIELD_MAP = {
    "weather_sf": {
        "hourly.temperature_2m":       "temperature_c",
        "hourly.precipitation":        "precipitation_mm",
        "hourly.wind_speed_10m":       "wind_speed_kmh",
        "hourly.relative_humidity_2m": "humidity_pct",
    },
    "transit_sf": {
        "Entities[].TripUpdate.Trip.TripId":                          "trip_id",
        "Entities[].TripUpdate.Trip.RouteId":                         "route_id",
        "Entities[].TripUpdate.StopTimeUpdates[].StopId":             "stop_id",
        "Entities[].TripUpdate.StopTimeUpdates[].Arrival.Delay":      "arrival_delay_seconds",
        "Entities[].TripUpdate.StopTimeUpdates[].Departure.Delay":    "departure_delay_seconds",
    },
    "incidents_sf": {
        "service_request_id":                  "service_request_id",
        "requested_datetime":                  "requested_datetime",
        "status_description":                  "status",
        "service_name":                        "service_name",
        "agency_responsible":                  "agency_responsible",
        "address":                             "address",
        "lat":                                 "latitude",
        "long":                                "longitude",
        "neighborhoods_sffind_boundaries":     "neighborhood",
    },
}

# Staging table for each source
STAGING_TABLE = {
    "weather_sf":   "stg_weather_sf",
    "transit_sf":   "stg_transit_sf",
    "incidents_sf": "stg_incidents_sf",
}


# =============================================================================
# Row count in drift window
# =============================================================================

def _get_row_count(staging_table: str, since: str) -> int:
    """
    Count rows in a staging view ingested at or after `since`.

    Uses LIMIT 500 for cost control — enough for a representative sample.
    Returns the count of rows in that sample (0–500).

    Args:
        staging_table: e.g. "stg_weather_sf"
        since:         ISO timestamp string — start of the drift window
    """
    sql = f"""
        SELECT COUNT(*) AS row_count
        FROM (
            SELECT ingested_at
            FROM `staging.{staging_table}`
            WHERE ingested_at >= TIMESTAMP('{since}')
            LIMIT 500
        )
    """
    rows = list(query_bigquery(sql))
    return rows[0].row_count


# =============================================================================
# NULL rate per column
# =============================================================================

def _get_null_counts(staging_table: str, columns: list[str], since: str) -> dict:
    """
    Count NULLs in each column for rows ingested at or after `since`.

    Runs a single query with COUNTIF per column — one scan for all columns.
    Uses LIMIT 500 for cost control.

    Args:
        staging_table: e.g. "stg_weather_sf"
        columns:       List of staging column names to check
        since:         ISO timestamp string

    Returns:
        {column_name: null_count}
    """
    if not columns:
        return {}

    count_exprs = ",\n            ".join(
        f"COUNTIF({col} IS NULL) AS null_{col}" for col in columns
    )
    sql = f"""
        SELECT {count_exprs}
        FROM (
            SELECT {", ".join(columns)}, ingested_at
            FROM `staging.{staging_table}`
            WHERE ingested_at >= TIMESTAMP('{since}')
            LIMIT 500
        )
    """
    rows = list(query_bigquery(sql))
    if not rows:
        return {col: 0 for col in columns}

    row = rows[0]
    return {col: getattr(row, f"null_{col}", 0) for col in columns}


# =============================================================================
# Main assessment entry point
# =============================================================================

def assess_drift_damage(source_name: str, changes: list[dict], detection_time: str) -> dict:
    """
    Assess whether corrupted data has already landed in staging.

    For each schema change that maps to a staging column, counts NULLs in
    that column for rows ingested in the last 24 hours (the drift window).
    A high NULL rate on a field_removed or type_changed column is direct
    evidence of data corruption.

    field_added changes are skipped — the staging model just didn't extract
    the new field yet, no existing data is corrupted.

    Args:
        source_name:     e.g. "weather_sf"
        changes:         List of change dicts from compare_schemas()
        detection_time:  ISO timestamp when drift was detected (window start)

    Returns:
        {
            "source_name":           str,
            "staging_table":         str,
            "assessment_window":     str,
            "total_rows_in_window":  int,
            "affected_columns":      list[dict],
            "corrupted_rows_estimate": int,
            "recommendation":        str
        }
    """
    staging_table = STAGING_TABLE.get(source_name)
    if not staging_table:
        logger.warning("No staging table mapping for source: %s", source_name)
        return {
            "source_name":             source_name,
            "staging_table":           None,
            "assessment_window":       "last 24 hours",
            "total_rows_in_window":    0,
            "affected_columns":        [],
            "corrupted_rows_estimate": 0,
            "recommendation":          f"Unknown source '{source_name}' — no assessment possible.",
        }

    field_map = STAGING_FIELD_MAP.get(source_name, {})

    # Only field_removed and type_changed cause corruption — field_added is harmless
    damaging_changes = [
        c for c in changes
        if c["change_type"] in ("field_removed", "type_changed")
    ]

    # Map fingerprint paths to staging column names
    affected_columns_names = []
    for change in damaging_changes:
        col = field_map.get(change["field_path"])
        if col and col not in affected_columns_names:
            affected_columns_names.append(col)

    # Get row count in window
    total_rows = _get_row_count(staging_table, detection_time)

    # No rows in window — nothing to assess
    if total_rows == 0:
        return {
            "source_name":             source_name,
            "staging_table":           staging_table,
            "assessment_window":       f"since {detection_time}",
            "total_rows_in_window":    0,
            "affected_columns":        [],
            "corrupted_rows_estimate": 0,
            "recommendation":          "No rows ingested during drift window. No reprocessing needed.",
        }

    # No mapped columns — change doesn't affect staging
    if not affected_columns_names:
        return {
            "source_name":             source_name,
            "staging_table":           staging_table,
            "assessment_window":       f"since {detection_time}",
            "total_rows_in_window":    total_rows,
            "affected_columns":        [],
            "corrupted_rows_estimate": 0,
            "recommendation":          "No staging columns affected by this schema change. No reprocessing needed.",
        }

    # Check NULL rates on affected columns
    null_counts = _get_null_counts(staging_table, affected_columns_names, detection_time)

    affected_columns = []
    max_corrupted = 0
    for col in affected_columns_names:
        null_count = null_counts.get(col, 0)
        impact_pct = round(null_count / total_rows * 100, 1) if total_rows > 0 else 0.0
        change = next(
            (c for c in damaging_changes if field_map.get(c["field_path"]) == col),
            None,
        )
        affected_columns.append({
            "staging_column": col,
            "change_type":    change["change_type"] if change else "unknown",
            "null_count":     null_count,
            "total_rows":     total_rows,
            "impact_pct":     impact_pct,
        })
        if null_count > max_corrupted:
            max_corrupted = null_count

    if max_corrupted > 0:
        recommendation = (
            f"{max_corrupted} rows (up to {round(max_corrupted / total_rows * 100, 1)}%) "
            f"may have corrupted data. Recommend reprocessing after fix is deployed."
        )
    else:
        recommendation = (
            "Affected columns show no NULLs in the drift window. "
            "Data may be intact — verify after fix is deployed."
        )

    return {
        "source_name":             source_name,
        "staging_table":           staging_table,
        "assessment_window":       f"since {detection_time}",
        "total_rows_in_window":    total_rows,
        "affected_columns":        affected_columns,
        "corrupted_rows_estimate": max_corrupted,
        "recommendation":          recommendation,
    }
