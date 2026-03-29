import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from google.cloud import bigquery
from google.cloud.exceptions import Conflict

load_dotenv(Path(__file__).parent.parent / ".env")

PROJECT_ID = os.environ.get("GCP_PROJECT_ID")
REGION = os.environ.get("GCP_REGION")
CREDENTIALS_PATH = os.environ.get("GCP_CREDENTIALS_PATH")

if not all([PROJECT_ID, REGION, CREDENTIALS_PATH]):
    print("ERROR: GCP_PROJECT_ID, GCP_REGION, and GCP_CREDENTIALS_PATH must all be set in .env")
    sys.exit(1)

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(
    Path(__file__).parent.parent / CREDENTIALS_PATH.lstrip("./")
)

# Import schemas from single source of truth
sys.path.insert(0, str(Path(__file__).parent.parent))
from dags.utils.schemas import RAW_TABLE_SCHEMA

client = bigquery.Client(project=PROJECT_ID)

# =============================================================================
# Datasets
# =============================================================================

DATASETS = ["raw", "staging", "warehouse", "agents"]

print(f"\nProject: {PROJECT_ID} | Region: {REGION}")
print("=" * 50)
print("Creating datasets...")

for dataset_id in DATASETS:
    full_id = f"{PROJECT_ID}.{dataset_id}"
    dataset = bigquery.Dataset(full_id)
    dataset.location = REGION
    try:
        client.create_dataset(dataset)
        print(f"  [CREATED]  {dataset_id}")
    except Conflict:
        print(f"  [EXISTS]   {dataset_id}")

# =============================================================================
# Raw tables
# =============================================================================

RAW_TABLES = ["weather_sf", "transit_sf", "incidents_sf"]

print("\nCreating raw tables...")

for table_name in RAW_TABLES:
    table_ref = f"{PROJECT_ID}.raw.{table_name}"
    table = bigquery.Table(table_ref, schema=RAW_TABLE_SCHEMA)
    try:
        client.create_table(table)
        print(f"  [CREATED]  raw.{table_name}")
    except Conflict:
        print(f"  [EXISTS]   raw.{table_name}")

print("\nDone.")