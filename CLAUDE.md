# ADORE — Autonomous Data Operations and Recovery Engine


## Instructions for Claude Code
**Read this file at the start of every session.**

Before each task:
Analyse the instruction first and tell me if you have any questions. Wait for my confirmation before proceeding with the task.

After completing each task:
1. Update `Current Progress — Phase 1` by checking off the completed task.
2. Add any new decisions, patterns, gotchas, or conventions that emerged during implementation to the relevant section of this file (or create a new section if needed).
3. If a new reusable module/utility was created, document it under a `## Key Modules` section so future tasks know it exists and how to use it.
4. If any Critical Rule was added or modified, update the `## Critical Rules` section.
5. Commit the updated `CLAUDE.md` as part of the task's final commit.

**Post-task review process:**
After completing each task, produce two things:

Give me a proper review of the task that I can take back to my manager. Like what you did. Tell the important things that might be useful for making next decision. Keep under 200 words
1. **Manager review** (under 200 words): What was built, key architectural decisions made, verification results, and anything important for the next decision. This goes to the user's manager.

2. **Files for review** (for Tech Lead): Key files created or modified — not every file, just architecturally significant ones. Format:
```
FILES FOR REVIEW:
- path/to/file1 — brief reason
- path/to/file2 — brief reason
```

Do not proceed to the next task — wait for the user.

**Do not remove or rewrite existing content unless it is factually wrong.** Only append or update.


## What This Project Is
A data pipeline that ingests live San Francisco city data (weather, transit, incidents), transforms it through dbt medallion architecture (raw → staging → warehouse) in BigQuery, and uses an AI agent (Schema Guardian) to autonomously detect schema drift, diagnose impact, generate dbt model fixes, and present repair packages for human approval via a Streamlit dashboard.

## Tech Stack
- **Orchestration:** Apache Airflow 2.8.1 (self-hosted, Docker Compose, LocalExecutor)
- **Data Warehouse:** Google BigQuery (project: adore-pipeline-v2, region: us-central1)
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
8. **Intermediate dbt models** go in `dbt/models/intermediate/`. Materialized as views in the `warehouse` schema.

## BigQuery Datasets
- `raw` — Bronze. Raw API JSON responses.
- `staging` — Silver. dbt-parsed and cleaned.
- `warehouse` — Gold. Star schema facts and dimensions. Also contains intermediate cross-source models.
- `agents` — Agent logs, schema metadata, quality scores, approval queue.

## dbt Layer Architecture

### Layers
- **Staging (Silver):** One model per source. Parses raw JSON into typed columns. Materialized as views. Schema: `staging`.
- **Intermediate:** Cross-source analytical models. Joins staging models on shared dimensions (time). Materialized as views. Schema: `warehouse`.
- **Warehouse (Gold):** Final fact and dimension tables for dashboard consumption. Materialized as tables. Schema: `warehouse`.

### Intermediate Models (cross-source)
These models exist because the data sources share natural join keys (time). Only joins with genuine analytical value are built — no forced correlations.

- `int_hourly_weather_transit` — Hourly grain. Average transit delay + trip counts joined with hourly weather (precip, temp, wind). Join key: hour. Purpose: "does weather affect transit delays?"
- `int_daily_weather_incidents` — Daily grain. Incident counts by category joined with daily weather summary. Join key: date. Purpose: "does weather drive 311 complaint volume?"

### Warehouse Fact Tables
- `fact_weather_transit_hourly` — Built from int_hourly_weather_transit. Adds day_of_week, is_weekend, is_rush_hour. Dashboard-ready for weather impact analysis.
- `fact_daily_city_summary` — One row per day. Weather summary + total delays + total incidents + top incident categories. The "city pulse" table.
- `fact_transit_performance` — Single-source. Per-route, per-hour delay stats. Enables route reliability analysis.
- `fact_incident_trends` — Single-source. Daily/weekly incident counts by type and neighborhood.

