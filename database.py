"""SQLite persistence for portal data, run history, and audit snapshots."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable


SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    full_history INTEGER NOT NULL DEFAULT 0,
    is_initial INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    email_sent INTEGER NOT NULL DEFAULT 0,
    email_error TEXT
);

CREATE TABLE IF NOT EXISTS monthly_values (
    metric TEXT NOT NULL,
    year INTEGER NOT NULL,
    month INTEGER NOT NULL,
    value REAL NOT NULL,
    observed_at TEXT NOT NULL,
    source_endpoint TEXT NOT NULL,
    PRIMARY KEY (metric, year, month)
);

CREATE TABLE IF NOT EXISTS run_metric_values (
    run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    metric TEXT NOT NULL,
    year INTEGER NOT NULL,
    month INTEGER NOT NULL,
    value REAL NOT NULL,
    PRIMARY KEY (run_id, metric, year, month)
);

CREATE TABLE IF NOT EXISTS run_metric_latest (
    run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    metric TEXT NOT NULL,
    year INTEGER NOT NULL,
    month INTEGER NOT NULL,
    value REAL NOT NULL,
    PRIMARY KEY (run_id, metric)
);

CREATE TABLE IF NOT EXISTS manufacturer_snapshots (
    run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    agency_id TEXT NOT NULL,
    agency_name TEXT,
    state TEXT,
    company_type TEXT,
    row_hash TEXT NOT NULL,
    raw_json TEXT NOT NULL,
    PRIMARY KEY (run_id, agency_id)
);

CREATE INDEX IF NOT EXISTS idx_monthly_values_period
    ON monthly_values (year, month);
CREATE INDEX IF NOT EXISTS idx_runs_status
    ON runs (status, id);
CREATE INDEX IF NOT EXISTS idx_manufacturer_snapshots_run
    ON manufacturer_snapshots (run_id);
"""


