"""Gmail delivery for the weekly portal digest."""

from __future__ import annotations

import csv
import html
import io
import json
import os
import smtplib
from email.message import EmailMessage
from typing import Any, Iterable


class EmailConfigurationError(RuntimeError):
    pass


def _number(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:,.2f}"


def _growth(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:+.2%}"


def _escape(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return html.escape(str(value))


def _manufacturer_name(item: dict[str, Any]) -> str:
    return str(item.get("agency_name") or item.get("raw", {}).get("AgencyName") or "Unknown")


def _manufacturer_row(item: dict[str, Any]) -> str:
    raw = item.get("raw", {})
    return (
        "<tr>"
        f"<td>{_escape(_manufacturer_name(item))}</td>"
        f"<td>{_escape(item.get('state') or raw.get('State'))}</td>"
        f"<td>{_escape(item.get('company_type') or raw.get('CompanyType'))}</td>"
        f"<td>{_escape(raw.get('Email'))}</td>"
        "</tr>"
    )


def build_email_html(
    *,
    observed_at: str,
    metrics: Iterable[dict[str, Any]],
    manufacturer_diff: dict[str, Any],
    current_manufacturers: dict[str, dict[str, Any]],
    dashboard_url: str,
    is_initial: bool = False,
) -> str:
    metric_rows = []
    for metric in metrics:
        metric_rows.append(
            "<tr>"
            f"<td>{_escape(metric['label'])}</td>"
            f"<td>{_escape(metric.get('current_period'))}</td>"
            f"<td>{_number(metric.get('current'))} MW</td>"
            f"<td>{_number(metric.get('previous'))} MW</td>"
            f"<td>{_number(metric.get('delta'))} MW</td>"
            f"<td>{_growth(metric.get('growth'))}</td>"
            f"<td>{_escape(metric.get('comparison'))}</td>"
            "</tr>"
        )

    diff = manufacturer_diff
    changed_rows = []
    for item in diff.get("changed", [])[:100]:
        after = item["after"]
        changed_rows.append(
            "<tr>"
            f"<td>{_escape(_manufacturer_name(after))}</td>"
            f"<td>{_escape(after.get('state'))}</td>"
            f"<td>{_escape(', '.join(item.get('changed_fields', [])))}</td>"
            "</tr>"
        )

    section = ""
    if is_initial:
        section += "<p>This run created the initial historical baseline.</p>"
    section += f"""
    <h2>Monthly production and sales</h2>
    <table>
      <thead><tr><th>Metric</th><th>Latest month</th><th>Current</th>
      <th>Previous week</th><th>Change</th><th>Growth</th><th>Comparison</th></tr></thead>
      <tbody>{''.join(metric_rows)}</tbody>
    </table>
    <p class="note">Growth is calculated against the previous weekly observation. If a new
    month became the latest published month, the comparison is labelled accordingly.</p>

    <h2>Manufacturer list</h2>
    <p>Current manufacturers: <strong>{diff.get('counts', {}).get('current', len(current_manufacturers))}</strong>.
    Added: <strong>{diff.get('counts', {}).get('added', 0)}</strong> ·
    Removed: <strong>{diff.get('counts', {}).get('removed', 0)}</strong> ·
    Changed: <strong>{diff.get('counts', {}).get('changed', 0)}</strong></p>
    """

    if diff.get("added"):
        section += "<h3>Added manufacturers</h3><table><thead><tr><th>Company</th><th>State</th><th>Type</th><th>Email</th></tr></thead><tbody>"
        section += "".join(_manufacturer_row(item) for item in diff["added"][:100])
        section += "</tbody></table>"
    if diff.get("removed"):
        section += "<h3>Removed manufacturers</h3><table><thead><tr><th>Company</th><th>State</th><th>Type</th><th>Email</th></tr></thead><tbody>"
        section += "".join(_manufacturer_row(item) for item in diff["removed"][:100])
        section += "</tbody></table>"
    if changed_rows:
        section += "<h3>Changed manufacturer records</h3><table><thead><tr><th>Company</th><th>State</th><th>Changed fields</th></tr></thead><tbody>"
        section += "".join(changed_rows)
        section += "</tbody></table>"
    if not diff.get("added") and not diff.get("removed") and not diff.get("changed"):
        section += "<p>No manufacturer records changed since the previous successful run.</p>"

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><style>
body {{ font-family: Arial, sans-serif; color: #1d2939; line-height: 1.45; }}
h1 {{ color: #176b87; }} h2 {{ margin-top: 28px; color: #176b87; }}
h3 {{ margin-top: 20px; color: #344054; }}
table {{ border-collapse: collapse; width: 100%; margin: 10px 0 14px; font-size: 13px; }}
th, td {{ border: 1px solid #d0d5dd; padding: 7px 8px; text-align: left; vertical-align: top; }}
th {{ background: #eef7fa; }} .note {{ color: #667085; font-size: 12px; }}
a {{ color: #176b87; }}
</style></head><body>
<h1>Solar DCR Portal weekly update</h1>
<p>Observed: <strong>{_escape(observed_at)}</strong></p>
{section}
<p>Open the local dashboard: <a href="{_escape(dashboard_url)}">{_escape(dashboard_url)}</a></p>
</body></html>"""


def build_manufacturer_csv(items: Iterable[dict[str, Any]]) -> bytes:
    rows = [item.get("raw", {}) for item in items]
    keys = sorted({key for row in rows for key in row.keys()})
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=keys, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                key: json.dumps(value, ensure_ascii=False, sort_keys=True)
                if isinstance(value, (dict, list))
                else value
                for key, value in row.items()
            }
        )
    return output.getvalue().encode("utf-8")


def send_gmail(
    *,
    subject: str,
    html_body: str,
    manufacturer_csv: bytes,
    sender: str | None = None,
    password: str | None = None,
    receiver: str | None = None,
) -> None:
    sender = sender or os.getenv("EMAIL_SENDER")
    password = password or os.getenv("EMAIL_PASSWORD")
    receiver = receiver or os.getenv("EMAIL_RECEIVER")
    if not sender or not password or not receiver:
        raise EmailConfigurationError(
            "Set EMAIL_SENDER, EMAIL_PASSWORD, and EMAIL_RECEIVER before sending email"
        )

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = receiver
    message.set_content("The Solar DCR Portal weekly update is available as HTML.")
    message.add_alternative(html_body, subtype="html")
    message.add_attachment(
        manufacturer_csv,
        maintype="text",
        subtype="csv",
        filename="solar-dcr-manufacturers.csv",
    )

    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=45) as smtp:
        smtp.login(sender, password)
        smtp.send_message(message)

