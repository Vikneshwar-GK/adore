/*
Derived from stg_transit_sf.
One row per distinct stop_id.
When a stop appears on multiple routes, the most frequently observed route is used.
NOTE: GTFS-RT does not provide stop names or coordinates — only IDs.
Name/coordinate resolution would require a separate GTFS static feed.
*/

WITH stop_route_counts AS (
    SELECT
        stop_id,
        route_id,
        COUNT(*) AS observation_count
    FROM {{ ref('stg_transit_sf') }}
    WHERE stop_id IS NOT NULL AND route_id IS NOT NULL
    GROUP BY stop_id, route_id
),

ranked AS (
    SELECT
        stop_id,
        route_id,
        ROW_NUMBER() OVER (PARTITION BY stop_id ORDER BY observation_count DESC) AS rn
    FROM stop_route_counts
),

primary_route AS (
    SELECT stop_id, route_id
    FROM ranked
    WHERE rn = 1
),

stop_timestamps AS (
    SELECT
        stop_id,
        MIN(recorded_at) AS first_seen,
        MAX(recorded_at) AS last_seen
    FROM {{ ref('stg_transit_sf') }}
    WHERE stop_id IS NOT NULL
    GROUP BY stop_id
)

SELECT
    st.stop_id,
    pr.route_id,
    st.first_seen,
    st.last_seen
FROM stop_timestamps st
LEFT JOIN primary_route pr USING (stop_id)
