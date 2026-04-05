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
9. **`agents.agent_repairs` uses DML INSERT (`insert_rows_sql`), not streaming insert.** Streaming inserts land in a buffer that blocks DML UPDATE for up to ~90 minutes. `agent_repairs` needs an immediate UPDATE on approval, so it must be written via `insert_rows_sql`. All other tables continue to use `write_to_bigquery` (streaming insert).

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
- [x] Task 12 — dbt warehouse models (Gold)
- [x] Task 12b — dbt intermediate models (cross-source analytics)
- [x] Task 13a — Schema Guardian: infrastructure + detection layer
- [x] Task 13b-1 — Schema Guardian: lineage analysis module
- [x] Task 13b-2 — Schema Guardian: data assessment + repair validation utilities
- [x] Task 13b-3 — Schema Guardian: email notification module
- [x] Task 13b-4 — Schema Guardian: LLM repair engine
- [x] Task 13b-5 — Schema Guardian: Airflow DAG + end-to-end verification
- [x] Task 13 — Schema Guardian complete
- [ ] Task 13b-5 — Schema Guardian: approval queue integration
- [x] Task 14 — Chaos Engine (schema drift only)
- [x] Task 15a — Agent Monitor dashboard + deploy repair function
- [ ] Task 16 — City Intelligence dashboard
- [ ] Task 17 — README + architecture diagram + demo polish

## dbt Intermediate + Cross-Source Notes
- **`days_with_incidents=0` on first runs** — the SF 311 DAG runs at 2am UTC and fetches the prior 24h. Open-Meteo returns a 7-day forecast window from the current date. On fresh data, the incident dates (yesterday) lag behind the weather window (today to +7 days), so the LEFT JOIN produces NULLs. This resolves naturally as more incident data accumulates.
- **`fact_daily_city_summary` references `int_daily_weather_incidents`** — the "self-contained" constraint from the task spec was relaxed. Intermediates exist to be reused; duplicating `top_category` window logic in two files was worse than a clean dependency.
- **`rows` is a reserved BigQuery keyword** — do not use it as a column alias in BigQuery SQL. Use `row_count` instead. Using `rows` causes `Syntax error: Unexpected keyword ROWS`.
- **FULL OUTER JOIN grain** — `fact_daily_city_summary` uses FULL OUTER JOIN across weather+incidents and transit CTEs. `COALESCE(wi.date, t.date)` produces the primary key. Only days with data in at least one source appear — no empty rows from dim_date spine.

## dbt Warehouse Notes
- **`dim_date` grain is hourly** — matches weather and transit data. Join incidents (daily grain) to dim_date using `DATE(date_hour)`.
- **`avg_resolution_hours` is NULL** — SF 311 API does not return `closed_datetime`. Placeholder field kept for future use.
- **GTFS-RT has no static data** — `dim_route` and `dim_stop` contain IDs only. Route names, stop names, and stop coordinates require a separate GTFS static feed (not in scope).
- **dim_stop primary route** — when a stop appears on multiple routes, the most-observed route wins (by COUNT). This is an approximation.
- **`on_time_pct` definition** — arrival_delay_seconds BETWEEN -60 AND 300 (1 min early to 5 min late). Adjust thresholds in Task 12b/15 if needed.

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
- `./agents` is mounted at `/opt/airflow/agents` (added Task 13b-5). Agents use `sys.path.insert(0, parent.parent)` which resolves to `/opt/airflow/` — giving access to both `agents/` and `dags/`. Verified: `from agents.schema_guardian import run_guardian` works inside container.
- **DAG trigger pattern** — ingestion DAGs use `TriggerDagRunOperator` (import: `airflow.operators.trigger_dagrun`, Airflow 2.x path) with `wait_for_completion=False`. The agent DAG runs independently; ingestion doesn't block on it.
- **`schedule=None` for agent DAGs** — Schema Guardian and future agent DAGs are trigger-only. They never run on their own schedule.

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

### `infra/verify_data.py`
Queries raw, staging, and warehouse layers to confirm row counts and value ranges. Run after any dbt full refresh or data backfill.

### `infra/verify_task12b.py`
Verifies intermediate and cross-source fact tables from Task 12b. Checks row counts, NULL ratios for cross-source joins, and dim_date population.

