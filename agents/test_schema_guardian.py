"""
Test script for Schema Guardian detection layer (Task 13a).

Run this twice:
  Run 1 — creates baselines for sources with data, skips empty sources
  Run 2 — all sources with data report stable

Usage:
    python3 agents/test_schema_guardian.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.schema_guardian import run_detection
from dags.utils.bigquery_client import query_bigquery

SOURCES = ["weather_sf", "transit_sf", "incidents_sf"]


def verify_bigquery_state():
    """Query agent tables and print a summary of current state."""
    print("\n--- BigQuery state ---")

    # agent_events
    rows = list(query_bigquery("""
        SELECT event_type, source_name, severity, detected_at
        FROM `agents.agent_events`
        ORDER BY detected_at DESC
        LIMIT 20
    """))
    print(f"\nagents.agent_events ({len(rows)} rows):")
    for r in rows:
        print(f"  [{r.severity}] {r.event_type:<30} source={r.source_name}")

    # schema_metadata — count active fields per source
    rows = list(query_bigquery("""
        SELECT source_name, COUNT(*) AS active_fields
        FROM (
            SELECT source_name, field_path, is_active,
                ROW_NUMBER() OVER (
                    PARTITION BY source_name, field_path
                    ORDER BY detected_at DESC
                ) AS rn
            FROM `agents.schema_metadata`
        )
        WHERE rn = 1 AND is_active = TRUE
        GROUP BY source_name
        ORDER BY source_name
    """))
    print(f"\nagents.schema_metadata (active fields per source):")
    for r in rows:
        print(f"  {r.source_name}: {r.active_fields} active fields")

    # schema_change_log
    rows = list(query_bigquery("""
        SELECT COUNT(*) AS total FROM `agents.schema_change_log`
    """))
    print(f"\nagents.schema_change_log: {rows[0].total} rows (expect 0 — no drift yet)")


def main():
    print("=" * 60)
    print("Schema Guardian — Detection Layer Test")
    print("=" * 60)

    results = {}
    for source in SOURCES:
        print(f"\n[{source}]")
        result = run_detection(source)
        results[source] = result
        print(f"  → {result}")

    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    for source, result in results.items():
        status = result["status"]
        extra = ""
        if status == "baseline_created":
            extra = f"  ({result['field_count']} fields)"
        elif status == "stable":
            extra = f"  ({result['field_count']} fields)"
        elif status == "drift_detected":
            extra = f"  ({len(result['changes'])} changes)"
        elif status == "skipped":
            extra = f"  (reason: {result['reason']})"
        print(f"  {source:<20} {status}{extra}")

    verify_bigquery_state()


if __name__ == "__main__":
    main()
