"""Reusable comparisons for the weekly email and local dashboard."""

from __future__ import annotations

from typing import Any

from database import Database
from portal import METRICS


def _growth(current: float | None, baseline: float | None) -> float | None:
    if current is None or baseline is None or abs(baseline) < 0.0000000001:
        return None
    return (current - baseline) / baseline


def metric_comparisons(db: Database, run_id: int | None = None) -> list[dict[str, Any]]:
    """Return latest values and the most meaningful prior weekly comparison."""

    current_run = db.latest_successful_run() if run_id is None else {"id": run_id}
    if current_run is None:
        return []
    current_run_id = int(current_run["id"])
    previous_run = db.latest_successful_run(before_id=current_run_id)
    latest = db.run_latest_metrics(current_run_id)
    previous_latest = (
        db.run_latest_metrics(int(previous_run["id"])) if previous_run else {}
    )
    previous_values = (
        db.run_metric_values(int(previous_run["id"])) if previous_run else {}
    )

    output: list[dict[str, Any]] = []
    for metric, definition in METRICS.items():
        current = latest.get(metric)
        previous = previous_latest.get(metric)
        if current is None:
            output.append(
                {
                    "metric": metric,
                    "label": definition["label"],
                    "unit": "MW",
                    "current": None,
                    "previous": None,
                    "delta": None,
                    "growth": None,
                    "comparison": "No non-zero data",
                    "period_changed": False,
                }
            )
            continue

        current_period = f"{current['year']:04d}-{current['month']:02d}"
        baseline: float | None = None
        baseline_period: str | None = None
        comparison = "No previous run"
        period_changed = False

        if previous is not None:
            previous_period = f"{previous['year']:04d}-{previous['month']:02d}"
            same_period_key = (metric, int(current["year"]), int(current["month"]))
            same_period_value = previous_values.get(same_period_key)
            if current_period == previous_period and same_period_value is not None:
                baseline = same_period_value
                baseline_period = previous_period
                comparison = "Week on week"
            else:
                # A newly published month is not a like-for-like WoW comparison.
                # Show the prior latest value as context but label it clearly.
                baseline = float(previous["value"])
                baseline_period = previous_period
                comparison = "Latest month changed"
                period_changed = True

        delta = float(current["value"]) - baseline if baseline is not None else None
        output.append(
            {
                "metric": metric,
                "label": definition["label"],
                "unit": "MW",
                "current": float(current["value"]),
                "current_period": current_period,
                "previous": baseline,
                "previous_period": baseline_period,
                "delta": delta,
                "growth": _growth(float(current["value"]), baseline),
                "comparison": comparison,
                "period_changed": period_changed,
            }
        )
    return output


def manufacturer_diff(
    db: Database,
    current_run_id: int | None = None,
    previous_run_id: int | None = None,
) -> dict[str, Any]:
    current_run = db.latest_successful_run() if current_run_id is None else {"id": current_run_id}
    if current_run is None:
        return {"added": [], "removed": [], "changed": [], "counts": {}}
    current_id = int(current_run["id"])
    if previous_run_id is None:
        previous_run = db.latest_successful_run(before_id=current_id)
        previous_run_id = int(previous_run["id"]) if previous_run else None

    current = db.manufacturer_snapshots(current_id)
    previous = db.manufacturer_snapshots(previous_run_id) if previous_run_id else {}
    added_ids = sorted(set(current) - set(previous))
    removed_ids = sorted(set(previous) - set(current))
    common_ids = sorted(set(current) & set(previous))

    added = [current[agency_id] for agency_id in added_ids]
    removed = [previous[agency_id] for agency_id in removed_ids]
    changed: list[dict[str, Any]] = []
    for agency_id in common_ids:
        before = previous[agency_id]
        after = current[agency_id]
        if before["row_hash"] == after["row_hash"]:
            continue
        before_raw = before["raw"]
        after_raw = after["raw"]
        changed_fields = sorted(
            key
            for key in set(before_raw) | set(after_raw)
            if before_raw.get(key) != after_raw.get(key)
        )
        changed.append(
            {
                "agency_id": agency_id,
                "before": before,
                "after": after,
                "changed_fields": changed_fields,
            }
        )

    return {
        "added": added,
        "removed": removed,
        "changed": changed,
        "counts": {
            "current": len(current),
            "added": len(added),
            "removed": len(removed),
            "changed": len(changed),
        },
    }

