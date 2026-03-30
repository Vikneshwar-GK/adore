/*
Raw JSON structure (from raw.transit_sf) — GTFS-RT with PascalCase keys:
{
  "Header": { "Timestamp": 1774873257 },
  "Entities": [
    {
      "Id": "11947822_M21",
      "TripUpdate": {
        "Trip": {
          "TripId": "11947822_M21",
          "RouteId": "1",
          "DirectionId": 0,
          "StartDate": "20260330"
        },
        "Timestamp": 1774873252,
        "StopTimeUpdates": [
          {
            "StopSequence": 20,
            "StopId": "13550",
            "Arrival":   { "Delay": -192, "Time": 1774873290 },
            "Departure": null
          }
        ]
      }
    }
  ]
}
NOTE: Keys are PascalCase (Entities, TripUpdate, StopTimeUpdates, etc.), not standard lowercase GTFS-RT.
Departure is frequently null — use SAFE_CAST.
Timestamps are Unix epoch seconds.
Deduplication: keep latest ingested_at per (trip_id, stop_id, recorded_at).
*/

WITH base AS (
    SELECT ingested_at, raw_data
    FROM {{ source('raw', 'transit_sf') }}
),

entities AS (
    SELECT
        base.ingested_at,
        entity
    FROM base,
    UNNEST(JSON_EXTRACT_ARRAY(base.raw_data, '$.Entities')) AS entity
),

stop_updates AS (
    SELECT
        e.ingested_at,
        JSON_VALUE(e.entity, '$.TripUpdate.Trip.TripId')  AS trip_id,
        JSON_VALUE(e.entity, '$.TripUpdate.Trip.RouteId') AS route_id,
        TIMESTAMP_SECONDS(
            CAST(JSON_VALUE(e.entity, '$.TripUpdate.Timestamp') AS INT64)
        ) AS recorded_at,
        stop
    FROM entities e,
    UNNEST(JSON_EXTRACT_ARRAY(e.entity, '$.TripUpdate.StopTimeUpdates')) AS stop
),

parsed AS (
    SELECT
        trip_id,
        route_id,
        JSON_VALUE(stop, '$.StopId')                              AS stop_id,
        SAFE_CAST(JSON_VALUE(stop, '$.Arrival.Delay')   AS INT64) AS arrival_delay_seconds,
        SAFE_CAST(JSON_VALUE(stop, '$.Departure.Delay') AS INT64) AS departure_delay_seconds,
        recorded_at,
        ingested_at,
        ROW_NUMBER() OVER (
            PARTITION BY trip_id, JSON_VALUE(stop, '$.StopId'), recorded_at
            ORDER BY ingested_at DESC
        ) AS rn
    FROM stop_updates
    WHERE trip_id IS NOT NULL
)

SELECT
    trip_id,
    route_id,
    stop_id,
    arrival_delay_seconds,
    departure_delay_seconds,
    recorded_at,
    ingested_at
FROM parsed
WHERE rn = 1
