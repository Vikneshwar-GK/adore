"""
Repair Validator — Task 13b-2

Validates a proposed SQL fix before it enters the approval queue.
Runs four checks: syntax, row count, NULL rates, column names.

No LLM calls — deterministic validation only.

Import usage:
    from agents.repair_validator import validate_sql_fix
"""

import logging
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(
    Path(__file__).parent.parent / "gcp-credentials.json"
)

sys.path.insert(0, str(Path(__file__).parent.parent))
from dags.utils.bigquery_client import dry_run_sql, query_bigquery

logger = logging.getLogger(__name__)

# Row count difference threshold — flag if new SQL differs by more than this
ROW_COUNT_DIFF_THRESHOLD_PCT = 10.0

# Rows to sample for row count / NULL / column checks
SAMPLE_LIMIT = 500


# =============================================================================
# Jinja ref resolver
# =============================================================================

def resolve_dbt_refs(sql: str, project_id: str = None) -> str:
    """
    Replace dbt Jinja tags with real BigQuery table references.

    Handles the three patterns used in this project:
        {{ source('raw', 'X') }}   →  `project`.raw.X
        {{ ref('stg_X') }}         →  `project`.staging.stg_X
        {{ ref('X') }}             →  `project`.warehouse.X   (int_, dim_, fact_)

    Uses regex to handle whitespace variations in Jinja tags.
    Not a general-purpose Jinja parser — only handles patterns in this project.

    Args:
        sql:        SQL string containing dbt Jinja tags.
        project_id: GCP project ID. Defaults to GCP_PROJECT_ID env var.

    Returns:
        SQL string with all Jinja tags replaced by real table references.
    """
    pid = project_id or os.environ["GCP_PROJECT_ID"]

    # {{ source('raw', 'table_name') }}
    sql = re.sub(
        r"\{\{\s*source\(\s*'raw'\s*,\s*'(\w+)'\s*\)\s*\}\}",
        lambda m: f"`{pid}`.raw.{m.group(1)}",
        sql,
    )

    # {{ ref('stg_X') }} → staging schema
    sql = re.sub(
        r"\{\{\s*ref\(\s*'(stg_\w+)'\s*\)\s*\}\}",
        lambda m: f"`{pid}`.staging.{m.group(1)}",
        sql,
    )

    # {{ ref('X') }} for everything else (int_, dim_, fact_) → warehouse schema
    sql = re.sub(
        r"\{\{\s*ref\(\s*'(\w+)'\s*\)\s*\}\}",
        lambda m: f"`{pid}`.warehouse.{m.group(1)}",
        sql,
    )

    return sql


# =============================================================================
# Individual checks
# =============================================================================

def _check_syntax(sql: str) -> dict:
    """Dry run — zero cost syntax and table reference validation."""
    result = dry_run_sql(sql)
    return {
        "passed":           result["valid"],
        "estimated_bytes":  result["estimated_bytes"],
        "error":            result["error"],
    }


def _run_sample(sql: str) -> list:
    """Execute SQL with LIMIT appended and return rows."""
    # Append LIMIT inside a subquery so it works regardless of existing clauses
    wrapped = f"SELECT * FROM ({sql}) _sample LIMIT {SAMPLE_LIMIT}"
    return list(query_bigquery(wrapped))


def _check_row_count(old_sql: str, new_sql: str) -> dict:
    """Compare row counts between old and new SQL on a LIMIT 500 sample."""
    try:
        old_rows = _run_sample(old_sql)
        new_rows = _run_sample(new_sql)
        old_count = len(old_rows)
        new_count = len(new_rows)

        if old_count == 0:
            diff_pct = 0.0
        else:
            diff_pct = round(abs(new_count - old_count) / old_count * 100, 1)

        passed = diff_pct <= ROW_COUNT_DIFF_THRESHOLD_PCT
        return {
            "passed":    passed,
            "old_count": old_count,
            "new_count": new_count,
            "diff_pct":  diff_pct,
            "error":     None if passed else f"Row count diff {diff_pct}% exceeds {ROW_COUNT_DIFF_THRESHOLD_PCT}% threshold",
        }
    except Exception as e:
        return {"passed": False, "old_count": None, "new_count": None, "diff_pct": None, "error": str(e)}


