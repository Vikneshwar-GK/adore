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
# AGENTS LAYER — added by Task 13
# =============================================================================

SCHEMA_METADATA_SCHEMA = [
    bigquery.SchemaField("source_name", "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("field_path",  "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("field_type",  "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("detected_at", "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("is_active",   "BOOLEAN",   mode="REQUIRED"),
]

AGENT_EVENTS_SCHEMA = [
    bigquery.SchemaField("event_id",           "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("agent_name",         "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("event_type",         "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("source_name",        "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("severity",           "STRING",    mode="NULLABLE"),
    bigquery.SchemaField("details",            "STRING",    mode="NULLABLE"),
    bigquery.SchemaField("detected_at",        "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("resolved_at",        "TIMESTAMP", mode="NULLABLE"),
    bigquery.SchemaField("notification_sent",  "BOOLEAN",   mode="NULLABLE"),
]

AGENT_REPAIRS_SCHEMA = [
    bigquery.SchemaField("repair_id",         "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("event_id",          "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("source_name",       "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("old_sql",           "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("new_sql",           "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("old_schema",        "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("new_schema",        "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("impact_analysis",   "STRING",    mode="NULLABLE"),
    bigquery.SchemaField("data_assessment",   "STRING",    mode="NULLABLE"),
    bigquery.SchemaField("validation_result", "STRING",    mode="NULLABLE"),
    bigquery.SchemaField("status",            "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("proposed_at",       "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("approved_at",       "TIMESTAMP", mode="NULLABLE"),
    bigquery.SchemaField("deployed_at",       "TIMESTAMP", mode="NULLABLE"),
    bigquery.SchemaField("user_notes",        "STRING",    mode="NULLABLE"),
]

SCHEMA_CHANGE_LOG_SCHEMA = [
    bigquery.SchemaField("change_id",   "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("source_name", "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("change_type", "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("field_path",  "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("old_value",   "STRING",    mode="NULLABLE"),
    bigquery.SchemaField("new_value",   "STRING",    mode="NULLABLE"),
    bigquery.SchemaField("detected_at", "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("repair_id",   "STRING",    mode="NULLABLE"),
]