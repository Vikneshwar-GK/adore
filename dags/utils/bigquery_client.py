import logging
import os
from datetime import datetime

from google.cloud import bigquery

logger = logging.getLogger(__name__)

# 1GB cost protection cap — enforced on every query (Task 6 decision)
MAX_BYTES_BILLED = 1_000_000_000


def write_to_bigquery(dataset_id: str, table_id: str, rows: list[dict]) -> None:
    """
    Write rows to a BigQuery table using streaming insert.

    This is the ONLY place in the project that writes to BigQuery.
    All DAGs must use this function — no direct BQ client usage in DAG files.

    Args:
        dataset_id: BigQuery dataset (e.g. "raw")
        table_id:   BigQuery table (e.g. "weather_sf")
        rows:       List of dicts matching the target table schema
    """
    project_id = os.environ["GCP_PROJECT_ID"]
    client = bigquery.Client(project=project_id)
    table_ref = f"{project_id}.{dataset_id}.{table_id}"

    errors = client.insert_rows_json(table_ref, rows)
    if errors:
        raise RuntimeError(
            f"BigQuery streaming insert failed for {table_ref}: {errors}"
        )

    logger.info("Inserted %d row(s) into %s", len(rows), table_ref)


def insert_rows_sql(dataset_id: str, table_id: str, rows: list[dict]) -> None:
    """
    Insert rows via DML INSERT (not streaming insert).

    Unlike write_to_bigquery (streaming insert), rows written here are
    immediately DML-updatable (no streaming buffer delay). Use this for
    any table that requires UPDATE after insert — specifically agent_repairs.

    Handles Python types:
        None      → NULL
        bool      → TRUE / FALSE
        datetime  → TIMESTAMP('...')
        int/float → numeric literal
        str       → single-quoted, single quotes escaped as ''
    """
    if not rows:
        return

    project_id = os.environ["GCP_PROJECT_ID"]
    columns = list(rows[0].keys())

    def _fmt(val):
        if val is None:
            return "NULL"
        if isinstance(val, bool):
            return "TRUE" if val else "FALSE"
        if isinstance(val, datetime):
            return f"TIMESTAMP('{val.isoformat()}')"
        if isinstance(val, (int, float)):
            return str(val)
        # String — escape single quotes (SQL standard: '' not \')
        escaped = str(val).replace("'", "''")
        return f"'{escaped}'"

    value_rows = []
    for row in rows:
        vals = ", ".join(_fmt(row[col]) for col in columns)
        value_rows.append(f"({vals})")

    col_list = ", ".join(columns)
    values_clause = ",\n  ".join(value_rows)
    sql = (
        f"INSERT INTO `{project_id}.{dataset_id}.{table_id}` ({col_list})\n"
        f"VALUES\n  {values_clause}"
    )

    query_bigquery(sql)
    logger.info(
        "DML INSERT %d row(s) into %s.%s.%s", len(rows), project_id, dataset_id, table_id
    )


def dry_run_sql(sql: str) -> dict:
    """
    Validate SQL syntax via a BigQuery dry run — no data scanned, zero cost.

    Submits the query with dry_run=True. BigQuery parses and validates the SQL
    (including table references and column names) without executing it.

    Args:
        sql: The SQL string to validate.

    Returns:
        {
            "valid": True/False,
            "estimated_bytes": int or None,
            "error": None or error message string
        }
    """
    project_id = os.environ["GCP_PROJECT_ID"]
    client = bigquery.Client(project=project_id)
    job_config = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
    try:
        job = client.query(sql, job_config=job_config)
        return {
            "valid": True,
            "estimated_bytes": job.total_bytes_processed,
            "error": None,
        }
    except Exception as e:
        return {
            "valid": False,
            "estimated_bytes": None,
            "error": str(e),
        }


def query_bigquery(sql: str):
    """
    Run a SQL query against BigQuery with a 1GB max bytes billed cap.

    Enforces cost protection on every query — will raise if scan exceeds 1GB.

    Args:
        sql: The SQL query string to execute

    Returns:
        google.cloud.bigquery.table.RowIterator
    """
    project_id = os.environ["GCP_PROJECT_ID"]
    client = bigquery.Client(project=project_id)
    job_config = bigquery.QueryJobConfig(maximum_bytes_billed=MAX_BYTES_BILLED)
    return client.query(sql, job_config=job_config).result()
