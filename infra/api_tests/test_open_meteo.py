import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")

URL = "https://api.open-meteo.com/v1/forecast"
PARAMS = {
    "latitude": 37.7749,
    "longitude": -122.4194,
    "current_weather": True,
    "hourly": "temperature_2m,precipitation,wind_speed_10m,relative_humidity_2m",
}

print("Testing Open-Meteo API...")
print(f"URL: {URL}")

try:
    response = requests.get(URL, params=PARAMS, timeout=10)
    print(f"Status code: {response.status_code}")

    if response.status_code != 200:
        print(f"FAILURE: Unexpected status code {response.status_code}")
        print(f"Response: {response.text[:500]}")
        sys.exit(1)

    data = response.json()

    # Verify expected fields
    required_fields = ["current_weather", "hourly"]
    missing = [f for f in required_fields if f not in data]
    if missing:
        print(f"FAILURE: Missing expected fields: {missing}")
        sys.exit(1)

    current = data["current_weather"]
    hourly = data["hourly"]

    print(f"\nSample response:")
    print(f"  Temperature:  {current.get('temperature')} °C")
    print(f"  Wind speed:   {current.get('windspeed')} km/h")
    print(f"  Weather code: {current.get('weathercode')}")
    print(f"  Humidity (first hour): {hourly.get('relative_humidity_2m', [None])[0]} %")
    print(f"  Precip (first hour):   {hourly.get('precipitation', [None])[0]} mm")

    print("\nSUCCESS: Open-Meteo API is reachable and returning expected fields.")

except requests.exceptions.Timeout:
    print("FAILURE: Request timed out.")
    sys.exit(1)
except requests.exceptions.RequestException as e:
    print(f"FAILURE: Network error — {e}")
    sys.exit(1)
except Exception as e:
    print(f"FAILURE: Unexpected error — {e}")
    sys.exit(1)