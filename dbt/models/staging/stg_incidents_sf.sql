/*
Raw JSON structure (from raw.incidents_sf) — JSON array of incident records:
[
  {
    "service_request_id": "101003771845",
    "requested_datetime":  "2026-03-29T23:08:07.000",   -- milliseconds, no timezone (UTC implied)
    "updated_datetime":    "2026-03-29T23:08:08.000",
    "status_description":  "Open",                       -- NOTE: field is status_description, not status
    "status_notes":        "open",
    "agency_responsible":  "Healthy Streets Operation Center",
    "service_name":        "Encampment",
    "service_subtype":     "encampment",
    "address":             "108 GOLDEN GATE AVE, SAN FRANCISCO, CA 94102",
    "lat":                 "37.78212307",                -- STRING, not float
    "long":                "-122.41248503",              -- STRING, not float
    "neighborhoods_sffind_boundaries": "Tenderloin",
    "source":              "Web"
  },
  ...
]
NOTE: closed_datetime is not present in the API response — omitted.
NOTE: lat/long are strings — use SAFE_CAST to FLOAT64.
NOTE: neighborhood field is neighborhoods_sffind_boundaries.
Deduplication: incidents appear in multiple daily pulls — keep latest ingested_at per service_request_id.
*/

WITH base AS (
    SELECT ingested_at, raw_data
    FROM {{ source('raw', 'incidents_sf') }}
),

unnested AS (
    SELECT
        base.ingested_at,
        incident
    FROM base,
    UNNEST(JSON_EXTRACT_ARRAY(base.raw_data)) AS incident
),

parsed AS (
    SELECT
        JSON_VALUE(incident, '$.service_request_id')                      AS service_request_id,
        PARSE_TIMESTAMP(
            '%Y-%m-%dT%H:%M:%E3S',
            JSON_VALUE(incident, '$.requested_datetime')
        )                                                                  AS requested_datetime,
        JSON_VALUE(incident, '$.status_description')                      AS status,
        JSON_VALUE(incident, '$.service_name')                            AS service_name,
        JSON_VALUE(incident, '$.agency_responsible')                      AS agency_responsible,
        JSON_VALUE(incident, '$.address')                                 AS address,
        SAFE_CAST(JSON_VALUE(incident, '$.lat')  AS FLOAT64)              AS latitude,
        SAFE_CAST(JSON_VALUE(incident, '$.long') AS FLOAT64)              AS longitude,
        JSON_VALUE(incident, '$.neighborhoods_sffind_boundaries')         AS neighborhood,
        JSON_VALUE(incident, '$.source')                                  AS source,
        ingested_at,
        ROW_NUMBER() OVER (
            PARTITION BY JSON_VALUE(incident, '$.service_request_id')
            ORDER BY ingested_at DESC
        ) AS rn
    FROM unnested
    WHERE JSON_VALUE(incident, '$.service_request_id') IS NOT NULL
)

SELECT
    service_request_id,
    requested_datetime,
    status,
    service_name,
    agency_responsible,
    address,
    latitude,
    longitude,
    neighborhood,
    source,
    ingested_at
FROM parsed
WHERE rn = 1
