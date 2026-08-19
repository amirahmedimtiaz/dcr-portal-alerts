"""Run one portal scrape, persist the snapshot, and optionally send Gmail."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from analytics import manufacturer_diff, metric_comparisons
from database import Database
from emailer import build_email_html, build_manufacturer_csv, send_gmail
from portal import HISTORY_START_YEAR, SolarPortalScraper


LOGGER = logging.getLogger("dcr_portal_alerts")
JST = ZoneInfo("Asia/Tokyo")


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def now_jst() -> datetime:
    return datetime.now(JST)


def run_once(*, force_full_history: bool = False, send_email: bool = True) -> dict:
    load_dotenv()
    started_at = now_jst().isoformat(timespec="seconds")
    database_path = os.getenv("DATABASE_PATH", "portal.db")
    db = Database(database_path)
    is_initial = not db.has_successful_run()
    full_history = force_full_history or is_initial
    current_year = now_jst().year
    start_year = int(os.getenv("HISTORY_START_YEAR", str(HISTORY_START_YEAR)))
    timeout = float(os.getenv("SCRAPE_TIMEOUT_SECONDS", "45"))
    delay = float(os.getenv("SCRAPE_DELAY_SECONDS", "0.15"))
    scraper = SolarPortalScraper(
        base_url=os.getenv("PORTAL_BASE_URL", "https://solardcrportal.nise.res.in"),
        timeout=timeout,
        delay_seconds=delay,
    )
    run_id = db.start_run(
        started_at=started_at,
        full_history=full_history,
        is_initial=is_initial,
    )

    try:
        result = scraper.scrape(
            start_year=start_year,
            current_year=current_year,
            full_history=full_history,
        )
        db.save_scrape(
            run_id,
            observed_at=started_at,
            metric_values=result.metric_values,
            manufacturers=result.manufacturers,
        )
        latest = db.latest_nonzero_metrics()
        db.save_latest_metrics(run_id, latest)
        db.finish_run(
            run_id,
            finished_at=now_jst().isoformat(timespec="seconds"),
            status="success",
        )
    except Exception as exc:
        LOGGER.exception("Scrape failed")
        db.finish_run(
            run_id,
            finished_at=now_jst().isoformat(timespec="seconds"),
            status="failed",
            error=str(exc),
        )
        raise

    metrics = metric_comparisons(db, run_id)
    diff = manufacturer_diff(db, run_id)
    current_manufacturers = db.manufacturer_snapshots(run_id)
    dashboard_url = os.getenv("DASHBOARD_URL", "http://127.0.0.1:5000")
    report = {
        "run_id": run_id,
        "observed_at": started_at,
        "is_initial": is_initial,
        "full_history": full_history,
        "current_year": current_year,
        "states": result.states,
        "metrics": metrics,
        "manufacturer_diff": diff,
        "manufacturer_count": len(current_manufacturers),
    }

    should_email = send_email and (
        not is_initial or _bool_env("SEND_INITIAL_EMAIL", False)
    )
    email_error: str | None = None
    email_sent = False
    if should_email and (
        _bool_env("SEND_NO_CHANGE_EMAIL", True)
        or any(metric.get("delta") not in (None, 0) for metric in metrics)
        or any(diff.get("counts", {}).get(key, 0) for key in ("added", "removed", "changed"))
    ):
        try:
            html_body = build_email_html(
                observed_at=started_at,
                metrics=metrics,
                manufacturer_diff=diff,
                current_manufacturers=current_manufacturers,
                dashboard_url=dashboard_url,
                is_initial=is_initial,
            )
            manufacturer_csv = build_manufacturer_csv(current_manufacturers.values())
            subject = f"Solar DCR Portal weekly update — {started_at[:10]}"
            send_gmail(
                subject=subject,
                html_body=html_body,
                manufacturer_csv=manufacturer_csv,
            )
            email_sent = True
            LOGGER.info("Weekly email sent")
        except Exception as exc:
            email_error = str(exc)
            LOGGER.exception("Email delivery failed")
    elif is_initial and not should_email:
        LOGGER.info("Initial baseline saved; initial email disabled")
    elif should_email:
        LOGGER.info("No changes detected and no-change emails are disabled")

    if email_sent or email_error:
        db.finish_run(
            run_id,
            finished_at=now_jst().isoformat(timespec="seconds"),
            status="success",
            email_sent=email_sent,
            email_error=email_error,
        )
    report["email_sent"] = email_sent
    report["email_error"] = email_error
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--full-history",
        action="store_true",
        help="Fetch every year from HISTORY_START_YEAR through the current year",
    )
    parser.add_argument(
        "--no-email",
        action="store_true",
        help="Scrape and persist data without attempting Gmail delivery",
    )
    args = parser.parse_args()
    load_dotenv()
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        report = run_once(
            force_full_history=args.full_history,
            send_email=not args.no_email,
        )
    except Exception as exc:
        print(f"Run failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    return 1 if report.get("email_error") else 0


if __name__ == "__main__":
    raise SystemExit(main())
