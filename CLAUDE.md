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

**Do not remove or rewrite existing content unless it is factually wrong.** Only append or update.


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

## Current Progress — Phase 1 (Active)
- [x] Task 0 — Repository setup and scaffolding
- [x] Task 1 — Local environment setup (Docker, Airflow)
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
- [ ] Task 16 — README + architecture diagram + demo polish

## Docker / Airflow Setup Notes
- SQLite does not support LocalExecutor — Postgres is required as the Airflow metadata DB. A `postgres:15` service is included in `docker-compose.yml` for this purpose only (not a data warehouse).
- `airflow-init` service runs `db migrate` + `users create` once, then exits (`restart: "no"`). Webserver and scheduler depend on it completing successfully.
- GCP credentials file is gitignored. Mount it by setting `GCP_CREDENTIALS_PATH` in `.env` and adding a volume entry if needed per-task.
- Airflow logs are written to `./logs/` (gitignored).
- Default admin login: `airflow` / `airflow` (local dev only).

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

## Stretch Goals — Phase 2/3 (Only after Phase 1 is polished)
- [ ] Quality Inspector (rule-based only, no LLM)
- [ ] Pipeline Doctor (LangGraph)
- [ ] Documentation Agent
- [ ] City Intelligence dashboard
- [ ] Pipeline Health dashboard