"""Read-only client for the public Solar DCR Portal summary endpoints."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


LOGGER = logging.getLogger(__name__)

PORTAL_BASE_URL = "https://solardcrportal.nise.res.in"
SUMMARY_PATH = "/Summary/index"
HISTORY_START_YEAR = 2022

MONTHS = {
    "Jan": 1,
    "Feb": 2,
    "Mar": 3,
    "Apr": 4,
    "May": 5,
    "Jun": 6,
    "Jul": 7,
    "Aug": 8,
    "Sep": 9,
    "Oct": 10,
    "Nov": 11,
    "Dec": 12,
}


METRICS: dict[str, dict[str, str]] = {
    "cell_manufactured": {
        "label": "Solar cells manufactured",
        "endpoint": "WaferToCell",
        "source_label": "Solar Cell Manufactured (MW)",
    },
    "cell_sold": {
        "label": "Solar cells sold",
        "endpoint": "DCRInvChart",
        "source_label": "Solar Cell Sold (MW)",
    },
    "module_manufactured": {
        "label": "Solar modules manufactured",
        "endpoint": "PnlMfgChart",
        "source_label": "Solar Module Manufactured (MW)",
    },
    "module_sold": {
        "label": "Solar modules sold",
        "endpoint": "PnlInvChart",
        "source_label": "Solar Module Sold (MW)",
    },
}

ARRAY_RE = re.compile(
    r'new\s+DevExpress\.data\.ArrayStore\(\{"data":(\[.*?\])\}\)',
    re.DOTALL,
)


class PortalScrapeError(RuntimeError):
    """Raised when a portal response cannot be safely parsed."""


def parse_devexpress_data(html: str) -> list[dict[str, Any]]:
    """Extract the JSON-like ArrayStore data embedded by DevExtreme."""

    match = ARRAY_RE.search(html)
    if not match:
        title = re.search(r"<title>\s*([^<]+)", html, re.IGNORECASE)
        suffix = f" ({title.group(1).strip()})" if title else ""
        raise PortalScrapeError(f"DevExtreme data array not found{suffix}")

    payload = match.group(1)
    # The list endpoint includes JavaScript Date values. They are not needed for
    # the public dashboard, so preserve the field while normalizing the value.
    payload = re.sub(r"new\s+Date\([^)]*\)", "null", payload)
    payload = re.sub(r"\bundefined\b", "null", payload)
    try:
        parsed = json.loads(payload, parse_constant=lambda _value: None)
    except json.JSONDecodeError as exc:
        raise PortalScrapeError(f"Could not parse portal data array: {exc}") from exc
    if not isinstance(parsed, list):
        raise PortalScrapeError("Portal data array was not a list")
    return parsed


def _stable_json_hash(value: Any) -> str:
    serialized = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


@dataclass
class ScrapeResult:
    metric_values: dict[str, list[dict[str, Any]]]
    manufacturers: list[dict[str, Any]]
    states: list[str]


class SolarPortalScraper:
    def __init__(
        self,
        *,
        base_url: str = PORTAL_BASE_URL,
        timeout: float = 45.0,
        delay_seconds: float = 0.15,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.delay_seconds = max(0.0, delay_seconds)
        self.session = requests.Session()
        retry = Retry(
            total=3,
            connect=3,
            read=3,
            status=3,
            backoff_factor=0.6,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET", "POST"}),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.session.headers.update(
            {
                "User-Agent": (
                    "dcr-portal-alerts/1.0 (+local monitoring; respectful weekly requests)"
                ),
                "Accept": "text/html,application/xhtml+xml",
            }
        )

    def initialize_session(self) -> None:
        response = self.session.get(
            f"{self.base_url}{SUMMARY_PATH}", timeout=self.timeout
        )
        response.raise_for_status()
        if "500 Error Page" in response.text:
            raise PortalScrapeError("Portal summary page returned an internal error")

    def _post_fragment(self, path: str, data: list[tuple[str, str]]) -> str:
        response = self.session.post(
            f"{self.base_url}{path}",
            data=data,
            headers={
                "X-Requested-With": "XMLHttpRequest",
                "Referer": f"{self.base_url}{SUMMARY_PATH}",
                "Origin": self.base_url,
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        if "500 Error Page" in response.text or "Internal Server Error" in response.text:
            raise PortalScrapeError(f"Portal endpoint returned an internal error: {path}")
        return response.text

    def fetch_metric_year(self, metric: str, year: int) -> list[dict[str, Any]]:
        definition = METRICS[metric]
        html = self._post_fragment(
            f"/Summary/{definition['endpoint']}",
            [
                ("Year1[]", str(year)),
                ("MfgId", ""),
                ("RecaptchaToken", ""),
            ],
        )
        rows = parse_devexpress_data(html)
        points: list[dict[str, Any]] = []
        for row in rows:
            month_name = str(row.get("xValue", ""))
            month = MONTHS.get(month_name)
            if month is None:
                continue
            try:
                value = float(row.get("yValue", 0) or 0)
            except (TypeError, ValueError) as exc:
                raise PortalScrapeError(
                    f"Non-numeric {metric} value for {year}-{month_name}: {row.get('yValue')}"
                ) from exc
            points.append(
                {
                    "year": year,
                    "month": month,
                    "value": value,
                    "source_endpoint": definition["endpoint"],
                }
            )
        if not points:
            raise PortalScrapeError(f"No monthly points returned for {metric} in {year}")
        return points

    def fetch_metric_history(self, start_year: int, end_year: int) -> dict[str, list[dict[str, Any]]]:
        result: dict[str, list[dict[str, Any]]] = {metric: [] for metric in METRICS}
        for year in range(start_year, end_year + 1):
            for metric in METRICS:
                LOGGER.info("Fetching %s for %s", metric, year)
                result[metric].extend(self.fetch_metric_year(metric, year))
                time.sleep(self.delay_seconds)
        return result

    def fetch_current_year(self, year: int) -> dict[str, list[dict[str, Any]]]:
        result: dict[str, list[dict[str, Any]]] = {metric: [] for metric in METRICS}
        for metric in METRICS:
            LOGGER.info("Fetching current-year %s for %s", metric, year)
            result[metric] = self.fetch_metric_year(metric, year)
            time.sleep(self.delay_seconds)
        return result

    def fetch_manufacturers(self) -> tuple[list[dict[str, Any]], list[str]]:
        summary_html = self._post_fragment(
            "/Summary/AgencyListTbl",
            [("CompType[]", "Manufacturer"), ("RecaptchaToken", "")],
        )
        summary_rows = parse_devexpress_data(summary_html)
        states = sorted(
            {
                str(row.get("State", "")).strip()
                for row in summary_rows
                if str(row.get("State", "")).strip()
            }
        )
        if not states:
            raise PortalScrapeError("Manufacturer summary returned no states")

        manufacturers: list[dict[str, Any]] = []
        for state in states:
            LOGGER.info("Fetching manufacturer details for %s", state)
            detail_html = self._post_fragment(
                "/Summary/AgencyListDt",
                [
                    ("State", state),
                    ("CompType[]", "Manufacturer"),
                    ("RecaptchaToken", ""),
                ],
            )
            for raw in parse_devexpress_data(detail_html):
                if not isinstance(raw, dict):
                    continue
                raw_state = str(raw.get("State") or state).strip()
                agency_name = str(raw.get("AgencyName") or "").strip()
                company_type = str(raw.get("CompanyType") or "").strip()
                raw["State"] = raw_state
                agency_id = str(raw.get("AgencyId") or "").strip()
                if not agency_id or agency_id == "00000000-0000-0000-0000-000000000000":
                    agency_id = _stable_json_hash(
                        {"state": raw_state, "name": agency_name, "type": company_type}
                    )[:32]
                manufacturers.append(
                    {
                        "agency_id": agency_id,
                        "agency_name": agency_name,
                        "state": raw_state,
                        "company_type": company_type,
                        "row_hash": _stable_json_hash(raw),
                        "raw": raw,
                    }
                )
            time.sleep(self.delay_seconds)

        deduplicated: dict[str, dict[str, Any]] = {}
        for manufacturer in manufacturers:
            deduplicated[manufacturer["agency_id"]] = manufacturer
        return list(deduplicated.values()), states

    def scrape(self, *, start_year: int, current_year: int, full_history: bool) -> ScrapeResult:
        self.initialize_session()
        metric_values = (
            self.fetch_metric_history(start_year, current_year)
            if full_history
            else self.fetch_current_year(current_year)
        )
        manufacturers, states = self.fetch_manufacturers()
        return ScrapeResult(
            metric_values=metric_values,
            manufacturers=manufacturers,
            states=states,
        )