### `infra/api_tests/test_open_meteo.py`
Tests Open-Meteo weather API. No auth. Verifies current_weather and hourly fields are present.

### `infra/api_tests/test_511.py`
Tests 511.org GTFS-RT TripUpdates feed. Decodes with `utf-8-sig` (BOM handling). 0 entities is valid outside peak hours — confirms connectivity and parse, not volume.

### `infra/api_tests/test_sf311.py`
Tests SF 311 Socrata API. Sends `X-App-Token` header. Filters last 24h with `$where` clause using `%Y-%m-%dT%H:%M:%S` format (no `.000Z` suffix).

### `dags/utils/bigquery_client.py`
The ONLY place in the project that writes to BigQuery. All DAGs must import from here.
- `write_to_bigquery(dataset_id, table_id, rows)` — streaming insert, raises on error. Use for all tables except `agent_repairs`.
- `insert_rows_sql(dataset_id, table_id, rows)` — DML INSERT (not streaming). Rows are immediately DML-updatable. Use only for `agent_repairs` (requires UPDATE on approval). Handles Python types: `None`→NULL, `bool`→TRUE/FALSE, `datetime`→TIMESTAMP(), str/int/float as literals.
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

### `dbt/models/intermediate/int_hourly_weather_transit.sql`
Hourly weather + city-wide transit aggregation. LEFT JOIN so every weather hour is preserved. Transit aggregates: avg/max delay, total trips, total stop updates, on_time_pct.

### `dbt/models/intermediate/int_daily_weather_incidents.sql`
Daily weather + incident counts. LEFT JOIN so every weather day is preserved. Includes `top_category` via ROW_NUMBER window function (alphabetical tiebreak).

### `dbt/models/warehouse/fact_weather_transit_hourly.sql`
Enriches `int_hourly_weather_transit` with dim_date fields. Dashboard-ready: no joins needed for time-based filtering.

### `dbt/models/warehouse/fact_daily_city_summary.sql`
Daily city pulse. References `int_daily_weather_incidents` for weather+incidents, aggregates `stg_transit_sf` directly for transit. FULL OUTER JOIN so any day in either source appears.

### `agents/schema_guardian.py`
Schema Guardian detection layer. Standalone — loads `.env` and credentials itself. Key functions:
- `extract_schema(raw_data_json)` — recursive JSON fingerprinter. Dot notation for nested objects, `[]` notation for array elements. Handles top-level arrays (SF 311).
- `get_stored_schema(source_name)` — reads latest active schema from `agents.schema_metadata` via window function.
- `store_schema(source_name, schema)` — append-only write. Active fields get `is_active=TRUE`, missing fields get `is_active=FALSE` (never deleted).
- `compare_schemas(old, new)` — pure function, returns list of changes: `field_added`, `field_removed`, `type_changed`.
- `run_detection(source_name)` — main entry point. Returns status dict: `baseline_created`, `stable`, `drift_detected`, or `skipped`.

### `agents/test_schema_guardian.py`
Test script for detection layer. Run twice to confirm baseline → stable flow. Also prints BigQuery state summary after each run.

### `agents/lineage_analyzer.py`
Lineage analysis module. Pure Python, no BigQuery, no LLM. Key functions:
- `load_manifest(path)` — loads dbt/target/manifest.json. Raises clear error if missing.
- `build_dependency_graph(manifest)` — builds `upstream` and `downstream` dicts from manifest nodes. Filters to models only.
- `get_downstream_models(graph, model_name, manifest)` — BFS traversal returning all affected models with depth. Deduplicates via visited set. Short name → unique_id resolved from manifest metadata (no hardcoded prefix).
- `get_impact_summary(model_name)` — main entry point. Returns downstream models, affected dashboards, and rendered tree text.
- `DASHBOARD_MAP` — dict mapping warehouse table names to dashboard names.

### `agents/test_lineage.py`
Test suite for lineage analyzer. 31 checks covering all three staging models, deduplication, depths, dashboard mapping, tree rendering, and nonexistent model edge case.

