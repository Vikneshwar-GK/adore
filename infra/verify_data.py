import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from google.cloud import bigquery

load_dotenv(Path(__file__).parent.parent / ".env")
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(
    Path(__file__).parent.parent / "gcp-credentials.json"
)

client = bigquery.Client(project="adore-pipeline-v2")


def q(sql):
    return list(client.query(sql).result())


print("=" * 60)
print("RAW LAYER")
print("=" * 60)

for table in ["weather_sf", "transit_sf", "incidents_sf"]:
    rows = q(f"""
        SELECT
            COUNT(*) as total_rows,
            MIN(ingested_at) as first_ingestion,
            MAX(ingested_at) as last_ingestion
        FROM raw.{table}
    """)
    r = rows[0]
    print(f"raw.{table}:")
    print(f"  rows={r.total_rows}, first={r.first_ingestion}, last={r.last_ingestion}")

print()
print("=" * 60)
print("STAGING LAYER")
print("=" * 60)

rows = q("""
    SELECT
        COUNT(*) as row_count,
        MIN(recorded_at) as earliest,
        MAX(recorded_at) as latest,
        ROUND(AVG(temperature_c), 1) as avg_temp,
        MIN(temperature_c) as min_temp,
        MAX(temperature_c) as max_temp,
        COUNTIF(temperature_c IS NULL) as null_temps
    FROM staging.stg_weather_sf
""")
r = rows[0]
print("stg_weather_sf:")
print(f"  rows={r.row_count}, earliest={r.earliest}, latest={r.latest}")
print(f"  temp: avg={r.avg_temp}°C, min={r.min_temp}°C, max={r.max_temp}°C, nulls={r.null_temps}")

rows = q("""
    SELECT
        COUNT(*) as row_count,
        COUNT(DISTINCT route_id) as routes,
        COUNT(DISTINCT trip_id) as trips,
        ROUND(AVG(arrival_delay_seconds), 1) as avg_delay,
        MIN(arrival_delay_seconds) as min_delay,
        MAX(arrival_delay_seconds) as max_delay
    FROM staging.stg_transit_sf
    WHERE arrival_delay_seconds IS NOT NULL
""")
r = rows[0]
print("stg_transit_sf:")
print(f"  rows={r.row_count}, routes={r.routes}, trips={r.trips}")
print(f"  delay: avg={r.avg_delay}s, min={r.min_delay}s, max={r.max_delay}s")

rows = q("""
    SELECT
        COUNT(*) as row_count,
        COUNT(DISTINCT neighborhood) as neighborhoods,
        MIN(latitude) as min_lat,
        MAX(latitude) as max_lat,
        MIN(longitude) as min_lon,
        MAX(longitude) as max_lon,
        COUNTIF(latitude IS NULL) as null_coords
    FROM staging.stg_incidents_sf
""")
r = rows[0]
print("stg_incidents_sf:")
print(f"  rows={r.row_count}, neighborhoods={r.neighborhoods}, null_coords={r.null_coords}")
print(f"  lat: {r.min_lat:.4f} to {r.max_lat:.4f}, lon: {r.min_lon:.4f} to {r.max_lon:.4f}")

print()
print("=" * 60)
print("WAREHOUSE LAYER")
print("=" * 60)

rows = q("""
    SELECT
        COUNT(*) as total_hours,
        COUNTIF(is_rush_hour) as rush_hours,
        COUNTIF(is_weekend) as weekend_hours
    FROM warehouse.dim_date
""")
r = rows[0]
print(f"dim_date: total_hours={r.total_hours}, rush_hours={r.rush_hours}, weekend_hours={r.weekend_hours}")

rows = q("""
    SELECT
        COUNT(*) as row_count,
        ROUND(AVG(avg_delay_seconds), 1) as avg_delay,
        ROUND(AVG(on_time_pct), 1) as avg_on_time_pct,
        MIN(on_time_pct) as min_on_time,
        MAX(on_time_pct) as max_on_time
    FROM warehouse.fact_transit_performance
""")
r = rows[0]
print(f"fact_transit_performance: rows={r.row_count}, avg_delay={r.avg_delay}s, avg_on_time={r.avg_on_time_pct}%")

rows = q("""
    SELECT service_name, SUM(incident_count) as total
    FROM warehouse.fact_incident_trends
    GROUP BY service_name
    ORDER BY total DESC
    LIMIT 5
""")
print("fact_incident_trends — top 5 incident types:")
for r in rows:
    print(f"  {r.service_name}: {r.total}")

print()
print("All checks complete.")
