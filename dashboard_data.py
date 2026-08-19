"""Shared JSON payloads for the local Flask app and GitHub Pages build."""

from __future__ import annotations

from typing import Any

from analytics import manufacturer_diff, metric_comparisons, stock_position
from database import Database
from portal import METRICS


def manufacturer_items(db: Database, run_id: int | None = None) -> list[dict[str, Any]]:
    snapshots = db.manufacturer_snapshots(run_id)
    items = []
    for item in snapshots.values():
        raw = item["raw"]
        items.append(
            {
                "agency_id": item["agency_id"],
                "agency_name": item.get("agency_name") or raw.get("AgencyName"),
                "state": item.get("state") or raw.get("State"),
                "company_type": item.get("company_type") or raw.get("CompanyType"),
                "row_hash": item["row_hash"],
                "raw": raw,
            }
        )
    return items


def summary_payload(db: Database) -> dict[str, Any]:
    latest_run = db.latest_successful_run()
    if latest_run is None:
        return {
            "ready": False,
            "message": "No successful scrape yet.",
        }
    run_id = int(latest_run["id"])
    diff = manufacturer_diff(db, run_id)
    return {
        "ready": True,
        "latest_run": latest_run,
        "metrics": metric_comparisons(db, run_id),
        "stock_position": stock_position(db, run_id),
        "manufacturer_counts": db.manufacturer_count_by_type(run_id),
        "manufacturer_diff": diff["counts"],
        "manufacturer_count": len(db.manufacturer_snapshots(run_id)),
        "monthly_value_count": db.monthly_value_count(),
    }


def metrics_payload(db: Database) -> dict[str, Any]:
    series = db.metric_series()
    payload = []
    for key, definition in METRICS.items():
        payload.append(
            {
                "key": key,
                "label": definition["label"],
                "unit": "MW",
                "points": [
                    {
                        "period": f"{int(point['year']):04d}-{int(point['month']):02d}",
                        "value": float(point["value"]),
                    }
                    for point in series.get(key, [])
                ],
            }
        )
    return {"series": payload}


def manufacturers_payload(db: Database) -> dict[str, Any]:
    latest_run = db.latest_successful_run()
    if latest_run is None:
        return {"items": [], "fields": []}
    items = manufacturer_items(db, int(latest_run["id"]))
    fields = sorted({key for item in items for key in item["raw"].keys()})
    return {
        "run_id": int(latest_run["id"]),
        "observed_at": latest_run["finished_at"] or latest_run["started_at"],
        "fields": fields,
        "items": items,
    }


def all_payloads(db: Database) -> dict[str, dict[str, Any]]:
    return {
        "summary": summary_payload(db),
        "metrics": metrics_payload(db),
        "manufacturers": manufacturers_payload(db),
    }
