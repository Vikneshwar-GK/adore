"""
Chaos Engine — Task 14

CLI tool that injects controlled schema drift into raw BigQuery tables to
trigger Schema Guardian detection and repair flows.

Schema drift injection only — no data quality or pipeline failure types.
All state is in chaos/chaos_log.json. No database tables for chaos tracking.

Usage:
    python chaos/chaos_mode.py --inject schema_drift --source weather_sf
    python chaos/chaos_mode.py --inject schema_drift --source weather_sf --variant remove_field
    python chaos/chaos_mode.py --inject schema_drift --source transit_sf
    python chaos/chaos_mode.py --inject schema_drift --source incidents_sf
    python chaos/chaos_mode.py --reset
    python chaos/chaos_mode.py --status

Variants per source:
    weather_sf:   rename_field | remove_field | add_field
    transit_sf:   rename_field | remove_field | add_field
    incidents_sf: rename_field | remove_field | add_field

Default variant (when --variant is omitted): rename_field
"""

import argparse
import copy
import json
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(
    Path(__file__).parent.parent / "gcp-credentials.json"
)

sys.path.insert(0, str(Path(__file__).parent.parent))
from dags.utils.bigquery_client import query_bigquery, write_to_bigquery

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

CHAOS_LOG = Path(__file__).parent / "chaos_log.json"
DEFAULT_VARIANT = "rename_field"


# =============================================================================
# Drift mutations
# =============================================================================

def _mutate_weather_sf(raw: dict, variant: str) -> tuple[dict, str]:
    """
    Apply a drift mutation to a weather_sf raw_data dict.

    Returns: (mutated_dict, human-readable description)
    """
    mutated = copy.deepcopy(raw)

    if variant == "rename_field":
        # Rename hourly.temperature_2m → hourly.temp_celsius
        # Also rename the units key to keep the structure consistent
        hourly = mutated.get("hourly", {})
        if "temperature_2m" in hourly:
            hourly["temp_celsius"] = hourly.pop("temperature_2m")
        units = mutated.get("hourly_units", {})
        if "temperature_2m" in units:
            units["temp_celsius"] = units.pop("temperature_2m")
        description = (
            "Renamed hourly.temperature_2m → hourly.temp_celsius "
            "(+ hourly_units.temperature_2m → hourly_units.temp_celsius). "
            "Guardian detects: field_removed(temperature_2m) + field_added(temp_celsius)."
        )

    elif variant == "remove_field":
        # Remove hourly.precipitation entirely
        mutated.get("hourly", {}).pop("precipitation", None)
        mutated.get("hourly_units", {}).pop("precipitation", None)
        description = (
            "Removed hourly.precipitation (and hourly_units.precipitation). "
            "Guardian detects: field_removed(hourly.precipitation). "
            "LLM should COALESCE with NULL, preserving precipitation_mm column."
        )

    elif variant == "add_field":
        # Add hourly.uv_index — dummy array same length as other hourly arrays
        hourly = mutated.get("hourly", {})
        n = len(hourly.get("time", []))
        hourly["uv_index"] = [round(i % 11 * 0.5, 1) for i in range(n)]
        mutated.get("hourly_units", {})["uv_index"] = "index"
        description = (
            "Added hourly.uv_index array. "
            "Guardian detects: field_added(hourly.uv_index). "
            "LLM should not add a new column — field_added causes no breakage."
        )

    else:
        raise ValueError(f"Unknown variant '{variant}' for weather_sf")

    return mutated, description


def _mutate_transit_sf(raw: dict, variant: str) -> tuple[dict, str]:
    """
    Apply a drift mutation to a transit_sf raw_data dict.

    Returns: (mutated_dict, human-readable description)
    """
    mutated = copy.deepcopy(raw)
    entities = mutated.get("Entities", [])

    if variant == "rename_field":
        # Deep rename: TripUpdate → TripData in every entity
        # This changes ALL paths under Entities[].TripUpdate.* simultaneously —
        # the most dramatic demo variant, showing multi-path change handling.
        for entity in entities:
            if "TripUpdate" in entity:
                entity["TripData"] = entity.pop("TripUpdate")
        description = (
            "Renamed TripUpdate → TripData in all Entities. "
            "Guardian detects: all Entities[].TripUpdate.* paths removed, "
            "all Entities[].TripData.* paths added (8+ field changes). "
            "LLM must update all JSON extraction paths while preserving output columns."
        )

    elif variant == "remove_field":
        # Remove Departure from every StopTimeUpdate
        for entity in entities:
            for stu in entity.get("TripUpdate", {}).get("StopTimeUpdates", []):
                stu.pop("Departure", None)
        description = (
            "Removed Departure from all StopTimeUpdates. "
            "Guardian detects: field_removed(Entities[].TripUpdate.StopTimeUpdates[].Departure). "
            "LLM should COALESCE departure_delay_seconds with NULL."
        )

    elif variant == "add_field":
        # Add DirectionName alongside existing DirectionId in each Trip
        for entity in entities:
            trip = entity.get("TripUpdate", {}).get("Trip", {})
            if "DirectionId" in trip:
                trip["DirectionName"] = "Inbound" if trip["DirectionId"] == 0 else "Outbound"
        description = (
            "Added Trip.DirectionName to all TripUpdate.Trip objects. "
            "Guardian detects: field_added(Entities[].TripUpdate.Trip.DirectionName). "
            "No breakage — field_added is harmless to existing columns."
        )

    else:
        raise ValueError(f"Unknown variant '{variant}' for transit_sf")

    return mutated, description


