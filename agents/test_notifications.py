"""
Test script for Email Notification Module (Task 13b-3).

Verifies:
- send_repair_alert returns False and logs a warning when env vars are missing
- Live send test (manual only) — requires env vars set in .env

Usage:
    python3 agents/test_notifications.py
"""

import os
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.notifications import send_repair_alert

PASS = "PASS"
FAIL = "FAIL"

SAMPLE_REPAIR_SUMMARY = {
    "source_name":            "weather_sf",
    "severity":               "critical",
    "change_summary":         "field_removed: hourly.temperature_2m",
    "affected_models_count":  5,
    "affected_dashboards":    ["City Intelligence"],
    "validation_passed":      True,
    "impact_tree_text": (
        "stg_weather_sf (BROKEN)\n"
        "├── int_hourly_weather_transit\n"
        "│   └── fact_weather_transit_hourly\n"
        "├── int_daily_weather_incidents\n"
        "│   └── fact_daily_city_summary"
    ),
    "repair_id":              "abc-123-def",
    "corrupted_rows_estimate": 12,
}


def check(label: str, condition: bool) -> bool:
    status = PASS if condition else FAIL
    print(f"  [{status}] {label}")
    return condition


def test_missing_env_vars():
    """Returns False gracefully when email env vars are not configured."""
    print("\n--- Missing env vars — should return False, not crash ---")

    empty_env = {
        k: v for k, v in os.environ.items()
        if k not in ("ALERT_EMAIL_ADDRESS", "ALERT_EMAIL_APP_PASSWORD", "ALERT_EMAIL_RECIPIENT")
    }

    with patch.dict(os.environ, empty_env, clear=True):
        result = send_repair_alert(SAMPLE_REPAIR_SUMMARY)

    check("returns False (not a crash)", result is False)
    check("result is a bool",            isinstance(result, bool))


def test_live_send():
    """
    Manual live send test — only runs when all 3 email env vars are present.

    To enable: set ALERT_EMAIL_ADDRESS, ALERT_EMAIL_APP_PASSWORD, and
    ALERT_EMAIL_RECIPIENT in your .env file, then run this script.

    Gmail app password: Google Account → Security → 2-Step Verification → App passwords
    """
    sender    = os.environ.get("ALERT_EMAIL_ADDRESS")
    password  = os.environ.get("ALERT_EMAIL_APP_PASSWORD")
    recipient = os.environ.get("ALERT_EMAIL_RECIPIENT")

    if not all([sender, password, recipient]):
        print(
            "\n--- Live email test SKIPPED ---\n"
            "  Set ALERT_EMAIL_ADDRESS, ALERT_EMAIL_APP_PASSWORD, "
            "ALERT_EMAIL_RECIPIENT in .env to enable."
        )
        return

    print("\n--- Live email send ---")
    result = send_repair_alert(SAMPLE_REPAIR_SUMMARY)
    check("send_repair_alert returned True", result is True)
    if result:
        print(f"  Check your inbox at {recipient}.")


def main():
    print("=" * 60)
    print("Email Notification Module — Test Suite")
    print("=" * 60)

    test_missing_env_vars()
    test_live_send()

    print("\n" + "=" * 60)
    print("Done.")


if __name__ == "__main__":
    main()
