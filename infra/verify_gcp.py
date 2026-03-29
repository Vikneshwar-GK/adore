import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from google.cloud import bigquery

load_dotenv(Path(__file__).parent.parent / ".env")

project_id = os.environ.get("GCP_PROJECT_ID")
credentials_path = os.environ.get("GCP_CREDENTIALS_PATH")

if not project_id:
    print("ERROR: GCP_PROJECT_ID not set in .env")
    sys.exit(1)

if not credentials_path:
    print("ERROR: GCP_CREDENTIALS_PATH not set in .env")
    sys.exit(1)

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(
    Path(__file__).parent.parent / credentials_path.lstrip("./")
)

try:
    client = bigquery.Client(project=project_id)
    results = list(client.query("SELECT 1 AS ok").result())
    assert results[0].ok == 1
    print(f"SUCCESS: Connected to BigQuery project '{project_id}'")
except Exception as e:
    print(f"ERROR: BigQuery connection failed — {e}")
    sys.exit(1)