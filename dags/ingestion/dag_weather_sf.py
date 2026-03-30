import json
import logging
from datetime import datetime, timedelta, timezone

import requests
from airflow import DAG
from airflow.operators.python import PythonOperator

from utils.bigquery_client import write_to_bigquery

logger = logging.getLogger(__name__)

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_PARAMS = {
    "latitude": 37.7749,
    "longitude": -122.4194,
    "current_weather": True,
    "hourly": "temperature_2m,precipitation,wind_speed_10m,relative_humidity_2m",
}


def ingest_weather():
    response = requests.get(OPEN_METEO_URL, params=OPEN_METEO_PARAMS, timeout=10)

    if response.status_code != 200:
        raise RuntimeError(
            f"Open-Meteo API returned {response.status_code}: {response.text[:500]}"
        )

    row = {
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "source": "open_meteo",
        "raw_data": json.dumps(response.json()),
    }

    write_to_bigquery("raw", "weather_sf", [row])
    logger.info("Weather ingestion complete — ingested_at: %s", row["ingested_at"])


with DAG(
    dag_id="ingest_weather_sf",
    start_date=datetime(2024, 1, 1),
    schedule="*/15 * * * *",
    catchup=False,
    default_args={
        "retries": 2,
        "retry_delay": timedelta(seconds=60),
    },
) as dag:
    PythonOperator(
        task_id="ingest_weather",
        python_callable=ingest_weather,
    )
