/*
Generated date spine — NOT derived from source data.
Hourly grain to match weather and transit data.
Range: 2024-01-01 to 2026-12-31.
is_rush_hour: TRUE for hours 7-9 (morning) and 16-19 (evening).
day_of_week_num: 1=Monday, 7=Sunday (ISO convention).
*/

WITH hours AS (
    SELECT ts AS date_hour
    FROM UNNEST(
        GENERATE_TIMESTAMP_ARRAY(
            TIMESTAMP '2024-01-01 00:00:00',
            TIMESTAMP '2026-12-31 23:00:00',
            INTERVAL 1 HOUR
        )
    ) AS ts
)

SELECT
    date_hour,
    DATE(date_hour)                                              AS date,
    EXTRACT(HOUR FROM date_hour)                                 AS hour,
    FORMAT_TIMESTAMP('%A', date_hour)                            AS day_of_week,
    -- ISO: 1=Monday, 7=Sunday
    MOD(EXTRACT(DAYOFWEEK FROM date_hour) + 5, 7) + 1           AS day_of_week_num,
    MOD(EXTRACT(DAYOFWEEK FROM date_hour) + 5, 7) + 1 >= 6      AS is_weekend,
    EXTRACT(MONTH FROM date_hour)                                AS month,
    EXTRACT(YEAR FROM date_hour)                                 AS year,
    EXTRACT(HOUR FROM date_hour) BETWEEN 7 AND 9
        OR EXTRACT(HOUR FROM date_hour) BETWEEN 16 AND 19        AS is_rush_hour
FROM hours