### Warehouse Dimension Tables
- `dim_date` — date_id, date, hour, day_of_week, is_weekend, is_holiday
- `dim_location` — location_id, latitude, longitude, neighborhood, zip_code
- `dim_route` — route_id, route_name, transit_type
- `dim_stop` — stop_id, stop_name, latitude, longitude, route_id

### Design Decisions
- Weather data is city-level (single point for all SF). Do NOT join weather at neighborhood level — it's the same value for every neighborhood. Weather joins are time-based only.
- Transit ↔ Incidents has no natural causal link. Do NOT build cross-source models joining these two.
- Intermediate layer is justified by genuine cross-source analysis, not added for decoration.

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
- dbt intermediate models: `dbt/models/intermediate/int_{description}.sql`
- dbt warehouse models: `dbt/models/warehouse/fact_{source}_{city}.sql`, `dim_{name}.sql`
- Agent implementations: `agents/{agent_name}.py`
- Dashboard apps: `dashboards/{dashboard_name}.py`
- Utility modules: `dags/utils/`

## Current Progress — Phase 1 (Active)
- [x] Task 0 — Repository setup and scaffolding
- [x] Task 1 — Local environment setup (Docker, Airflow)
- [x] Task 2 — GCP project setup
- [x] Task 3 — BigQuery datasets
- [x] Task 4 — API credential testing
- [x] Task 5/6 — Airflow verification + GCP cost protection
- [x] Task 7 — First ingestion DAG (Open-Meteo)
- [x] Task 8 — Remaining ingestion DAGs
- [x] Task 10 — dbt setup
- [x] Task 11 — dbt staging models (Silver)
- [ ] Task 12 — dbt warehouse models (Gold)
- [ ] Task 12b — dbt intermediate models (cross-source analytics)
- [ ] Task 13 — Schema Guardian agent
- [ ] Task 14 — Chaos Engine (schema drift only)
- [ ] Task 15 — Agent Monitor dashboard
- [ ] Task 16 — City Intelligence dashboard
- [ ] Task 17 — README + architecture diagram + demo polish

## dbt Staging Notes
- **Schema naming:** dbt by default creates `{target_dataset}_{custom_schema}`. The `generate_schema_name` macro in `dbt/macros/` overrides this to use the custom schema directly. Without it, staging views land in `staging_staging` instead of `staging`.
- **Weather UNNEST:** Open-Meteo returns parallel arrays. Use `GENERATE_ARRAY(0, N-1)` + `SAFE_OFFSET(idx)` to zip them — BigQuery has no native parallel array unnest.
- **Transit JSON keys are PascalCase:** `Entities`, `TripUpdate`, `StopTimeUpdates`, `Arrival.Delay`. Standard GTFS-RT lowercase field names do NOT apply to this 511.org response.
- **Incidents timestamps:** Format is `%Y-%m-%dT%H:%M:%E3S` (milliseconds suffix `.000`). `closed_datetime` does not exist in the SF 311 API response — omitted.
- **Incidents lat/long:** Stored as strings in the API response — must `SAFE_CAST` to `FLOAT64`.

## dbt Setup Notes
- `profiles.yml` is gitignored — commit `profiles.yml.example` instead. The real file must exist at `dbt/profiles.yml` locally and is mounted into containers via `./dbt:/opt/airflow/dbt`.
- `profiles.yml` requires a `dataset` field (dbt-bigquery calls it `dataset`, not `schema`). Missing this field causes `Runtime Error: Must specify schema`.
- `DBT_PROFILES_DIR=/opt/airflow/dbt` is set in `x-airflow-env` so dbt finds profiles.yml inside the container.
- `dbt debug` will always show `git ERROR` inside the Airflow container — git is not installed there. This is non-blocking; all dbt checks pass.
- dbt version in container: `1.9.0-b4`, adapter: `dbt-bigquery 1.8.0`.

