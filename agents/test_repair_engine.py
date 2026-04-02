"""
Test script for LLM Repair Engine (Task 13b-4).

Simulates a field rename (temperature_2m → temp_celsius) in the weather_sf
source and verifies the engine produces a valid repair package.

IMPORTANT: This test makes a REAL Anthropic API call and costs real money.
It is gated behind ANTHROPIC_API_KEY — skipped if the key is not set.

Usage:
    python3 agents/test_repair_engine.py
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

PASS = "PASS"
FAIL = "FAIL"

PROJECT_ROOT = Path(__file__).parent.parent


def check(label: str, condition: bool) -> bool:
    status = PASS if condition else FAIL
    print(f"  [{status}] {label}")
    return condition


def test_repair_weather_sf():
    """
    Simulate: temperature_2m renamed to temp_celsius in the Open-Meteo API.

    compare_schemas would produce:
      - field_removed: hourly.temperature_2m
      - field_removed: hourly_units.temperature_2m
      - field_added:   hourly.temp_celsius
      - field_added:   hourly_units.temp_celsius

    The LLM should infer it's a rename (similar names, one in/one out) and:
      - Update the JSON extraction path from "temperature_2m" → "temp_celsius"
      - Keep the output column name as "temperature_c" (unchanged)
    """
    from agents.repair_engine import run_repair

    old_schema = {
        "latitude":                            "number",
        "longitude":                           "number",
        "generationtime_ms":                   "number",
        "utc_offset_seconds":                  "number",
        "timezone":                            "string",
        "timezone_abbreviation":               "string",
        "elevation":                           "number",
        "hourly_units":                        "object",
        "hourly_units.time":                   "string",
        "hourly_units.temperature_2m":         "string",
        "hourly_units.precipitation":          "string",
        "hourly_units.wind_speed_10m":         "string",
        "hourly_units.relative_humidity_2m":   "string",
        "hourly":                              "object",
        "hourly.time":                         "array",
        "hourly.temperature_2m":               "array",
        "hourly.precipitation":                "array",
        "hourly.wind_speed_10m":               "array",
        "hourly.relative_humidity_2m":         "array",
    }

    new_schema = {
        "latitude":                            "number",
        "longitude":                           "number",
        "generationtime_ms":                   "number",
        "utc_offset_seconds":                  "number",
        "timezone":                            "string",
        "timezone_abbreviation":               "string",
        "elevation":                           "number",
        "hourly_units":                        "object",
        "hourly_units.time":                   "string",
        "hourly_units.temp_celsius":           "string",   # renamed
        "hourly_units.precipitation":          "string",
        "hourly_units.wind_speed_10m":         "string",
        "hourly_units.relative_humidity_2m":   "string",
        "hourly":                              "object",
        "hourly.time":                         "array",
        "hourly.temp_celsius":                 "array",    # renamed
        "hourly.precipitation":                "array",
        "hourly.wind_speed_10m":               "array",
        "hourly.relative_humidity_2m":         "array",
    }

    changes = [
        {
            "change_type": "field_removed",
            "field_path":  "hourly.temperature_2m",
            "old_value":   "array",
            "new_value":   None,
        },
        {
            "change_type": "field_removed",
            "field_path":  "hourly_units.temperature_2m",
            "old_value":   "string",
            "new_value":   None,
        },
        {
            "change_type": "field_added",
            "field_path":  "hourly.temp_celsius",
            "old_value":   None,
            "new_value":   "array",
        },
        {
            "change_type": "field_added",
            "field_path":  "hourly_units.temp_celsius",
            "old_value":   None,
            "new_value":   "string",
        },
    ]

    print("\n--- LLM Repair Engine — weather_sf field rename simulation ---")
    print("  Drift: temperature_2m → temp_celsius (field_removed + field_added)")
    print("  Calling run_repair (real Anthropic API call)...\n")

    result = run_repair(
        source_name="weather_sf",
        event_id="test-event-id-0000",
        changes=changes,
        old_schema=old_schema,
        new_schema=new_schema,
    )

    print(f"\n  Result status: {result.get('status')}")

    check("status is repair_proposed",     result.get("status") == "repair_proposed")
    check("repair_id is present",          bool(result.get("repair_id")))
    check("validation_passed key present", "validation_passed" in result)
    check("notification_sent key present", "notification_sent" in result)
    check("impact_summary key present",    "impact_summary" in result)

    if result.get("status") != "repair_proposed":
        print(f"\n  Failure reason: {result.get('reason')}")
        return

    repair_id = result["repair_id"]
    print(f"\n  Repair ID:         {repair_id}")
    print(f"  Validation passed: {result['validation_passed']}")
    print(f"  Notification sent: {result['notification_sent']}")
    print(f"  Affected models:   {result.get('impact_summary', {}).get('total_affected', 'N/A')}")

    # Fetch proposed SQL from BigQuery for manual review
    from dags.utils.bigquery_client import query_bigquery
    rows = list(query_bigquery(
        f"SELECT new_sql, status FROM `agents.agent_repairs` "
        f"WHERE repair_id = '{repair_id}' LIMIT 1"
    ))

    check("repair row written to agent_repairs", len(rows) == 1)

    if rows:
        check("status is pending", rows[0].status == "pending")

        proposed_sql = rows[0].new_sql
        check("proposed SQL is non-empty",               len(proposed_sql) > 0)
        check("proposed SQL references temp_celsius",    "temp_celsius" in proposed_sql)
        check("proposed SQL preserves temperature_c col", "temperature_c" in proposed_sql)

        print("\n--- Proposed SQL (manual review) ---")
        print(proposed_sql)


def main():
    print("=" * 60)
    print("LLM Repair Engine — Test Suite")
    print("=" * 60)

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print(
            "\nSkipping — ANTHROPIC_API_KEY not set in .env.\n"
            "Set it to run this test (makes real Anthropic API calls)."
        )
        return

    test_repair_weather_sf()

    print("\n" + "=" * 60)
    print("Done.")


if __name__ == "__main__":
    main()
