/*
Grain: one row per date per neighborhood per service_name.
Source: stg_incidents_sf.
avg_resolution_hours: NULL — closed_datetime is not present in the SF 311 API response
  and was not included in stg_incidents_sf. This field is a placeholder for when/if
  the API exposes it. closed_count is still computed from status field.
FK: date -> dim_date (join on DATE(dim_date.date_hour)), neighborhood -> dim_neighborhood.
Rows with null neighborhood are excluded.
*/

SELECT
    DATE(requested_datetime)                                        AS date,
    neighborhood,
    service_name,
    COUNT(*)                                                        AS incident_count,
    CAST(NULL AS FLOAT64)                                           AS avg_resolution_hours,
    COUNTIF(LOWER(status) != 'closed')                             AS open_count,
    COUNTIF(LOWER(status) = 'closed')                              AS closed_count
FROM {{ ref('stg_incidents_sf') }}
WHERE neighborhood IS NOT NULL
GROUP BY
    DATE(requested_datetime),
    neighborhood,
    service_name
