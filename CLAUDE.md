# ADORE — Autonomous Data Operations and Recovery Engine

## What This Project Is
A data pipeline that ingests live San Francisco city data (weather, transit, incidents), transforms it through dbt medallion architecture (raw → staging → warehouse) in BigQuery, and uses an AI agent (Schema Guardian) to autonomously detect schema drift, diagnose impact, generate dbt model fixes, and present repair packages for human approval via a Streamlit dashboard.

## Tech Stack
- **Orchestration:** Apache Airflow 2.8.1 (self-hosted, Docker Compose, LocalExecutor)
- **Data Warehouse:** Google BigQuery (project: adore-pipeline, region: us-central1)
- **Transformation:** dbt (medallion: raw → staging → warehouse)
- **Agent Framework:** Anthropic Python SDK (native tool-use API, no LangChain)
- **Dashboard:** Streamlit
- **Language:** Python 3.11+
- **Cloud:** GCP ($300 free trial)

## Critical Rules
1. **Never define BigQuery table schemas in DAG files.** All schemas go in `dags/utils/schemas.py`.
2. **Never write BigQuery insertion logic in DAG files.** All BQ writes use `dags/utils/bigquery_client.py`.
3. **All DAGs use `catchup=False`.** No backfilling real-time data.
4. **Raw tables all share the same schema:** `ingested_at (TIMESTAMP), source (STRING), raw_data (STRING)`.
5. **LLM is never called on every poll cycle.** Rule-based detection first, LLM only when anomaly detected.
6. **All agent actions go through approval_queue.** Human approves, rejects, or modifies before deployment.
7. **Environment variables via `.env` file.** Never hardcode credentials or project IDs.

## BigQuery Datasets
- `raw` — Bronze. Raw API JSON responses.
- `staging` — Silver. dbt-parsed and cleaned.
- `warehouse` — Gold. Star schema facts and dimensions.
- `agents` — Agent logs, schema metadata, quality scores, approval queue.

## Data Sources
| Source | API | Frequency | Auth |
|--------|-----|-----------|------|
| Open-Meteo | Weather (temp, precip, wind, humidity) | Every 15 min | None |
| 511.org GTFS-RT | SF transit trip updates | Every 15 min | API token |
| SF 311 Socrata | City incidents | Daily 2am UTC | App token |

## API Notes
- **511.org:** TripUpdates endpoint, `format=json`. Decode with `utf-8-sig`. Rate limit 60 req/hr.
- **SF 311:** Endpoint `https://data.sfgov.org/resource/vw6y-z8j6.json`. Date filter format `%Y-%m-%dT%H:%M:%S` (no `.000Z` suffix).
- **Open-Meteo:** No key. SF coords: `lat=37.7749, lon=-122.4194`.

## File Conventions
- Ingestion DAGs: `dags/ingestion/dag_{source}_{city}.py`
- dbt staging models: `dbt/models/staging/stg_{source}_{city}.sql`
- dbt warehouse models: `dbt/models/warehouse/fact_{source}_{city}.sql`, `dim_{name}.sql`
- Agent implementations: `agents/{agent_name}.py`
- Dashboard apps: `dashboards/{dashboard_name}.py`
- Utility modules: `dags/utils/`

## Current Progress
- [x] Task 0 — Repository setup and scaffolding
- [ ] Task 1 — Local environment setup (Docker, Airflow)
- [ ] Task 2 — GCP project setup
- [ ] Task 3 — BigQuery datasets
- [ ] Task 4 — API credential testing
- [ ] Task 5 — Airflow running locally
- [ ] Task 6 — GCP cost protection
- [ ] Task 7 — First ingestion DAG (Open-Meteo)
- [ ] Task 8 — Remaining ingestion DAGs
- [ ] Task 9 — Deploy Airflow to GCE VM
- [ ] Task 10 — dbt setup
- [ ] Task 11 — dbt staging models
- [ ] Task 12 — dbt warehouse models
- [ ] Task 13 — Schema Guardian agent
- [ ] Task 14 — Chaos Engine (schema drift only)
- [ ] Task 15 — Agent Monitor dashboard
- [ ] Task 16 — Quality Inspector (rule-based only, stretch)
- [ ] Task 17 — Pipeline Doctor (stretch)
- [ ] Task 18 — Documentation Agent (stretch)
- [ ] Task 19 — City Intelligence dashboard (stretch)
- [ ] Task 20 — README + architecture diagram + demo polish