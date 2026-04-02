"""
End-to-End Repair Test — Task 13b-5

Manually simulates schema drift in weather_sf to verify the complete
Schema Guardian repair flow without the Chaos Engine:

  inject fake row → run_guardian → drift_detected → LLM repair →
  validation → repair package in agent_repairs → email notification

IMPORTANT — READ BEFORE RUNNING:
- Makes a REAL Anthropic API call (costs money). Gated behind ANTHROPIC_API_KEY.
- Writes a fake row to raw.weather_sf (BigQuery streaming insert).
- Cleanup: a DELETE is issued after the test, but BigQuery streaming inserts
  land in a buffer and may not be immediately deletable (up to ~90 minutes).
  The fake row will disappear eventually. Do NOT run this test twice quickly —
  the second run may detect "stable" if the fake row is still the latest.
- The schema_metadata baseline will reflect the fake drift until the next
  real ingestion re-establishes the correct schema via run_guardian.

Usage:
    python3 agents/test_e2e_repair.py
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(
    Path(__file__).parent.parent / "gcp-credentials.json"
)

PASS = "PASS"
FAIL = "FAIL"


def check(label: str, condition: bool) -> bool:
    status = PASS if condition else FAIL
    print(f"  [{status}] {label}")
    return condition


def run_e2e_test():
    from dags.utils.bigquery_client import query_bigquery, write_to_bigquery
    from agents.schema_guardian import run_guardian

    print("\n--- Step 1: Fetch latest real raw row ---")
    rows = list(query_bigquery(
        "SELECT raw_data, ingested_at FROM `raw.weather_sf` "
        "ORDER BY ingested_at DESC LIMIT 1"
    ))
    if not rows:
        print("  No raw data found for weather_sf — run the ingestion DAG first.")
        return
    print(f"  Got row ingested_at={rows[0].ingested_at}")

    print("\n--- Step 2: Inject fake row with temperature_2m → temp_celsius ---")
    raw = json.loads(rows[0].raw_data)

    # Rename in hourly object
    if "temperature_2m" in raw.get("hourly", {}):
        raw["hourly"]["temp_celsius"] = raw["hourly"].pop("temperature_2m")
    if "temperature_2m" in raw.get("hourly_units", {}):
        raw["hourly_units"]["temp_celsius"] = raw["hourly_units"].pop("temperature_2m")

    fake_ingested_at = datetime.now(timezone.utc).isoformat()
    fake_row = {
        "ingested_at": fake_ingested_at,
        "source":      "open_meteo_e2e_test",
        "raw_data":    json.dumps(raw),
    }
    write_to_bigquery("raw", "weather_sf", [fake_row])
    print(f"  Fake row written: ingested_at={fake_ingested_at}")
    print("  NOTE: BigQuery streaming buffer — cleanup DELETE may take up to ~90 min to take effect.")

    print("\n--- Step 3: Run Schema Guardian (real Anthropic API call) ---")
    result = run_guardian("weather_sf")
    status = result.get("status")
    print(f"  Detection status: {status}")

    check("status is drift_detected",  status == "drift_detected")

    if status != "drift_detected":
        print(f"  Unexpected status: {status}. Is the fake row the latest in raw.weather_sf?")
        _cleanup(fake_ingested_at)
        return

    changes = result.get("changes", [])
    print(f"  Changes detected: {len(changes)}")
    for c in changes:
        print(f"    {c['change_type']}: {c['field_path']}")

    repair = result.get("repair", {})
    repair_status = repair.get("status")
    repair_id = repair.get("repair_id")

    print(f"\n  Repair status:    {repair_status}")
    print(f"  Repair ID:        {repair_id}")
    print(f"  Validation:       {repair.get('validation_passed')}")
    print(f"  Notification:     {repair.get('notification_sent')}")
    affected = repair.get("impact_summary", {}).get("total_affected", "N/A")
    print(f"  Affected models:  {affected}")

    check("repair status is repair_proposed", repair_status == "repair_proposed")
    check("repair_id is non-empty",           bool(repair_id))
    check("validation_passed key present",    "validation_passed" in repair)
    check("impact_summary present",           bool(repair.get("impact_summary")))

    print("\n--- Step 4: Verify repair package in BigQuery ---")
    if repair_id:
        repair_rows = list(query_bigquery(
            f"SELECT status, new_sql, validation_result, impact_analysis, data_assessment "
            f"FROM `agents.agent_repairs` "
            f"WHERE repair_id = '{repair_id}' LIMIT 1"
        ))
        check("repair row exists in agent_repairs", len(repair_rows) == 1)

        if repair_rows:
            r = repair_rows[0]
            check("status is pending",               r.status == "pending")
            check("new_sql is non-empty",            bool(r.new_sql))
            check("validation_result is populated",  bool(r.validation_result))
            check("impact_analysis is populated",    bool(r.impact_analysis))
            check("data_assessment is populated",    bool(r.data_assessment))

            val = json.loads(r.validation_result) if r.validation_result else {}
            check("validation has checks dict",      "checks" in val)
            check("validation has summary",          "summary" in val)

            impact = json.loads(r.impact_analysis) if r.impact_analysis else {}
            check("impact has downstream_models",    "downstream_models" in impact)

            print("\n--- Proposed SQL (manual review) ---")
            print(r.new_sql)

            print("\n--- Validation summary ---")
            print(val.get("summary", "(none)"))

            print("\n--- Impact tree ---")
            print(impact.get("impact_tree_text", "(none)"))

    print("\n--- Step 5: Cleanup ---")
    _cleanup(fake_ingested_at)


def _cleanup(fake_ingested_at: str):
    """
    Attempt to delete the injected fake row from raw.weather_sf.

    BigQuery streaming inserts land in a buffer and may not be immediately
    deletable with DML. If the DELETE returns 0 rows affected, the row will
    clear from the buffer automatically — typically within 90 minutes.
    The schema_metadata baseline will reflect the fake drift until the next
    real ingestion re-runs run_guardian and re-establishes the correct schema.
    """
    from dags.utils.bigquery_client import query_bigquery
    print(f"  Deleting fake row (ingested_at='{fake_ingested_at}') from raw.weather_sf ...")
    try:
        list(query_bigquery(
            f"DELETE FROM `raw.weather_sf` "
            f"WHERE ingested_at = TIMESTAMP('{fake_ingested_at}')"
        ))
        print("  Cleanup DELETE issued. (May not take effect immediately if row is still in streaming buffer.)")
    except Exception as e:
        print(f"  Cleanup failed (non-blocking): {e}")
        print("  The fake row will clear from the streaming buffer automatically.")


def main():
    print("=" * 60)
    print("Schema Guardian — End-to-End Repair Test")
    print("=" * 60)
    print("MANUAL-ONLY: makes real Anthropic API calls and writes to BigQuery.")

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print(
            "\nSkipping — ANTHROPIC_API_KEY not set in .env.\n"
            "Set it to run this test."
        )
        return

    run_e2e_test()

    print("\n" + "=" * 60)
    print("Done.")


if __name__ == "__main__":
    main()
