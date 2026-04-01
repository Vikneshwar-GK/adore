/*
Grain: one row per date.
Purpose: "Does weather drive 311 complaint volume?" — daily weather summary joined with
daily incident counts.

Left side (weather): stg_weather_sf aggregated from hourly to daily.
  total_precip_mm: SUM of hourly precipitation (not average — accumulation is meaningful).
  max_wind_speed_kmh: MAX across hours of the day.
Right side (incidents): stg_incidents_sf aggregated by DATE(requested_datetime).
  top_category: the service_name with the highest incident count that day.
    Computed via ROW_NUMBER() PARTITION BY date ORDER BY count DESC — ties broken by
    alphabetical service_name for determinism.

Join: LEFT JOIN incidents onto weather so every day with weather data is preserved,
even days with no 311 activity.
*/

WITH weather_daily AS (
    SELECT
        DATE(recorded_at)            AS date,
        AVG(temperature_c)           AS avg_temp_c,
        SUM(precipitation_mm)        AS total_precip_mm,
        MAX(wind_speed_kmh)          AS max_wind_speed_kmh,
        AVG(humidity_pct)            AS avg_humidity_pct
    FROM {{ ref('stg_weather_sf') }}
    GROUP BY DATE(recorded_at)
),

incident_counts AS (
    SELECT
        DATE(requested_datetime)     AS date,
        service_name,
        COUNT(*)                     AS cnt
    FROM {{ ref('stg_incidents_sf') }}
    GROUP BY DATE(requested_datetime), service_name
),

top_category AS (
    SELECT
        date,
        service_name                 AS top_category,
        ROW_NUMBER() OVER (
            PARTITION BY date
            ORDER BY cnt DESC, service_name ASC
        )                            AS rn
    FROM incident_counts
),

incidents_daily AS (
    SELECT
        DATE(requested_datetime)                   AS date,
        COUNT(*)                                   AS total_incidents,
        COUNTIF(LOWER(status) != 'closed')         AS open_incidents,
        COUNTIF(LOWER(status) = 'closed')          AS closed_incidents
    FROM {{ ref('stg_incidents_sf') }}
    GROUP BY DATE(requested_datetime)
)

SELECT
    w.date,
    w.avg_temp_c,
    w.total_precip_mm,
    w.max_wind_speed_kmh,
    w.avg_humidity_pct,
    i.total_incidents,
    i.open_incidents,
    i.closed_incidents,
    tc.top_category
FROM weather_daily w
LEFT JOIN incidents_daily i USING (date)
LEFT JOIN top_category tc ON tc.date = w.date AND tc.rn = 1
