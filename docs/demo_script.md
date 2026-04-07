# ADORE Demo Script (60 seconds)

## Setup (do before recording)
- `docker compose up -d` (containers warm)
- `streamlit run dashboards/agent_monitor.py` (dashboard open in browser)
- Terminal ready with chaos command typed but not executed
- Verify no pending repairs in dashboard

---

## Recording

**1. [5s]** Show the Agent Monitor dashboard — clean state, no pending repairs, recent events visible

**2. [5s]** Switch to terminal. Run:
```bash
python chaos/chaos_mode.py --inject schema_drift --source weather_sf
```
Show the output — `"Renamed temperature_2m → temp_celsius"`

**3. [5s]** Run the guardian directly:
```bash
python -c "from agents.schema_guardian import run_guardian; run_guardian('weather_sf')"
```
Or trigger `ingest_weather_sf` in the Airflow UI (localhost:8080) to show the full automated path.

**4. [10s]** Switch to Agent Monitor dashboard, click Refresh.
Show the pending repair appearing with the warning banner.

**5. [15s]** Expand the repair card. Slowly scroll through:
- Schema changes (field removed + field added)
- Impact tree (5 downstream models, City Intelligence dashboard)
- Side-by-side SQL diff (COALESCE fix handles both old and new rows)
- Validation results (all green — syntax, row count, NULL rates, column check)

**6. [10s]** Click Approve. Show the spinner, then success message.

**7. [5s]** Show repair moved to Repair History as `approved`.

**8. [5s]** Switch to terminal:
```bash
python chaos/chaos_mode.py --reset
```
Show: `"Pipeline restored"`

---

**Total: ~60 seconds**

---

## Talking Points (for voiceover or live demo)

- Detection is rule-based — a JSON fingerprint comparison. Zero LLM cost on stable runs.
- The LLM is invoked only when drift is detected. Uses Anthropic's tool-use API — the agent decides which tools to call (read model SQL, get schema diff, fetch sample data) and in what order.
- The COALESCE fix handles the transition window: rows ingested before and after the rename both parse correctly.
- Human-in-the-loop by design. The agent investigates and proposes. The engineer reviews evidence and approves.
- On approval: fix written to disk, dbt rebuilds the staging model and all downstream models automatically.
