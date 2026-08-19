import json
import tempfile
import unittest
from pathlib import Path

from analytics import manufacturer_diff, metric_comparisons
from database import Database
from portal import parse_devexpress_data


class CoreTests(unittest.TestCase):
    def test_parse_chart_array(self):
        html = """
        <script>new DevExpress.data.ArrayStore({"data":[
          {"SeriesText":"DCR","xValue":"Jan","yValue":1.25},
          {"SeriesText":"DCR","xValue":"Feb","yValue":0}
        ]})</script>
        """
        self.assertEqual(parse_devexpress_data(html)[0]["yValue"], 1.25)

    def test_parse_date_normalization(self):
        html = 'new DevExpress.data.ArrayStore({"data":[{"RegisterDate":new Date(1, 0, 1),"State":"Gujarat"}]})'
        self.assertEqual(parse_devexpress_data(html)[0]["RegisterDate"], None)

    def test_week_on_week_comparison_and_manufacturer_diff(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Database(Path(directory) / "test.db")
            first = db.start_run("2026-08-08T09:00:00+09:00", False, True)
            db.save_scrape(
                first,
                observed_at="2026-08-08T09:00:00+09:00",
                metric_values={
                    "cell_manufactured": [{"year": 2026, "month": 7, "value": 100, "source_endpoint": "x"}],
                    "cell_sold": [{"year": 2026, "month": 7, "value": 50, "source_endpoint": "x"}],
                },
                manufacturers=[
                    {
                        "agency_id": "a",
                        "agency_name": "Alpha",
                        "state": "Gujarat",
                        "company_type": "Solar-Cells Manufacturer Only",
                        "row_hash": "old",
                        "raw": {"AgencyName": "Alpha", "CellDCR": 1},
                    }
                ],
            )
            db.save_latest_metrics(first, db.latest_nonzero_metrics())
            db.finish_run(first, finished_at="2026-08-08T09:00:01+09:00", status="success")

            second = db.start_run("2026-08-15T09:00:00+09:00", False, False)
            db.save_scrape(
                second,
                observed_at="2026-08-15T09:00:00+09:00",
                metric_values={
                    "cell_manufactured": [{"year": 2026, "month": 7, "value": 110, "source_endpoint": "x"}],
                    "cell_sold": [{"year": 2026, "month": 7, "value": 50, "source_endpoint": "x"}],
                },
                manufacturers=[
                    {
                        "agency_id": "a",
                        "agency_name": "Alpha",
                        "state": "Gujarat",
                        "company_type": "Solar-Cells Manufacturer Only",
                        "row_hash": "new",
                        "raw": {"AgencyName": "Alpha", "CellDCR": 2},
                    },
                    {
                        "agency_id": "b",
                        "agency_name": "Beta",
                        "state": "West Bengal",
                        "company_type": "Solar-Panels Manufacturer Only",
                        "row_hash": "new",
                        "raw": {"AgencyName": "Beta"},
                    },
                ],
            )
            db.save_latest_metrics(second, db.latest_nonzero_metrics())
            db.finish_run(second, finished_at="2026-08-15T09:00:01+09:00", status="success")

            comparisons = {item["metric"]: item for item in metric_comparisons(db, second)}
            self.assertEqual(comparisons["cell_manufactured"]["comparison"], "Week on week")
            self.assertEqual(comparisons["cell_manufactured"]["delta"], 10)
            self.assertAlmostEqual(comparisons["cell_manufactured"]["growth"], 0.1)

            diff = manufacturer_diff(db, second)
            self.assertEqual(diff["counts"], {"current": 2, "added": 1, "removed": 0, "changed": 1})


if __name__ == "__main__":
    unittest.main()