### `agents/data_assessor.py`
Assesses whether corrupted data landed in staging during the drift window. Key components:
- `STAGING_FIELD_MAP` — maps fingerprint paths (e.g. `"hourly.temperature_2m"`) to staging column names (e.g. `"temperature_c"`). Based on Task 11 staging SQL.
- `assess_drift_damage(source_name, changes, detection_time)` — main entry point. Counts NULLs per affected column in staging rows ingested since `detection_time`. Uses LIMIT 500 for cost control. `field_added` changes are skipped (no damage). Returns structured dict with `corrupted_rows_estimate` and `recommendation`.

### `agents/repair_validator.py`
Validates proposed SQL fixes before they enter the approval queue. Key components:
- `resolve_dbt_refs(sql)` — replaces Jinja tags with real BigQuery references. `source('raw', X)` → raw schema, `ref('stg_X')` → staging, everything else → warehouse.
- `validate_sql_fix(source_name, new_sql, old_sql)` — four sequential checks: syntax (dry run), row count (LIMIT 500, 10% threshold), NULL rates, column names. Syntax failure short-circuits the rest.

### `agents/notifications.py`
Sends plain-text email alerts when a repair package is ready for approval. Standalone — no imports from other agent modules.
- `send_repair_alert(repair_summary)` — composes and sends via Gmail SMTP (TLS, port 587). Returns True on success, False on any failure. Never raises — all errors are logged so the calling agent is never blocked.
- Reads `ALERT_EMAIL_ADDRESS`, `ALERT_EMAIL_APP_PASSWORD`, `ALERT_EMAIL_RECIPIENT` from env. Logs a warning and returns False if any are missing.

### `agents/repair_engine.py`
Core LLM repair orchestrator. Uses Anthropic tool-use API to generate SQL fixes for schema drift.
- `run_repair(source_name, event_id, changes, old_schema, new_schema)` — full repair flow: tool-use loop → validate → assess damage → write to `agent_repairs` → notify. Returns `{status, repair_id, validation_passed, notification_sent, impact_summary}`.
- Five tools: `get_current_model_sql`, `get_schema_diff`, `get_downstream_impact`, `get_sample_raw_data`, `propose_sql_fix` (terminal). LLM calls them in any order; loop exits on `propose_sql_fix` or max 10 iterations.
- Model: `claude-sonnet-4-6`. All fixes queued as `status="pending"` — no auto-deployment.

### `agents/schema_guardian.py` — `run_guardian()`
Added in Task 13b-4. Orchestrates detection + repair as a single pipeline entry point.
- `run_guardian(source_name)` — calls `run_detection()`, then triggers `run_repair()` if drift is found. Returns detection result augmented with `"repair"` key.
- `run_detection()` now includes `old_schema` and `new_schema` in its `drift_detected` return so `run_guardian` can pass them to the repair engine.

### `dags/agents/dag_schema_guardian.py`
Schema Guardian Airflow DAG. `schedule=None` — triggered only, never runs on its own.
- DAG id: `agent_schema_guardian`. Single PythonOperator task: `run_schema_guardian`.
- Reads `source_name` from `dag_run.conf`. Imports `run_guardian` inside the task function (not at module level) so the agents/ path is resolved at runtime inside the container.
- Raises `AirflowException` only on repair failure — stable/baseline/skipped all exit cleanly.

### `dags/utils/bigquery_client.py` — `dry_run_sql()`
Added in Task 13b-2. Validates SQL without executing it — zero cost, zero rows scanned. Returns `{valid, estimated_bytes, error}`.

## Data Assessor + Repair Validator Notes
- **LIMIT 500** — all validation queries use LIMIT 500 to keep costs low. Representative sample, not full scan.
- **Syntax short-circuits** — `validate_sql_fix` stops after syntax failure and skips remaining checks. Invalid SQL would crash the subsequent queries.
- **NULL threshold** — `_check_nulls` flags columns where new SQL produces >5 percentage points more NULLs than old SQL.
- **Row count threshold** — 10% diff flags a warning. Configurable via `ROW_COUNT_DIFF_THRESHOLD_PCT` in `repair_validator.py`.
- **`resolve_dbt_refs` scope** — only handles patterns in THIS project. Not a general Jinja parser.