def _check_nulls(old_sql: str, new_sql: str) -> dict:
    """
    Compare NULL rates per column between old and new SQL.

    Flags columns where the new SQL produces more NULLs than the old SQL.
    A significant increase in NULLs on a key column signals the fix is broken.
    """
    try:
        old_rows = _run_sample(old_sql)
        new_rows = _run_sample(new_sql)

        if not old_rows or not new_rows:
            return {"passed": True, "columns_with_new_nulls": [], "error": None}

        # Get column names from the first row of each result
        old_cols = set(old_rows[0].keys())
        new_cols = set(new_rows[0].keys())
        common_cols = old_cols & new_cols

        def null_rate(rows, col):
            if not rows:
                return 0.0
            nulls = sum(1 for r in rows if getattr(r, col, None) is None)
            return nulls / len(rows)

        columns_with_new_nulls = []
        for col in common_cols:
            old_rate = null_rate(old_rows, col)
            new_rate = null_rate(new_rows, col)
            # Flag if new SQL has meaningfully more NULLs (> 5 percentage points)
            if new_rate - old_rate > 0.05:
                columns_with_new_nulls.append({
                    "column":        col,
                    "old_null_rate": round(old_rate * 100, 1),
                    "new_null_rate": round(new_rate * 100, 1),
                })

        passed = len(columns_with_new_nulls) == 0
        return {
            "passed":                 passed,
            "columns_with_new_nulls": columns_with_new_nulls,
            "error":                  None if passed else f"{len(columns_with_new_nulls)} column(s) have significantly more NULLs",
        }
    except Exception as e:
        return {"passed": False, "columns_with_new_nulls": [], "error": str(e)}


def _check_columns(old_sql: str, new_sql: str) -> dict:
    """Verify new SQL produces the same column names as old SQL."""
    try:
        old_rows = _run_sample(old_sql)
        new_rows = _run_sample(new_sql)

        old_cols = set(old_rows[0].keys()) if old_rows else set()
        new_cols = set(new_rows[0].keys()) if new_rows else set()

        missing = sorted(old_cols - new_cols)
        extra   = sorted(new_cols - old_cols)
        passed  = len(missing) == 0

        error = None
        if missing:
            error = f"Missing columns: {missing}"
        return {
            "passed":          passed,
            "missing_columns": missing,
            "extra_columns":   extra,
            "error":           error,
        }
    except Exception as e:
        return {"passed": False, "missing_columns": [], "extra_columns": [], "error": str(e)}


# =============================================================================
# Main entry point
# =============================================================================

def validate_sql_fix(source_name: str, new_sql: str, old_sql: str) -> dict:
    """
    Run four validation checks on a proposed SQL fix.

    Checks run in order — syntax failure short-circuits the rest since
    executing invalid SQL would raise an exception.

    Args:
        source_name: e.g. "weather_sf" (used for logging only)
        new_sql:     Proposed dbt model SQL (may contain Jinja tags)
        old_sql:     Current dbt model SQL (may contain Jinja tags)

    Returns:
        {
            "valid": bool,
            "checks": {
                "syntax":       {passed, estimated_bytes, error},
                "row_count":    {passed, old_count, new_count, diff_pct, error},
                "null_check":   {passed, columns_with_new_nulls, error},
                "column_check": {passed, missing_columns, extra_columns, error}
            },
            "summary": str
        }
    """
    logger.info("Validating SQL fix for %s", source_name)

    # Resolve Jinja tags so BigQuery can execute the SQL
    resolved_new = resolve_dbt_refs(new_sql)
    resolved_old = resolve_dbt_refs(old_sql)

    checks = {}

    # 1 — Syntax (dry run, zero cost)
    checks["syntax"] = _check_syntax(resolved_new)
    if not checks["syntax"]["passed"]:
        summary = f"Syntax check failed: {checks['syntax']['error']}"
        logger.warning("Validation failed for %s: %s", source_name, summary)
        return {
            "valid":   False,
            "checks":  checks,
            "summary": summary,
        }

    # 2 — Row count
    checks["row_count"] = _check_row_count(resolved_old, resolved_new)

    # 3 — NULL check
    checks["null_check"] = _check_nulls(resolved_old, resolved_new)

    # 4 — Column check
    checks["column_check"] = _check_columns(resolved_old, resolved_new)

    all_passed = all(c["passed"] for c in checks.values())

    if all_passed:
        rc = checks["row_count"]
        summary = (
            f"All 4 checks passed. "
            f"Row count diff: {rc['diff_pct']}% (within {ROW_COUNT_DIFF_THRESHOLD_PCT}% threshold)."
        )
    else:
        failures = [name for name, c in checks.items() if not c["passed"]]
        errors   = [c["error"] for c in checks.values() if not c["passed"] and c.get("error")]
        summary  = f"Validation failed ({', '.join(failures)}): {'; '.join(errors)}"

    logger.info("Validation result for %s: valid=%s — %s", source_name, all_passed, summary)
    return {
        "valid":   all_passed,
        "checks":  checks,
        "summary": summary,
    }
