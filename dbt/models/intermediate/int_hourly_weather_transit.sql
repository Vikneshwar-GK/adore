/*
Grain: one row per hour.
Purpose: "Does weather affect transit delays?" — hourly weather conditions joined with
city-wide transit performance.

Left side (weather): stg_weather_sf — already deduplicated to one row per hour.
Right side (transit): stg_transit_sf aggregated city-wide (all routes) per hour.
  Only stop updates with non-null arrival_delay_seconds are included in transit aggregations.
  on_time_pct: % of stop updates with arrival_delay_seconds BETWEEN -60 AND 300.

Join: LEFT JOIN transit onto weather so every weather hour is preserved,
even hours with no transit data (late night, early morning).
*/

WITH weather AS (
    SELECT
        TIMESTAMP_TRUNC(recorded_at, HOUR) AS date_hour,
        temperature_c,
        precipitation_mm,
        wind_speed_kmh,
        humidity_pct
    FROM {{ ref('stg_weather_sf') }}
),

transit AS (
    SELECT
        TIMESTAMP_TRUNC(recorded_at, HOUR)                              AS date_hour,
        AVG(arrival_delay_seconds)                                      AS avg_delay_seconds,
        MAX(arrival_delay_seconds)                                      AS max_delay_seconds,
        COUNT(DISTINCT trip_id)                                         AS total_trips,
        COUNT(*)                                                        AS total_stop_updates,
        ROUND(
            COUNTIF(arrival_delay_seconds BETWEEN -60 AND 300) * 100.0
            / COUNT(*),
            2
        )                                                               AS on_time_pct
    FROM {{ ref('stg_transit_sf') }}
    WHERE arrival_delay_seconds IS NOT NULL
    GROUP BY TIMESTAMP_TRUNC(recorded_at, HOUR)
)

SELECT
    w.date_hour,
    w.temperature_c,
    w.precipitation_mm,
    w.wind_speed_kmh,
    w.humidity_pct,
    t.avg_delay_seconds,
    t.max_delay_seconds,
    t.total_trips,
    t.total_stop_updates,
    t.on_time_pct
FROM weather w
LEFT JOIN transit t USING (date_hour)