def _mutate_incidents_sf(raw: list, variant: str) -> tuple[list, str]:
    """
    Apply a drift mutation to an incidents_sf raw_data list (array of objects).

    Returns: (mutated_list, human-readable description)
    """
    mutated = copy.deepcopy(raw)

    if variant == "rename_field":
        # Rename status_description → status in every incident record
        for incident in mutated:
            if "status_description" in incident:
                incident["status"] = incident.pop("status_description")
        description = (
            "Renamed status_description → status in all incident records. "
            "Guardian detects: field_removed(status_description) + field_added(status). "
            "LLM should update JSON path from $.status_description to $.status, "
            "keeping output column name 'status' unchanged."
        )

    elif variant == "remove_field":
        # Remove neighborhoods_sffind_boundaries from every incident
        for incident in mutated:
            incident.pop("neighborhoods_sffind_boundaries", None)
        description = (
            "Removed neighborhoods_sffind_boundaries from all incident records. "
            "Guardian detects: field_removed(neighborhoods_sffind_boundaries). "
            "LLM should COALESCE neighborhood column with NULL."
        )

    elif variant == "add_field":
        # Add priority field to every incident
        for incident in mutated:
            incident["priority"] = "Normal"
        description = (
            "Added priority='Normal' to all incident records. "
            "Guardian detects: field_added(priority). "
            "No breakage — field_added is harmless to existing columns."
        )

    else:
        raise ValueError(f"Unknown variant '{variant}' for incidents_sf")

    return mutated, description


def _apply_mutation(source_name: str, raw_data: str, variant: str) -> tuple[str, str]:
    """
    Parse raw_data, apply the mutation, return (mutated_json, description).

    incidents_sf raw_data is a JSON array; all others are JSON objects.
    """
    parsed = json.loads(raw_data)

    if source_name == "weather_sf":
        mutated, description = _mutate_weather_sf(parsed, variant)
    elif source_name == "transit_sf":
        mutated, description = _mutate_transit_sf(parsed, variant)
    elif source_name == "incidents_sf":
        if not isinstance(parsed, list) or len(parsed) == 0:
            raise ValueError(
                "incidents_sf raw_data is empty — run the incidents ingestion DAG first."
            )
        mutated, description = _mutate_incidents_sf(parsed, variant)
    else:
        raise ValueError(f"Unknown source: {source_name}")

    return json.dumps(mutated), description


# =============================================================================
# chaos_log.json helpers
# =============================================================================

def _read_log() -> list:
    if not CHAOS_LOG.exists():
        return []
    try:
        return json.loads(CHAOS_LOG.read_text())
    except (json.JSONDecodeError, OSError):
        return []


def _write_log(entries: list) -> None:
    CHAOS_LOG.write_text(json.dumps(entries, indent=2))


def _append_log(entry: dict) -> None:
    entries = _read_log()
    entries.append(entry)
    _write_log(entries)


# =============================================================================
# Commands
# =============================================================================

def cmd_inject(source_name: str, variant: str) -> None:
    """Inject a schema drift mutation into raw.{source_name}."""
    print(f"\nChaos Engine — Injecting schema drift")
    print(f"  Source:  {source_name}")
    print(f"  Variant: {variant}")

    # 1. Fetch latest real row
    print(f"\nFetching latest row from raw.{source_name} ...")
    rows = list(query_bigquery(
        f"SELECT raw_data, source, ingested_at "
        f"FROM `raw.{source_name}` "
        f"ORDER BY ingested_at DESC LIMIT 1"
    ))
    if not rows:
        print(f"  ERROR: No rows found in raw.{source_name}. Run the ingestion DAG first.")
        sys.exit(1)

    real_row = rows[0]
    print(f"  Real row ingested_at: {real_row.ingested_at}")

    # 2. Apply mutation
    mutated_json, description = _apply_mutation(source_name, real_row.raw_data, variant)

    # 3. Build the injected row — ingested_at must be NEWER than the real row
    injected_at = datetime.now(timezone.utc).isoformat()
    injection_id = str(uuid.uuid4())

    # 4. Log BEFORE writing to BigQuery (so cleanup is possible even if BQ write fails)
    log_entry = {
        "injection_id":       injection_id,
        "source_name":        source_name,
        "variant":            variant,
        "description":        description,
        "injected_at":        injected_at,
        "table":              f"raw.{source_name}",
        "ingested_at_marker": injected_at,
    }
    _append_log(log_entry)
    print(f"\nLogged to chaos_log.json (injection_id={injection_id})")

    # 5. Write mutated row to BigQuery
    write_to_bigquery("raw", source_name, [{
        "ingested_at": injected_at,
        "source":      real_row.source,
        "raw_data":    mutated_json,
    }])

    # 6. Print summary
    print(f"\n{'=' * 60}")
    print(f"INJECTION COMPLETE")
    print(f"{'=' * 60}")
    print(f"  Injection ID: {injection_id}")
    print(f"  Table:        raw.{source_name}")
    print(f"  Injected at:  {injected_at}")
    print(f"\nWhat was changed:")
    print(f"  {description}")
    print(f"\nWhat Schema Guardian should detect:")
    print(f"  Run: python -c \"from agents.schema_guardian import run_guardian; import json; print(json.dumps(run_guardian('{source_name}'), indent=2, default=str))\"")
    print(f"\nTo clean up: python chaos/chaos_mode.py --reset")