## Chaos Engine Notes
- **Schema drift only** — no data quality or pipeline failure injection. Phase 2 stretch goal.
- **Log before inject** — `chaos_log.json` is written BEFORE the BigQuery write. Cleanup is possible even if BQ write fails.
- **Streaming buffer on reset** — BigQuery raises an explicit error if you DELETE a row still in the streaming buffer. The error is caught and printed; the log is still cleared. The row will be gone within ~90 minutes automatically.
- **Schema baseline after reset** — `schema_metadata` retains the drifted fingerprint after `--reset`. The next real `run_guardian` will detect "drift back to normal" and may trigger another repair. This is expected and demonstrates bidirectional detection.
- **Transit rename is the most dramatic variant** — `TripUpdate → TripData` changes 8+ fingerprinted paths simultaneously. Best for demos.
- **`type_change` variant is NOT implemented** — the schema fingerprinter types arrays as `"array"` regardless of element type. A numbers→strings change inside an array is invisible to the fingerprinter. Only structural key-level changes (rename, remove, add) are detectable.

### `chaos/chaos_mode.py`
CLI tool for injecting schema drift. Usage: `python3 chaos/chaos_mode.py --inject schema_drift --source {source} [--variant rename_field|remove_field|add_field]`
- `--inject schema_drift --source X` — fetches latest raw row, mutates it, writes back with newer `ingested_at`
- `--reset` — attempts DELETE of all injected rows, clears `chaos_log.json`
- `--status` — prints all active injections from `chaos_log.json`
- Default variant: `rename_field` (most realistic real-world drift scenario)

### `agents/repair_engine.py` — `deploy_repair()` + `reject_repair()`
Added in Task 15a.
- `deploy_repair(repair_id)` — writes new SQL to disk, runs `dbt run --select stg_{source}+` inside the container via subprocess, updates BigQuery status to `approved`. Creates `.sql.backup` before overwriting; restores on failure.
- `reject_repair(repair_id, user_notes)` — DML UPDATE to `rejected` status, logs event.
- subprocess uses `docker compose exec -T` (no TTY) with `cwd=PROJECT_ROOT`.

### `dashboards/agent_monitor.py`
Agent Monitor Streamlit dashboard. Run: `streamlit run dashboards/agent_monitor.py`
- **Pending Approvals** — expandable cards with schema diff, impact tree, data assessment, SQL side-by-side, validation checks, Approve/Reject buttons.
- **Recent Events** — last 50 events from `agent_events`, filterable by source + event type.
- **Repair History** — last 20 non-pending repairs with expandable details.

## Email Notifications
- Gmail app password required — see Google Account → Security → 2-Step Verification → App passwords.

## LLM Repair Engine Notes
- **Tool-use loop** — max 10 iterations. The LLM calls tools in any order; loop exits when `propose_sql_fix` is called or iterations are exhausted.
- **`propose_sql_fix` is terminal** — once called, the loop exits immediately regardless of remaining iterations. No further tool calls are processed.
- **Validation runs on failure too** — if validation fails, the repair is still written to `agent_repairs` with the validation result. Human reviewers see the failure evidence and can decide.
- **Circular import guard** — `schema_guardian.py` imports `repair_engine` inside `run_guardian()` (not at module top), preventing a circular import since `repair_engine` imports from `lineage_analyzer`, `data_assessor`, etc.
- **`old_schema`/`new_schema` in detection result** — `run_detection()` now returns these in the `drift_detected` result so `run_guardian()` can pass them to `run_repair()`. Without this, they'd be gone after `store_schema()` updates the baseline.
- **`ANTHROPIC_API_KEY`** — required env var. If missing, `run_repair` returns `{"status": "failed", "reason": "missing_api_key"}` without crashing.
- **`max_tokens=4096` may be tight for transit model** — `stg_transit_sf.sql` is 80+ lines of complex SQL. If the LLM truncates its `propose_sql_fix` output, the column check will catch it (missing columns = fail). If truncation issues appear during Chaos Engine testing, bump to 8192 in `repair_engine.py`.
- **`deploy_repair` is built** — Task 15a. See Key Modules above.

