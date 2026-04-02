"""
Email Notification Module — Task 13b-3

Sends a plain-text alert email when Schema Guardian has a repair package
ready for human approval.

No LLM calls, no BigQuery — standalone SMTP utility.

Import usage:
    from agents.notifications import send_repair_alert
"""

import logging
import os
import smtplib
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

logger = logging.getLogger(__name__)

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


def _build_body(r: dict) -> str:
    """Compose the plain-text email body from a repair summary dict."""
    dashboards = ", ".join(r.get("affected_dashboards", [])) or "None"
    validation = "PASSED" if r.get("validation_passed") else "FAILED"

    return (
        "SCHEMA DRIFT DETECTED\n"
        "=====================\n"
        f"Source:   {r['source_name']}\n"
        f"Severity: {r['severity'].upper()}\n"
        f"Change:   {r['change_summary']}\n"
        "\n"
        "IMPACT ANALYSIS\n"
        "===============\n"
        f"Affected models:     {r.get('affected_models_count', 'N/A')}\n"
        f"Affected dashboards: {dashboards}\n"
        "\n"
        f"{r.get('impact_tree_text', '(no tree available)')}\n"
        "\n"
        "DATA ASSESSMENT\n"
        "===============\n"
        f"Estimated corrupted rows: {r.get('corrupted_rows_estimate', 0)}\n"
        "\n"
        "REPAIR STATUS\n"
        "=============\n"
        f"Validation: {validation}\n"
        f"Repair ID:  {r.get('repair_id', 'N/A')}\n"
        "\n"
        "ACTION REQUIRED: Review and approve the repair package in the "
        "Agent Monitor dashboard.\n"
    )


def send_repair_alert(repair_summary: dict) -> bool:
    """
    Send a plain-text email alert for a Schema Guardian repair package.

    Never raises — all failures are logged and return False so the calling
    agent is never blocked by a notification failure.

    Args:
        repair_summary: Dict with keys:
            source_name, severity, change_summary, affected_models_count,
            affected_dashboards, validation_passed, impact_tree_text,
            repair_id, corrupted_rows_estimate

    Returns:
        True if the email was sent successfully, False otherwise.
    """
    sender    = os.environ.get("ALERT_EMAIL_ADDRESS")
    password  = os.environ.get("ALERT_EMAIL_APP_PASSWORD")
    recipient = os.environ.get("ALERT_EMAIL_RECIPIENT")

    if not all([sender, password, recipient]):
        missing = [
            name for name, val in [
                ("ALERT_EMAIL_ADDRESS",      sender),
                ("ALERT_EMAIL_APP_PASSWORD", password),
                ("ALERT_EMAIL_RECIPIENT",    recipient),
            ]
            if not val
        ]
        logger.warning(
            "Email notification skipped — missing env vars: %s",
            ", ".join(missing),
        )
        return False

    try:
        subject = (
            f"[ADORE] Schema Drift — "
            f"{repair_summary['source_name']} ({repair_summary['severity']})"
        )
        body = _build_body(repair_summary)

        msg = MIMEText(body, "plain")
        msg["Subject"] = subject
        msg["From"]    = sender
        msg["To"]      = recipient

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(sender, password)
            smtp.sendmail(sender, recipient, msg.as_string())

        logger.info("Repair alert sent to %s (repair_id=%s)", recipient, repair_summary.get("repair_id"))
        return True

    except Exception as e:
        logger.error(
            "Failed to send repair alert for %s: %s",
            repair_summary.get("source_name", "unknown"),
            e,
        )
        return False
