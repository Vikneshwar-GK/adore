from google.cloud import bigquery

# =============================================================================
# RAW LAYER (Bronze)
# All raw ingestion tables share the same schema.
# Source API payloads are stored as JSON strings in raw_data.
# =============================================================================

RAW_TABLE_SCHEMA = [
    bigquery.SchemaField("ingested_at", "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("source", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("raw_data", "STRING", mode="REQUIRED"),
]

# =============================================================================
# STAGING LAYER (Silver) — added by Task 11
# =============================================================================

# =============================================================================
# WAREHOUSE LAYER (Gold) — added by Task 12
# =============================================================================

# =============================================================================
# AGENTS LAYER — added by Task 13
# =============================================================================