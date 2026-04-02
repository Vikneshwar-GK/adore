"""
Test script for Repair Validator (Task 13b-2).

Verifies:
- resolve_dbt_refs replaces all Jinja patterns correctly
- validate_sql_fix passes all 4 checks for identical SQL (old == new)
- validate_sql_fix catches bad SQL and reports it clearly
- Syntax failure short-circuits remaining checks

Usage:
    python3 agents/test_repair_validator.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.repair_validator import resolve_dbt_refs, validate_sql_fix

PASS = "PASS"
FAIL = "FAIL"

PROJECT_ROOT = Path(__file__).parent.parent


def check(label: str, condition: bool) -> bool:
    status = PASS if condition else FAIL
    print(f"  [{status}] {label}")
    return condition


def test_resolve_dbt_refs():
    print("\n--- resolve_dbt_refs ---")

    sql = "SELECT * FROM {{ source('raw', 'weather_sf') }}"
    resolved = resolve_dbt_refs(sql)
    check("source() resolved to raw schema", ".raw.weather_sf" in resolved)
    check("no Jinja tags remain in source()", "{{" not in resolved)

    sql = "SELECT * FROM {{ ref('stg_weather_sf') }}"
    resolved = resolve_dbt_refs(sql)
    check("ref(stg_) resolved to staging schema", ".staging.stg_weather_sf" in resolved)

    sql = "SELECT * FROM {{ ref('int_hourly_weather_transit') }}"
    resolved = resolve_dbt_refs(sql)
    check("ref(int_) resolved to warehouse schema", ".warehouse.int_hourly_weather_transit" in resolved)

    sql = "SELECT * FROM {{ ref('dim_date') }}"
    resolved = resolve_dbt_refs(sql)
    check("ref(dim_) resolved to warehouse schema", ".warehouse.dim_date" in resolved)

    sql = "SELECT * FROM {{ ref('fact_weather_transit_hourly') }}"
    resolved = resolve_dbt_refs(sql)
    check("ref(fact_) resolved to warehouse schema", ".warehouse.fact_weather_transit_hourly" in resolved)

    # Whitespace variations
    sql = "SELECT * FROM {{  source(  'raw' ,  'transit_sf'  )  }}"
    resolved = resolve_dbt_refs(sql)
    check("handles whitespace in source()", ".raw.transit_sf" in resolved)


def test_identical_sql_passes():
    print("\n--- Identical SQL — all checks should pass ---")

    sql_path = PROJECT_ROOT / "dbt" / "models" / "staging" / "stg_weather_sf.sql"
    sql = sql_path.read_text()

    result = validate_sql_fix("weather_sf", sql, sql)

    check("valid is True",                  result["valid"] is True)
    check("has checks dict",                "checks" in result)
    check("has summary string",             isinstance(result["summary"], str))
    check("syntax check passed",            result["checks"]["syntax"]["passed"])
    check("row_count check passed",         result["checks"]["row_count"]["passed"])
    check("null_check passed",              result["checks"]["null_check"]["passed"])
    check("column_check passed",            result["checks"]["column_check"]["passed"])
    check("summary mentions all 4 checks",  "All 4 checks passed" in result["summary"])

    rc = result["checks"]["row_count"]
    check("old_count > 0",                  rc["old_count"] is not None and rc["old_count"] > 0)
    check("diff_pct == 0.0",                rc["diff_pct"] == 0.0)


def test_broken_sql_fails():
    print("\n--- Broken SQL — should fail column and row count checks ---")

    sql_path = PROJECT_ROOT / "dbt" / "models" / "staging" / "stg_weather_sf.sql"
    old_sql = sql_path.read_text()
    broken_sql = "SELECT 1 AS broken_column"

    result = validate_sql_fix("weather_sf", broken_sql, old_sql)

    check("valid is False",                  result["valid"] is False)
    check("summary is non-empty",            len(result["summary"]) > 0)
    # Syntax passes (SELECT 1 is valid SQL), but columns should differ
    check("syntax check passed",             result["checks"]["syntax"]["passed"])
    check("column_check failed",             not result["checks"]["column_check"]["passed"])
    check("missing_columns is non-empty",    len(result["checks"]["column_check"]["missing_columns"]) > 0)


def test_invalid_syntax_short_circuits():
    print("\n--- Invalid syntax — should short-circuit after syntax check ---")

    sql_path = PROJECT_ROOT / "dbt" / "models" / "staging" / "stg_weather_sf.sql"
    old_sql = sql_path.read_text()
    invalid_sql = "THIS IS NOT VALID SQL AT ALL ;;;"

    result = validate_sql_fix("weather_sf", invalid_sql, old_sql)

    check("valid is False",                    result["valid"] is False)
    check("syntax check failed",               not result["checks"]["syntax"]["passed"])
    check("syntax error message non-empty",    bool(result["checks"]["syntax"]["error"]))
    check("row_count not in checks (skipped)", "row_count" not in result["checks"])
    check("summary mentions syntax failure",   "Syntax" in result["summary"] or "syntax" in result["summary"])


def main():
    print("=" * 60)
    print("Repair Validator — Test Suite")
    print("=" * 60)

    test_resolve_dbt_refs()
    test_identical_sql_passes()
    test_broken_sql_fails()
    test_invalid_syntax_short_circuits()

    print("\n" + "=" * 60)
    print("Done.")


if __name__ == "__main__":
    main()
