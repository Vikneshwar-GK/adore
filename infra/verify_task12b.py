import os
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
print("INTERMEDIATE LAYER")
print("=" * 60)

result = q("""
    SELECT
        COUNT(*) AS total_hours,
        COUNTIF(avg_delay_seconds IS NOT NULL) AS hours_with_transit,
        COUNTIF(avg_delay_seconds IS NULL) AS hours_no_transit,
        ROUND(AVG(IF(avg_delay_seconds IS NOT NULL, avg_delay_seconds, NULL)), 1) AS avg_delay,
        ROUND(AVG(temperature_c), 1) AS avg_temp
    FROM warehouse.int_hourly_weather_transit
""")
r = result[0]
print("int_hourly_weather_transit:")
print(f"  total_hours={r.total_hours}, with_transit={r.hours_with_transit}, no_transit={r.hours_no_transit}")
print(f"  avg_delay={r.avg_delay}s, avg_temp={r.avg_temp}C")

result = q("""
    SELECT
        COUNT(*) AS total_days,
        COUNTIF(total_incidents IS NOT NULL) AS days_with_incidents,
        SUM(IFNULL(total_incidents, 0)) AS total_incidents,
        MIN(date) AS earliest,
        MAX(date) AS latest
    FROM warehouse.int_daily_weather_incidents
""")
r = result[0]
print("int_daily_weather_incidents:")
print(f"  total_days={r.total_days}, days_with_incidents={r.days_with_incidents}, total_incidents={r.total_incidents}")
print(f"  date_range={r.earliest} to {r.latest}")

print()
print("=" * 60)
print("CROSS-SOURCE FACT TABLES")
print("=" * 60)

result = q("""
    SELECT
        COUNT(*) AS row_count,
        COUNTIF(is_rush_hour) AS rush_hour_count,
        COUNTIF(is_weekend) AS weekend_count,
        COUNTIF(avg_delay_seconds IS NOT NULL) AS count_with_transit,
        COUNTIF(day_of_week IS NOT NULL) AS count_with_dim_date
    FROM warehouse.fact_weather_transit_hourly
""")
r = result[0]
print("fact_weather_transit_hourly:")
print(f"  row_count={r.row_count}, rush_hour={r.rush_hour_count}, weekend={r.weekend_count}")
print(f"  with_transit={r.count_with_transit}, dim_date_populated={r.count_with_dim_date}")

result = q("""
    SELECT
        COUNT(*) AS row_count,
        COUNTIF(avg_delay_seconds IS NOT NULL) AS days_with_transit,
        COUNTIF(total_incidents IS NOT NULL) AS days_with_incidents,
        MIN(date) AS earliest,
        MAX(date) AS latest
    FROM warehouse.fact_daily_city_summary
""")
r = result[0]
print("fact_daily_city_summary:")
print(f"  row_count={r.row_count}, with_transit={r.days_with_transit}, with_incidents={r.days_with_incidents}")
print(f"  date_range={r.earliest} to {r.latest}")

result = q("""
    SELECT date, avg_temp_c, avg_delay_seconds, total_incidents, top_category
    FROM warehouse.fact_daily_city_summary
    ORDER BY date
    LIMIT 5
""")
print("  sample rows (first 5):")
for r in result:
    print(f"    {r.date}: temp={r.avg_temp_c}C, delay={r.avg_delay_seconds}, incidents={r.total_incidents}, top={r.top_category}")

print()
print("All checks complete.")
