/*
Derived from stg_incidents_sf.
One row per distinct neighborhood (neighborhoods_sffind_boundaries field in raw).
Centroid coordinates are approximated from the average lat/lon of incidents in each neighborhood.
Rows with null neighborhood are excluded.
*/

SELECT
    neighborhood,
    AVG(latitude)    AS avg_latitude,
    AVG(longitude)   AS avg_longitude,
    COUNT(*)         AS incident_count
FROM {{ ref('stg_incidents_sf') }}
WHERE neighborhood IS NOT NULL
GROUP BY neighborhood
