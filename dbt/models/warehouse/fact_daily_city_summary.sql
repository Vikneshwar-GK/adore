/*
Grain: one row per date — the "city pulse" table.
Purpose: Single daily summary combining all three sources for dashboard overview.

Sources:
  - int_daily_weather_incidents: weather (daily) + incident counts + top_category.
    Reused here to avoid duplicating the top_category window function logic.
  - stg_transit_sf: aggregated to daily grain directly (int_hourly_weather_transit
    is hourly — re-aggregating from staging is cleaner than double-aggregating).

Join strategy: FULL OUTER JOIN across weather+incidents and transit on date,
so any day present in either source is included.

Transit daily on_time_pct: computed from raw stop updates, consistent with
fact_transit_performance definition (arrival_delay_seconds BETWEEN -60 AND 300).
Only non-null arrival_delay_seconds rows are included.
*/

WITH weather_incidents AS (
    SELECT
        date,
        avg_temp_c,
        total_precip_mm,
        max_wind_speed_kmh,
        avg_humidity_pct,
        total_incidents,
        open_incidents,
        closed_incidents,
        top_category
    FROM {{ ref('int_daily_weather_incidents') }}
),

transit_daily AS (
    SELECT
        DATE(recorded_at)                                               AS date,
        AVG(arrival_delay_seconds)                                      AS avg_delay_seconds,
        COUNT(DISTINCT trip_id)                                         AS total_trips,
        COUNT(*)                                                        AS total_stop_updates,
        ROUND(
            COUNTIF(arrival_delay_seconds BETWEEN -60 AND 300) * 100.0
            / COUNT(*),
            2
        )                                                               AS daily_on_time_pct
    FROM {{ ref('stg_transit_sf') }}
    WHERE arrival_delay_seconds IS NOT NULL
    GROUP BY DATE(recorded_at)
)

SELECT
    COALESCE(wi.date, t.date)   AS date,
    wi.avg_temp_c,
    wi.total_precip_mm,
    wi.max_wind_speed_kmh,
    wi.avg_humidity_pct,
    t.avg_delay_seconds,
    t.total_trips,
    t.total_stop_updates,
    t.daily_on_time_pct,
    wi.total_incidents,
    wi.open_incidents,
    wi.closed_incidents,
    wi.top_category
FROM weather_incidents wi
FULL OUTER JOIN transit_daily t USING (date)
