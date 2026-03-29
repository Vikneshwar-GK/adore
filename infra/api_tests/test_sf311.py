import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")

APP_TOKEN = os.environ.get("SF311_APP_TOKEN")
if not APP_TOKEN:
    print("FAILURE: SF311_APP_TOKEN not set in .env")
    sys.exit(1)

URL = "https://data.sfgov.org/resource/vw6y-z8j6.json"

# Date format: %Y-%m-%dT%H:%M:%S — NO .000Z suffix, Socrata rejects it
since = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%S")

PARAMS = {
    "$where": f"requested_datetime >= '{since}'",
    "$limit": 5,
}
HEADERS = {"X-App-Token": APP_TOKEN}

print("Testing SF 311 API...")
print(f"URL: {URL}")
print(f"Filtering records since: {since}")

try:
    response = requests.get(URL, params=PARAMS, headers=HEADERS, timeout=15)
    print(f"Status code: {response.status_code}")

    if response.status_code != 200:
        print(f"FAILURE: Unexpected status code {response.status_code}")
        print(f"Response: {response.text[:500]}")
        sys.exit(1)

    records = response.json()

    if not isinstance(records, list):
        print(f"FAILURE: Expected a list of records, got {type(records)}")
        sys.exit(1)

    if len(records) == 0:
        print("WARNING: No records returned for the last 24 hours. API is reachable but no data — this may be normal outside business hours.")
    else:
        sample = records[0]
        print(f"\nSample response:")
        print(f"  Records returned:   {len(records)}")
        print(f"  Service request ID: {sample.get('service_request_id')}")
        print(f"  Category:           {sample.get('service_name')}")
        print(f"  Status:             {sample.get('status')}")
        print(f"  Requested at:       {sample.get('requested_datetime')}")
        print(f"  Neighborhood:       {sample.get('neighborhoods_sffind_boundaries')}")

    print("\nSUCCESS: SF 311 API is reachable and returning valid records.")

except requests.exceptions.Timeout:
    print("FAILURE: Request timed out.")
    sys.exit(1)
except requests.exceptions.RequestException as e:
    print(f"FAILURE: Network error — {e}")
    sys.exit(1)
except Exception as e:
    print(f"FAILURE: Unexpected error — {e}")
    sys.exit(1)