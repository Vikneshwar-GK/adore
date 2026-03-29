import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")

API_KEY = os.environ.get("TRANSIT_511_API_KEY")
if not API_KEY:
    print("FAILURE: TRANSIT_511_API_KEY not set in .env")
    sys.exit(1)

URL = "http://api.511.org/transit/TripUpdates"
PARAMS = {
    "api_key": API_KEY,
    "agency": "SF",
    "format": "json",
}

print("Testing 511.org Transit API...")
print(f"URL: {URL}")

try:
    response = requests.get(URL, params=PARAMS, timeout=15)
    print(f"Status code: {response.status_code}")

    if response.status_code != 200:
        print(f"FAILURE: Unexpected status code {response.status_code}")
        print(f"Response: {response.text[:500]}")
        sys.exit(1)

    # Decode with utf-8-sig to strip BOM — do NOT use response.json()
    raw_text = response.content.decode("utf-8-sig")
    data = json.loads(raw_text)

    entities = data.get("entity", [])
    if not isinstance(entities, list):
        print(f"FAILURE: Expected 'entity' to be a list, got {type(entities)}")
        sys.exit(1)

    print(f"\nSample response:")
    print(f"  Total trip updates: {len(entities)}")

    if entities:
        sample = entities[0]
        trip_update = sample.get("trip_update", {})
        trip = trip_update.get("trip", {})
        print(f"  Sample entity ID:   {sample.get('id')}")
        print(f"  Trip ID:            {trip.get('trip_id')}")
        print(f"  Route ID:           {trip.get('route_id')}")
        stop_updates = trip_update.get("stop_time_update", [])
        print(f"  Stop time updates:  {len(stop_updates)}")

    print("\nSUCCESS: 511.org API is reachable, response parses as valid JSON.")

except requests.exceptions.Timeout:
    print("FAILURE: Request timed out.")
    sys.exit(1)
except requests.exceptions.RequestException as e:
    print(f"FAILURE: Network error — {e}")
    sys.exit(1)
except json.JSONDecodeError as e:
    print(f"FAILURE: JSON parse error — {e}")
    sys.exit(1)
except Exception as e:
    print(f"FAILURE: Unexpected error — {e}")
    sys.exit(1)