class Database:
    def __init__(self, path: str | Path = "portal.db") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)

    def has_successful_run(self) -> bool:
        with self.connect() as connection:
            return connection.execute(
                "SELECT 1 FROM runs WHERE status = 'success' LIMIT 1"
            ).fetchone() is not None

    def start_run(self, started_at: str, full_history: bool, is_initial: bool) -> int:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO runs (started_at, status, full_history, is_initial)
                VALUES (?, 'running', ?, ?)
                """,
                (started_at, int(full_history), int(is_initial)),
            )
            return int(cursor.lastrowid)

    def finish_run(
        self,
        run_id: int,
        *,
        finished_at: str,
        status: str,
        error: str | None = None,
        email_sent: bool = False,
        email_error: str | None = None,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE runs
                SET finished_at = ?, status = ?, error = ?,
                    email_sent = ?, email_error = ?
                WHERE id = ?
                """,
                (
                    finished_at,
                    status,
                    error,
                    int(email_sent),
                    email_error,
                    run_id,
                ),
            )

    def latest_successful_run(self, before_id: int | None = None) -> dict[str, Any] | None:
        where = "status = 'success'"
        params: list[Any] = []
        if before_id is not None:
            where += " AND id < ?"
            params.append(before_id)
        with self.connect() as connection:
            row = connection.execute(
                f"SELECT * FROM runs WHERE {where} ORDER BY id DESC LIMIT 1",
                params,
            ).fetchone()
            return dict(row) if row else None

    def recent_runs(self, limit: int = 12) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(row) for row in rows]

    def save_scrape(
        self,
        run_id: int,
        *,
        observed_at: str,
        metric_values: dict[str, list[dict[str, Any]]],
        manufacturers: Iterable[dict[str, Any]],
    ) -> None:
        with self.connect() as connection:
            for metric, points in metric_values.items():
                for point in points:
                    year = int(point["year"])
                    month = int(point["month"])
                    value = float(point["value"])
                    connection.execute(
                        """
                        INSERT INTO monthly_values
                            (metric, year, month, value, observed_at, source_endpoint)
                        VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(metric, year, month) DO UPDATE SET
                            value = excluded.value,
                            observed_at = excluded.observed_at,
                            source_endpoint = excluded.source_endpoint
                        """,
                        (
                            metric,
                            year,
                            month,
                            value,
                            observed_at,
                            point["source_endpoint"],
                        ),
                    )
                    connection.execute(
                        """
                        INSERT INTO run_metric_values
                            (run_id, metric, year, month, value)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (run_id, metric, year, month, value),
                    )

            for manufacturer in manufacturers:
                connection.execute(
                    """
                    INSERT INTO manufacturer_snapshots
                        (run_id, agency_id, agency_name, state, company_type, row_hash, raw_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        manufacturer["agency_id"],
                        manufacturer.get("agency_name"),
                        manufacturer.get("state"),
                        manufacturer.get("company_type"),
                        manufacturer["row_hash"],
                        json.dumps(
                            manufacturer["raw"],
                            sort_keys=True,
                            separators=(",", ":"),
                            default=str,
                        ),
                    ),
                )

    def save_latest_metrics(self, run_id: int, latest: dict[str, dict[str, Any]]) -> None:
        with self.connect() as connection:
            for metric, point in latest.items():
                connection.execute(
                    """
                    INSERT INTO run_metric_latest (run_id, metric, year, month, value)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(run_id, metric) DO UPDATE SET
                        year = excluded.year,
                        month = excluded.month,
                        value = excluded.value
                    """,
                    (
                        run_id,
                        metric,
                        int(point["year"]),
                        int(point["month"]),
                        float(point["value"]),
                    ),
                )

    def latest_nonzero_metrics(self) -> dict[str, dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT metric, year, month, value
                FROM monthly_values
                WHERE ABS(value) > 0.0000000001
                ORDER BY metric, year DESC, month DESC
                """
            ).fetchall()
        latest: dict[str, dict[str, Any]] = {}
        for row in rows:
            if row["metric"] not in latest:
                latest[row["metric"]] = dict(row)
        return latest

    def run_latest_metrics(self, run_id: int) -> dict[str, dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT metric, year, month, value FROM run_metric_latest WHERE run_id = ?",
                (run_id,),
            ).fetchall()
            return {row["metric"]: dict(row) for row in rows}

    def run_metric_values(self, run_id: int) -> dict[tuple[str, int, int], float]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT metric, year, month, value FROM run_metric_values WHERE run_id = ?",
                (run_id,),
            ).fetchall()
            return {
                (row["metric"], int(row["year"]), int(row["month"])): float(row["value"])
                for row in rows
            }

    def metric_series(self) -> dict[str, list[dict[str, Any]]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT metric, year, month, value, observed_at, source_endpoint
                FROM monthly_values
                ORDER BY metric, year, month
                """
            ).fetchall()
            result: dict[str, list[dict[str, Any]]] = {}
            latest = self.latest_nonzero_metrics()
            for row in rows:
                metric = row["metric"]
                latest_point = latest.get(metric)
                if latest_point and (row["year"], row["month"]) > (
                    latest_point["year"],
                    latest_point["month"],
                ):
                    continue
                result.setdefault(metric, []).append(dict(row))
            return result

    def manufacturer_snapshots(self, run_id: int | None = None) -> dict[str, dict[str, Any]]:
        if run_id is None:
            latest = self.latest_successful_run()
            if latest is None:
                return {}
            run_id = int(latest["id"])
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT agency_id, agency_name, state, company_type, row_hash, raw_json
                FROM manufacturer_snapshots
                WHERE run_id = ?
                ORDER BY agency_name COLLATE NOCASE
                """,
                (run_id,),
            ).fetchall()
        result: dict[str, dict[str, Any]] = {}
        for row in rows:
            item = dict(row)
            item["raw"] = json.loads(item.pop("raw_json"))
            result[item["agency_id"]] = item
        return result

    def manufacturer_count_by_type(self, run_id: int | None = None) -> dict[str, int]:
        if run_id is None:
            latest = self.latest_successful_run()
            if latest is None:
                return {}
            run_id = int(latest["id"])
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT COALESCE(company_type, 'Unknown') AS company_type, COUNT(*) AS count
                FROM manufacturer_snapshots
                WHERE run_id = ?
                GROUP BY company_type
                ORDER BY company_type
                """,
                (run_id,),
            ).fetchall()
            return {row["company_type"]: int(row["count"]) for row in rows}

    def monthly_value_count(self) -> int:
        with self.connect() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM monthly_values").fetchone()[0])

