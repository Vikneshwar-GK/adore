"""
Test script for Data Assessor (Task 13b-2).

Verifies:
- assess_drift_damage returns correct structure for all three sources
- Simulated field_removed change produces 0 corrupted rows (clean data)
- Unmapped field path returns empty affected_columns
- field_added change is correctly ignored (no damage)

Usage:
    python3 agents/test_data_assessor.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.data_assessor import assess_drift_damage

PASS = "PASS"
FAIL = "FAIL"

# Use a window that covers all existing staging data
SINCE = "2026-03-01T00:00:00+00:00"


def check(label: str, condition: bool) -> bool:
    status = PASS if condition else FAIL
    print(f"  [{status}] {label}")
    return condition


def test_output_structure():
    print("\n--- Output structure ---")

    result = assess_drift_damage(
        "weather_sf",
        [{"change_type": "field_removed", "field_path": "hourly.temperature_2m",
          "old_value": "array", "new_value": None}],
        SINCE,
    )

    check("has source_name",             "source_name" in result)
    check("has staging_table",           "staging_table" in result)
    check("has assessment_window",       "assessment_window" in result)
    check("has total_rows_in_window",    "total_rows_in_window" in result)
    check("has affected_columns",        "affected_columns" in result)
    check("has corrupted_rows_estimate", "corrupted_rows_estimate" in result)
    check("has recommendation",          "recommendation" in result)
    check("source_name is weather_sf",   result["source_name"] == "weather_sf")
    check("staging_table is stg_weather_sf", result["staging_table"] == "stg_weather_sf")
    check("total_rows_in_window is int", isinstance(result["total_rows_in_window"], int))
    check("total_rows_in_window > 0",    result["total_rows_in_window"] > 0)


def test_clean_data_no_corruption():
    print("\n--- Clean data — no actual drift ---")

    # field_removed for a mapped column — but data is clean so nulls = 0
    result = assess_drift_damage(
        "weather_sf",
        [{"change_type": "field_removed", "field_path": "hourly.temperature_2m",
          "old_value": "array", "new_value": None}],
        SINCE,
    )
    check("weather_sf: temperature_c in affected_columns",
          any(c["staging_column"] == "temperature_c" for c in result["affected_columns"]))
    check("weather_sf: corrupted_rows_estimate == 0", result["corrupted_rows_estimate"] == 0)
    check("weather_sf: null_count == 0",
          all(c["null_count"] == 0 for c in result["affected_columns"]))

    # transit — field_removed for route_id
    result = assess_drift_damage(
        "transit_sf",
        [{"change_type": "field_removed",
          "field_path": "Entities[].TripUpdate.Trip.RouteId",
          "old_value": "string", "new_value": None}],
        SINCE,
    )
    check("transit_sf: route_id in affected_columns",
          any(c["staging_column"] == "route_id" for c in result["affected_columns"]))
    check("transit_sf: corrupted_rows_estimate == 0", result["corrupted_rows_estimate"] == 0)

    # incidents — empty raw data, should return 0 rows
    result = assess_drift_damage(
        "incidents_sf",
        [{"change_type": "field_removed", "field_path": "service_request_id",
          "old_value": "string", "new_value": None}],
        SINCE,
    )
    check("incidents_sf: corrupted_rows_estimate == 0", result["corrupted_rows_estimate"] == 0)
    check("incidents_sf: recommendation is a string", isinstance(result["recommendation"], str))


def test_unmapped_field():
    print("\n--- Unmapped field path ---")

    # A field path that doesn't exist in STAGING_FIELD_MAP
    result = assess_drift_damage(
        "weather_sf",
        [{"change_type": "field_removed", "field_path": "some.unknown.field",
          "old_value": "string", "new_value": None}],
        SINCE,
    )
    check("affected_columns is empty", result["affected_columns"] == [])
    check("corrupted_rows_estimate == 0", result["corrupted_rows_estimate"] == 0)
    check("recommendation mentions no staging columns",
          "No staging columns" in result["recommendation"])


def test_field_added_ignored():
    print("\n--- field_added is ignored (no damage) ---")

    result = assess_drift_damage(
        "weather_sf",
        [{"change_type": "field_added", "field_path": "hourly.soil_temperature",
          "old_value": None, "new_value": "array"}],
        SINCE,
    )
    check("affected_columns is empty (field_added causes no damage)",
          result["affected_columns"] == [])
    check("corrupted_rows_estimate == 0", result["corrupted_rows_estimate"] == 0)


def test_affected_column_structure():
    print("\n--- Affected column dict structure ---")

    result = assess_drift_damage(
        "weather_sf",
        [{"change_type": "type_changed", "field_path": "hourly.precipitation",
          "old_value": "array", "new_value": "string"}],
        SINCE,
    )
    if result["affected_columns"]:
        col = result["affected_columns"][0]
        check("affected col has staging_column", "staging_column" in col)
        check("affected col has change_type",    "change_type" in col)
        check("affected col has null_count",     "null_count" in col)
        check("affected col has total_rows",     "total_rows" in col)
        check("affected col has impact_pct",     "impact_pct" in col)
        check("change_type is type_changed",     col["change_type"] == "type_changed")
    else:
        check("affected_columns populated", False)


def main():
    print("=" * 60)
    print("Data Assessor — Test Suite")
    print("=" * 60)

    test_output_structure()
    test_clean_data_no_corruption()
    test_unmapped_field()
    test_field_added_ignored()
    test_affected_column_structure()

    print("\n" + "=" * 60)
    print("Done.")


if __name__ == "__main__":
    main()
