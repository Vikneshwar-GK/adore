import json
import logging
import os
from datetime import datetime, timedelta, timezone

import requests
from airflow import DAG
from airflow.operators.python import PythonOperator

from utils.bigquery_client import write_to_bigquery

logger = logging.getLogger(__name__)

SF311_URL = "https://data.sfgov.org/resource/vw6y-z8j6.json"
PAGINATION_LIMIT = 50000


def ingest_incidents():
    app_token = os.environ["SF311_APP_TOKEN"]

    # Date format: %Y-%m-%dT%H:%M:%S — NO .000Z suffix, Socrata rejects it
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime(
        "%Y-%m-%dT%H:%M:%S"
    )

    response = requests.get(
        SF311_URL,
        headers={"X-App-Token": app_token},
        params={
            "$where": f"requested_datetime >= '{since}'",
            "$limit": PAGINATION_LIMIT,
            "$order": ":id",
        },
        timeout=30,
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"SF 311 API returned {response.status_code}: {response.text[:500]}"
        )

    records = response.json()

    if len(records) == PAGINATION_LIMIT:
        logger.warning(
            "SF 311 response hit the %d record limit — data may be truncated. "
            "Consider adding offset pagination.",
            PAGINATION_LIMIT,
        )

    row = {
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "source": "sf_311",
        "raw_data": json.dumps(records),
    }

    write_to_bigquery("raw", "incidents_sf", [row])
    logger.info(
        "Incidents ingestion complete — %d records, ingested_at: %s",
        len(records),
        row["ingested_at"],
    )


with DAG(
    dag_id="ingest_incidents_sf",
    start_date=datetime(2024, 1, 1),
    schedule="0 2 * * *",
    catchup=False,
    default_args={
        "retries": 2,
        "retry_delay": timedelta(seconds=300),
    },
) as dag:
    PythonOperator(
        task_id="ingest_incidents",
        python_callable=ingest_incidents,
    )
