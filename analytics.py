"""Reusable comparisons for the weekly email and local dashboard."""

from __future__ import annotations

from typing import Any

from database import Database
from portal import METRICS


STOCK_FIELDS: tuple[tuple[str, str, str, str], ...] = (
    ("cell_held", "CellDCR", "Solar cells held", "Stock With Manufacturer (MW)"),
    ("module_held", "ModuleDCR", "Solar modules held", "Stock With Manufacturer (MW)"),
    (
        "cell_unclaimed",
        "CellDCR1",
        "Solar cells sold · buyer unclaimed",
        "Sold By Manufacturer Un-Claimed (MW)",
    ),
    (
        "module_unclaimed",
        "ModuleDCR1",
        "Solar modules sold · buyer unclaimed",
        "Sold By Manufacturer Un-Claimed (MW)",
    ),
)


def _growth(current: float | None, baseline: float | None) -> float | None:
    if current is None or baseline is None or abs(baseline) < 0.0000000001:
        return None
    return (current - baseline) / baseline


def _raw_float(raw: dict[str, Any], field: str) -> float:
    try:
        return float(raw.get(field) or 0)
    except (TypeError, ValueError):
        return 0.0


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


def _snapshot_stock_totals(
    snapshots: dict[str, dict[str, Any]],
) -> dict[str, float]:
    totals = {key: 0.0 for key, _field, _label, _source_label in STOCK_FIELDS}
    for item in snapshots.values():
        raw = item.get("raw", {})
        for key, field, _label, _source_label in STOCK_FIELDS:
            totals[key] += _raw_float(raw, field)
    return totals


def stock_position(db: Database, run_id: int | None = None) -> dict[str, Any]:
    """Aggregate the portal's manufacturer-held and unclaimed DCR stock fields."""

    current_run = db.latest_successful_run() if run_id is None else {"id": run_id}
    if current_run is None:
        return {"unit": "MW", "metrics": [], "states": [], "top_holders": {}}
    current_run_id = int(current_run["id"])
    previous_run = db.latest_successful_run(before_id=current_run_id)
    current = db.manufacturer_snapshots(current_run_id)
    previous = (
        db.manufacturer_snapshots(int(previous_run["id"])) if previous_run else {}
    )
    current_totals = _snapshot_stock_totals(current)
    previous_totals = _snapshot_stock_totals(previous) if previous_run else {}

    metrics: list[dict[str, Any]] = []
    for key, field, label, source_label in STOCK_FIELDS:
        current_value = current_totals[key]
        previous_value = previous_totals.get(key) if previous_run else None
        metrics.append(
            {
                "key": key,
                "field": field,
                "label": label,
                "source_label": source_label,
                "current": current_value,
                "previous": previous_value,
                "delta": current_value - previous_value
                if previous_value is not None
                else None,
                "growth": _growth(current_value, previous_value),
            }
        )

    states: dict[str, dict[str, Any]] = {}
    for item in current.values():
        state = str(item.get("state") or item.get("raw", {}).get("State") or "Unknown")
        entry = states.setdefault(
            state,
            {
                "state": state,
                "cell_held": 0.0,
                "module_held": 0.0,
                "cell_unclaimed": 0.0,
                "module_unclaimed": 0.0,
            },
        )
        raw = item.get("raw", {})
        for key, field, _label, _source_label in STOCK_FIELDS:
            entry[key] += _raw_float(raw, field)

    top_holders: dict[str, list[dict[str, Any]]] = {}
    for key, field, _label, _source_label in STOCK_FIELDS[:2]:
        ranked = sorted(
            current.values(),
            key=lambda item: _raw_float(item.get("raw", {}), field),
            reverse=True,
        )[:5]
        top_holders[key] = [
            {
                "agency_id": item.get("agency_id"),
                "agency_name": item.get("agency_name")
                or item.get("raw", {}).get("AgencyName"),
                "state": item.get("state") or item.get("raw", {}).get("State"),
                "value": _raw_float(item.get("raw", {}), field),
            }
            for item in ranked
        ]

    return {
        "unit": "MW",
        "scope": "Stock With Manufacturer (MW)",
        "metrics": metrics,
        "states": sorted(states.values(), key=lambda item: item["state"]),
        "top_holders": top_holders,
    }


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