## Docker / Airflow Setup Notes
- SQLite does not support LocalExecutor — Postgres is required as the Airflow metadata DB. A `postgres:15` service is included in `docker-compose.yml` for this purpose only (not a data warehouse).
- `airflow-init` service runs `db migrate` + `users create` once, then exits (`restart: "no"`). Webserver and scheduler depend on it completing successfully.
- GCP credentials file is gitignored. Mount it by setting `GCP_CREDENTIALS_PATH` in `.env` and adding a volume entry if needed per-task.
- Airflow logs are written to `./logs/` (gitignored).
- Default admin login: `airflow` / `airflow` (local dev only).

## Environment Assumptions — Never Do This
**Never assume the user has any CLI tool, runtime, or package installed.** Before giving a command that requires a tool, verify it is installed first or explicitly guide installation. This applies to: `gcloud`, `docker`, `python`, `dbt`, `node`, or anything else.

When guiding setup steps:
1. Check if the tool exists (`tool --version`) before using it
2. If not found, provide install instructions first
3. Account for OS/architecture differences (e.g. Apple Silicon vs Intel on macOS)
4. Only proceed to the next step after the user confirms the current one works

## Lessons Learned

### Task 1 — Docker Compose config bugs (3 iterations to fix)
**Mistakes made:**
1. **YAML anchor cycle** — merged `*airflow-common` (a service-level anchor) into an `environment` mapping. A service block can't be merged into a field-level mapping. YAML detected the self-reference and refused to parse.
2. **Mixed Airflow init patterns** — set `_AIRFLOW_WWW_USER_CREATE=true` (entrypoint-driven init, needs `_AIRFLOW_WWW_USER_PASSWORD`) while also providing a custom `command` that ran `airflow users create`. Two mechanisms fighting over the same job.
3. **YAML `>` block scalar** — wrote a multi-line `airflow users create` command under `>`. YAML `>` folds newlines into spaces, turning each flag line into a separate shell command.

**Root cause:** Pattern-matched against recalled examples without simulating what the parser and runtime would actually do. Plausible-looking config ≠ correct config.

**Going forward:**
- When writing YAML anchors, verify the anchor scope matches the merge target (service block → service block, env map → env map).
- Never mix two init mechanisms for the same resource. Pick one and use it exclusively.
- Use `|` for multiline shell scripts in YAML (preserves newlines). Use `>` only for folded prose. When in doubt, use a single-line `bash -c "..."`.
- Reason through config files line by line before writing — don't assemble from recalled patterns.

## Key Modules

### `dags/utils/schemas.py`
Single source of truth for all BigQuery table schemas. Import from here — never define schemas inline in DAGs or setup scripts.
- `RAW_TABLE_SCHEMA` — shared schema for all raw ingestion tables (`ingested_at TIMESTAMP`, `source STRING`, `raw_data STRING`)
- Staging, warehouse, and agent schemas will be added here in Tasks 11–13.

### `infra/setup_bigquery.py`
Creates all 4 datasets (`raw`, `staging`, `warehouse`, `agents`) and 3 raw tables (`weather_sf`, `transit_sf`, `incidents_sf`). Idempotent — safe to re-run. Imports schemas from `dags/utils/schemas.py`.

### `infra/verify_gcp.py`
Confirms BigQuery connectivity. Run after any credential or project changes.

### `infra/api_tests/test_open_meteo.py`
Tests Open-Meteo weather API. No auth. Verifies current_weather and hourly fields are present.

### `infra/api_tests/test_511.py`
Tests 511.org GTFS-RT TripUpdates feed. Decodes with `utf-8-sig` (BOM handling). 0 entities is valid outside peak hours — confirms connectivity and parse, not volume.

### `infra/api_tests/test_sf311.py`
Tests SF 311 Socrata API. Sends `X-App-Token` header. Filters last 24h with `$where` clause using `%Y-%m-%dT%H:%M:%S` format (no `.000Z` suffix).

### `dags/utils/bigquery_client.py`
The ONLY place in the project that writes to BigQuery. All DAGs must import from here.
- `write_to_bigquery(dataset_id, table_id, rows)` — streaming insert, raises on error
- `query_bigquery(sql)` — runs query with 1GB `maximum_bytes_billed` cap enforced

