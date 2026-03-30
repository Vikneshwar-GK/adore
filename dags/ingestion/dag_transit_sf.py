import json
import logging
import os
from datetime import datetime, timedelta, timezone

import requests
from airflow import DAG
from airflow.operators.python import PythonOperator

from utils.bigquery_client import write_to_bigquery

logger = logging.getLogger(__name__)

TRANSIT_URL = "http://api.511.org/transit/TripUpdates"


def ingest_transit():
    api_key = os.environ["TRANSIT_511_API_KEY"]

    response = requests.get(
        TRANSIT_URL,
        params={"api_key": api_key, "agency": "SF", "format": "json"},
        timeout=15,
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"511.org API returned {response.status_code}: {response.text[:500]}"
        )

    # Response has a UTF-8 BOM — must decode with utf-8-sig, NOT response.json()
    decoded = response.content.decode("utf-8-sig")
    json.loads(decoded)  # Validate it's parseable JSON before storing

    row = {
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "source": "511_transit",
        "raw_data": decoded,
    }

    write_to_bigquery("raw", "transit_sf", [row])
    logger.info("Transit ingestion complete — ingested_at: %s", row["ingested_at"])


with DAG(
    dag_id="ingest_transit_sf",
    start_date=datetime(2024, 1, 1),
    schedule="*/15 * * * *",
    catchup=False,
    default_args={
        "retries": 2,
        "retry_delay": timedelta(seconds=60),
    },
) as dag:
    PythonOperator(
        task_id="ingest_transit",
        python_callable=ingest_transit,
    )