def cmd_reset() -> None:
    """Attempt to delete all injected rows and clear chaos_log.json."""
    entries = _read_log()
    if not entries:
        print("No active chaos injections — nothing to reset.")
        return

    print(f"\nChaos Engine — Reset")
    print(f"  Active injections: {len(entries)}")
    print(f"\n  WARNING: BigQuery streaming inserts land in a buffer.")
    print(f"  Rows inserted within the last ~90 minutes may not be")
    print(f"  immediately deletable. The DELETE will be issued but may")
    print(f"  have no effect until the buffer clears.")
    print(f"\n  IMPORTANT: After reset, the schema_metadata baseline still")
    print(f"  reflects the injected drift. The next run of Schema Guardian")
    print(f"  will detect the 'drift back to normal' and may trigger another")
    print(f"  repair. This is expected behaviour — the system detects change")
    print(f"  in both directions.")

    print(f"\nAttempting cleanup...")
    for entry in entries:
        source_name = entry["source_name"]
        marker      = entry["ingested_at_marker"]
        variant     = entry["variant"]
        print(f"\n  [{source_name} / {variant}] ingested_at='{marker}'")
        try:
            list(query_bigquery(
                f"DELETE FROM `raw.{source_name}` "
                f"WHERE ingested_at = TIMESTAMP('{marker}')"
            ))
            print(f"    DELETE issued (may be deferred by streaming buffer).")
        except Exception as e:
            print(f"    DELETE failed (non-blocking): {e}")
            print(f"    Row will clear from streaming buffer automatically.")

    _write_log([])
    print(f"\nchaos_log.json cleared.")
    print(f"\nReset complete. Run --status to confirm.")


def cmd_status() -> None:
    """Print all active injections from chaos_log.json."""
    entries = _read_log()
    if not entries:
        print("No active chaos injections.")
        return

    print(f"\nActive chaos injections: {len(entries)}")
    print(f"{'─' * 60}")
    for i, entry in enumerate(entries, 1):
        print(f"\n  [{i}] {entry['source_name']} / {entry['variant']}")
        print(f"      Injected at:  {entry['injected_at']}")
        print(f"      Injection ID: {entry['injection_id']}")
        print(f"      Description:  {entry['description']}")
    print(f"\nTo clean up: python chaos/chaos_mode.py --reset")


# =============================================================================
# CLI entry point
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Chaos Engine — controlled schema drift injection for Schema Guardian testing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python chaos/chaos_mode.py --inject schema_drift --source weather_sf
  python chaos/chaos_mode.py --inject schema_drift --source weather_sf --variant remove_field
  python chaos/chaos_mode.py --inject schema_drift --source transit_sf
  python chaos/chaos_mode.py --inject schema_drift --source incidents_sf --variant add_field
  python chaos/chaos_mode.py --reset
  python chaos/chaos_mode.py --status

Variants: rename_field (default) | remove_field | add_field
Sources:  weather_sf | transit_sf | incidents_sf
        """,
    )

    parser.add_argument(
        "--inject",
        metavar="TYPE",
        help="Injection type — only 'schema_drift' is supported",
    )
    parser.add_argument(
        "--source",
        metavar="SOURCE",
        help="Source name: weather_sf | transit_sf | incidents_sf",
    )
    parser.add_argument(
        "--variant",
        metavar="VARIANT",
        default=DEFAULT_VARIANT,
        help="Drift variant: rename_field (default) | remove_field | add_field",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Attempt to delete all injected rows and clear chaos_log.json",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Print all active injections",
    )

    args = parser.parse_args()

    if args.status:
        cmd_status()

    elif args.reset:
        cmd_reset()

    elif args.inject:
        if args.inject != "schema_drift":
            print(f"ERROR: Only 'schema_drift' injection is supported. Got: {args.inject}")
            sys.exit(1)
        if not args.source:
            print("ERROR: --source is required with --inject")
            sys.exit(1)
        if args.source not in ("weather_sf", "transit_sf", "incidents_sf"):
            print(f"ERROR: Unknown source '{args.source}'. Use: weather_sf | transit_sf | incidents_sf")
            sys.exit(1)
        if args.variant not in ("rename_field", "remove_field", "add_field"):
            print(f"ERROR: Unknown variant '{args.variant}'. Use: rename_field | remove_field | add_field")
            sys.exit(1)
        cmd_inject(args.source, args.variant)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
