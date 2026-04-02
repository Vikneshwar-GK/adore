"""
Schema Guardian DAG — Task 13b-5

Triggered (not scheduled) by each ingestion DAG after a successful run.
Runs run_guardian() for the given source: detects drift, and if drift is
found, triggers the LLM repair engine to generate and queue a fix.

Trigger pattern (from ingestion DAGs):
    TriggerDagRunOperator(
        trigger_dag_id="agent_schema_guardian",
        conf={"source_name": "weather_sf"},
        wait_for_completion=False,
    )
"""

import logging

from airflow import DAG
from airflow.exceptions import AirflowException
from airflow.operators.python import PythonOperator
from datetime import datetime

logger = logging.getLogger(__name__)


def run_schema_guardian(**context):
    """
    Call run_guardian for the source_name provided in dag_run.conf.

    Exits normally on stable/baseline_created/skipped.
    Logs repair_id on drift_detected + repair_proposed.
    Raises AirflowException on failure so Airflow marks the task failed.
    """
    source_name = context["dag_run"].conf.get("source_name")
    if not source_name:
        raise AirflowException("dag_run.conf must include 'source_name'")

    logger.info("Schema Guardian starting for source: %s", source_name)

    # Import here — agents/ is mounted at /opt/airflow/agents inside the container
    from agents.schema_guardian import run_guardian

    result = run_guardian(source_name)
    status = result.get("status")

    logger.info("Schema Guardian result for %s: status=%s", source_name, status)

    if status in ("stable", "baseline_created", "skipped"):
        logger.info(
            "%s — %s",
            source_name,
            {
                "stable":           f"schema stable ({result.get('field_count', '?')} fields)",
                "baseline_created": f"baseline created ({result.get('field_count', '?')} fields)",
                "skipped":          f"skipped ({result.get('reason', '?')})",
            }.get(status, status),
        )
        return

    if status == "drift_detected":
        changes = result.get("changes", [])
        logger.warning(
            "Drift detected for %s: %d change(s)", source_name, len(changes)
        )
        for c in changes:
            logger.warning(
                "  %s: %s (was: %s, now: %s)",
                c["change_type"], c["field_path"], c["old_value"], c["new_value"],
            )

        repair = result.get("repair", {})
        repair_status = repair.get("status")

        if repair_status == "repair_proposed":
            logger.info(
                "Repair proposed — repair_id=%s validation_passed=%s",
                repair.get("repair_id"),
                repair.get("validation_passed"),
            )
        elif repair_status == "failed":
            raise AirflowException(
                f"Repair engine failed for {source_name}: {repair.get('reason')}"
            )
        return

    # Unexpected status
    raise AirflowException(f"Unexpected Schema Guardian status: {status}")


with DAG(
    dag_id="agent_schema_guardian",
    description="Schema Guardian — detects drift and proposes repairs after ingestion",
    start_date=datetime(2024, 1, 1),
    schedule=None,
    catchup=False,
    default_args={"retries": 0},
) as dag:
    PythonOperator(
        task_id="run_schema_guardian",
        python_callable=run_schema_guardian,
    )