### `dags/ingestion/dag_weather_sf.py`
Ingestion DAG for Open-Meteo weather. Runs every 15 min. Fetches full API response, writes one row to `raw.weather_sf`. Establishes the pattern for all ingestion DAGs.

### `dags/ingestion/dag_transit_sf.py`
Ingestion DAG for 511.org GTFS-RT transit. Runs every 15 min. Decodes response with `utf-8-sig` (BOM), validates JSON, writes to `raw.transit_sf`. Never use `response.json()` for this endpoint.

### `dags/ingestion/dag_incidents_sf.py`
Ingestion DAG for SF 311 incidents. Runs daily at 2am UTC. Fetches last 24h of records ($limit=50000), writes entire array as single row to `raw.incidents_sf`. Logs a warning if response hits the 50k limit (potential truncation).

### `dbt/dbt_project.yml`
dbt project config. Staging → views in `staging` schema. Intermediate → views in `warehouse` schema. Warehouse → tables in `warehouse` schema.

### `dbt/models/staging/sources.yml`
Declares the `raw` source with all 3 raw tables. Models reference raw tables via `{{ source('raw', 'table_name') }}`.

### `dbt/macros/generate_schema_name.sql`
Overrides dbt's default schema naming. Without this, dbt appends the target dataset prefix to custom schemas (e.g. `staging_staging`). This macro uses the custom schema name directly so models land in `staging` and `warehouse` as intended.

### `dbt/models/staging/stg_weather_sf.sql`
Parses Open-Meteo hourly arrays using index-based UNNEST (`GENERATE_ARRAY` + `SAFE_OFFSET`). Deduplicates on `recorded_at`.

### `dbt/models/staging/stg_transit_sf.sql`
Double-unnests GTFS-RT: Entities → StopTimeUpdates. Keys are PascalCase (`Entities`, `TripUpdate`, `StopTimeUpdates`). Deduplicates on `(trip_id, stop_id, recorded_at)`.

### `dbt/models/staging/stg_incidents_sf.sql`
Unnests SF 311 JSON array. Maps `status_description` → `status`, `lat`/`long` (strings) → FLOAT64, `neighborhoods_sffind_boundaries` → `neighborhood`. Deduplicates on `service_request_id`.

## GCP Cost Controls
- **Budget alert:** $50 cap on `adore-pipeline-v2` with email alerts at 50% ($25), 80% ($40), and 100% ($50). Configured in GCP Console → Billing → Budgets & alerts.
- **BigQuery max bytes billed:** No persistent project-level default exists in the BigQuery API. The 1GB cap (`maximum_bytes_billed=1_073_741_824`) must be set per query via `QueryJobConfig`. This will be enforced in `dags/utils/bigquery_client.py` so every query in the project has the cap automatically.

## GCP Setup Notes
- GCP project ID: `adore-pipeline-v2` (original `adore-pipeline` was deleted)
- Service account: `adore-sa@adore-pipeline-v2.iam.gserviceaccount.com` with roles `BigQuery Admin` and `Storage Admin`
- Credentials key stored at project root as `gcp-credentials.json` (gitignored)
- `GOOGLE_APPLICATION_CREDENTIALS` is set in `x-airflow-env` in `docker-compose.yml` pointing to `/opt/airflow/gcp-credentials.json` (mounted read-only from `GCP_CREDENTIALS_PATH`)
- `infra/verify_gcp.py` confirms BigQuery connectivity — run it after any credential or project changes
- `python-dotenv` added to `requirements.txt` for loading `.env` outside of Docker contexts

## Stretch Goals — Phase 2/3 (Only after Phase 1 is polished)
- [ ] Deploy Airflow to GCE VM (deploy after Phase 1 is complete — no benefit deploying during active development)
- [ ] Quality Inspector (rule-based only, no LLM)
- [ ] Pipeline Doctor (LangGraph)
- [ ] Documentation Agent
- [ ] Pipeline Health dashboard