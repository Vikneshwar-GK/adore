/*
Grain: one row per hour.
Source: int_hourly_weather_transit enriched with dim_date fields.
Purpose: Dashboard-ready table for weather impact on transit analysis.
  Adds date, hour, day_of_week, is_weekend, is_rush_hour from dim_date
  so dashboards can filter without joining.
FK: date_hour -> dim_date.
*/

SELECT
    i.date_hour,
    d.date,
    d.hour,
    d.day_of_week,
    d.is_weekend,
    d.is_rush_hour,
    i.temperature_c,
    i.precipitation_mm,
    i.wind_speed_kmh,
    i.humidity_pct,
    i.avg_delay_seconds,
    i.max_delay_seconds,
    i.total_trips,
    i.total_stop_updates,
    i.on_time_pct
FROM {{ ref('int_hourly_weather_transit') }} i
LEFT JOIN {{ ref('dim_date') }} d ON d.date_hour = i.date_hour
