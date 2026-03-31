/*
Derived from stg_transit_sf.
One row per distinct route_id observed in GTFS-RT feed.
NOTE: GTFS-RT TripUpdates does not provide route names — only IDs.
Do not fabricate route names. Name resolution would require a separate GTFS static feed.
*/

SELECT
    route_id,
    MIN(recorded_at) AS first_seen,
    MAX(recorded_at) AS last_seen
FROM {{ ref('stg_transit_sf') }}
WHERE route_id IS NOT NULL
GROUP BY route_id
