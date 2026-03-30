/*
Raw JSON structure (from raw.weather_sf):
{
  "hourly": {
    "time":                  ["2026-03-30T00:00", "2026-03-30T01:00", ...],  -- 168 hours (7 days)
    "temperature_2m":        [13.4, 12.8, ...],
    "precipitation":         [0.0, 0.0, ...],
    "wind_speed_10m":        [3.5, 4.1, ...],
    "relative_humidity_2m":  [72, 75, ...]
  }
}
All arrays are parallel (same length). One API response covers 7 days of hourly forecasts.
UNNEST strategy: GENERATE_ARRAY indices to zip parallel arrays.
Deduplication: multiple ingestion runs overlap on the same hours — keep latest ingested_at per hour.
*/

WITH base AS (
    SELECT ingested_at, raw_data
    FROM {{ source('raw', 'weather_sf') }}
),

unnested AS (
    SELECT
        base.ingested_at,
        PARSE_TIMESTAMP(
            '%Y-%m-%dT%H:%M',
            JSON_VALUE(JSON_EXTRACT_ARRAY(base.raw_data, '$.hourly.time')[SAFE_OFFSET(idx)])
        ) AS recorded_at,
        CAST(
            JSON_VALUE(JSON_EXTRACT_ARRAY(base.raw_data, '$.hourly.temperature_2m')[SAFE_OFFSET(idx)])
            AS FLOAT64
        ) AS temperature_c,
        CAST(
            JSON_VALUE(JSON_EXTRACT_ARRAY(base.raw_data, '$.hourly.precipitation')[SAFE_OFFSET(idx)])
            AS FLOAT64
        ) AS precipitation_mm,
        CAST(
            JSON_VALUE(JSON_EXTRACT_ARRAY(base.raw_data, '$.hourly.wind_speed_10m')[SAFE_OFFSET(idx)])
            AS FLOAT64
        ) AS wind_speed_kmh,
        CAST(
            JSON_VALUE(JSON_EXTRACT_ARRAY(base.raw_data, '$.hourly.relative_humidity_2m')[SAFE_OFFSET(idx)])
            AS FLOAT64
        ) AS humidity_pct
    FROM base,
    UNNEST(
        GENERATE_ARRAY(
            0,
            ARRAY_LENGTH(JSON_EXTRACT_ARRAY(base.raw_data, '$.hourly.time')) - 1
        )
    ) AS idx
),

deduplicated AS (
    SELECT
        *,
        ROW_NUMBER() OVER (PARTITION BY recorded_at ORDER BY ingested_at DESC) AS rn
    FROM unnested
    WHERE recorded_at IS NOT NULL
)

SELECT
    recorded_at,
    temperature_c,
    precipitation_mm,
    wind_speed_kmh,
    humidity_pct,
    ingested_at
FROM deduplicated
WHERE rn = 1
