import logging
import os

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
