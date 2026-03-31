/*
Grain: one row per route per hour.
Source: stg_transit_sf.
on_time_pct: proportion of stop updates where arrival_delay is between -60s and 300s (5 min).
Only stop updates with non-null arrival_delay_seconds are included in aggregations.
FK: date_hour -> dim_date, route_id -> dim_route.
*/

SELECT
    TIMESTAMP_TRUNC(recorded_at, HOUR)                              AS date_hour,
    route_id,
    AVG(arrival_delay_seconds)                                      AS avg_delay_seconds,
    MAX(arrival_delay_seconds)                                      AS max_delay_seconds,
    COUNT(DISTINCT trip_id)                                         AS trip_count,
    COUNT(*)                                                        AS stop_update_count,
    ROUND(
        COUNTIF(arrival_delay_seconds BETWEEN -60 AND 300) * 100.0
        / COUNT(*),
        2
    )                                                               AS on_time_pct
FROM {{ ref('stg_transit_sf') }}
WHERE arrival_delay_seconds IS NOT NULL
GROUP BY
    TIMESTAMP_TRUNC(recorded_at, HOUR),
    route_id