## Lineage Analyzer Notes
- **manifest.json location** — `dbt/target/manifest.json`. Generated by `dbt ls` (fastest) or `dbt run`. Must be regenerated after adding new models.
- **BFS depth assignment** — first visit wins. If a model is reachable via two paths, it gets the depth of the shorter path. This prevents duplicates and gives the most direct depth.
- **Tree rendering** — `├──` for non-last siblings, `└──` for last. `│` continuation lines only appear under non-last children. Implemented via recursive descent with a prefix string.
- **Project name** — read from `manifest["metadata"]["project_name"]`, not hardcoded. Unique IDs constructed as `model.{project_name}.{model_name}`.

## Schema Guardian — Detection Notes
- **`incidents_sf` skips on empty raw data** — SF 311 raw rows currently contain `[]` (no records). Detection is skipped rather than storing a 0-field baseline. Will auto-baseline once real incident data arrives.
- **Severity rules** — `field_removed` and `type_changed` → `critical`. `field_added` only → `warning`. Worst change in the set wins.
- **Append-only schema history** — `schema_metadata` is never updated or deleted. Window function `ROW_NUMBER() PARTITION BY field_path ORDER BY detected_at DESC` always retrieves the latest state per field.

### Warehouse Dimensions
- `dim_date` — generated hourly spine (2024–2026), 26.3k rows. No source dependency.
- `dim_route` — 59 distinct routes from GTFS-RT. IDs only — no names available from TripUpdates feed.
- `dim_stop` — 3,037 distinct stops. Primary route assigned by most-frequent observation. IDs only.
- `dim_neighborhood` — 100 SF neighborhoods from 311 data. Centroid = avg lat/lon of incidents.

### Warehouse Facts
- `fact_transit_performance` — route × hour grain. `on_time_pct` = % delays between -60s and 300s.
- `fact_incident_trends` — date × neighborhood × service_name grain. `avg_resolution_hours` is NULL — `closed_datetime` not present in SF 311 API response.
- `fact_weather_transit_hourly` — hourly grain. Built from `int_hourly_weather_transit`, enriched with dim_date fields (date, hour, day_of_week, is_weekend, is_rush_hour). Dashboard-ready — no joins needed.
- `fact_daily_city_summary` — daily grain. City pulse table. References `int_daily_weather_incidents` for weather+incidents side; aggregates `stg_transit_sf` directly for transit (int_hourly_weather_transit is hourly — re-aggregating from staging avoids double-aggregation). FULL OUTER JOIN across sources so any day in either appears.

### Intermediate Models
- `int_hourly_weather_transit` — view in warehouse schema. Left join: weather (left) + city-wide transit aggregated to hour. Transit columns are NULL for hours with no feed data (expected for late night / future forecast window).
- `int_daily_weather_incidents` — view in warehouse schema. Left join: weather daily (left) + incidents aggregated to date. `top_category` uses ROW_NUMBER() PARTITION BY date ORDER BY cnt DESC, service_name ASC (alphabetical tiebreak for determinism).

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

## Schema Guardian Features

### Detection Layer (Task 13a)
- Rule-based schema fingerprinting and comparison
- Change classification: field_added, field_removed, type_changed
- Append-only schema history in BigQuery

### Repair Layer (Task 13b)
- Context-aware SQL fix generation via Anthropic tool-use API
- Downstream impact analysis via dbt lineage (manifest.json)
- Pre-existing data assessment — checks if corrupted data landed during drift window
- Automated validation — row count comparison, NULL checks, dbt test execution
- Email notification to engineer when repair package is ready
- Complete repair package presented via Agent Monitor dashboard with Approve/Reject

### Repair Package Contents
- What changed (schema diff)
- Change classification (renamed/removed/type changed)
- Full downstream impact tree (models + dashboards)
- Data corruption assessment
- Proposed SQL fix
- Validation results with evidence
- Approve / Reject / Modify interface

## Stretch Goals — Phase 2/3 (Only after Phase 1 is polished)
- [ ] Deploy Airflow to GCE VM (deploy after Phase 1 is complete — no benefit deploying during active development)
- [ ] Quality Inspector (rule-based only, no LLM)
- [ ] Pipeline Doctor (LangGraph)
- [ ] Documentation Agent
- [ ] Pipeline Health dashboard