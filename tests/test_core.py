import json
import tempfile
import unittest
from pathlib import Path

from analytics import manufacturer_diff, metric_comparisons, stock_position
from database import Database
from portal import parse_devexpress_data
from site_builder import build_site


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
                        "raw": {
                            "AgencyName": "Alpha",
                            "CellDCR": 1,
                            "ModuleDCR": 3,
                            "CellDCR1": 0.5,
                            "ModuleDCR1": 1,
                        },
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
                        "raw": {
                            "AgencyName": "Alpha",
                            "CellDCR": 2,
                            "ModuleDCR": 4,
                            "CellDCR1": 0.75,
                            "ModuleDCR1": 1.5,
                        },
                    },
                    {
                        "agency_id": "b",
                        "agency_name": "Beta",
                        "state": "West Bengal",
                        "company_type": "Solar-Panels Manufacturer Only",
                        "row_hash": "new",
                        "raw": {
                            "AgencyName": "Beta",
                            "CellDCR": 5,
                            "ModuleDCR": 1,
                            "CellDCR1": 0,
                            "ModuleDCR1": 0.25,
                        },
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

            stock = stock_position(db, second)
            stock_metrics = {item["key"]: item for item in stock["metrics"]}
            self.assertEqual(stock_metrics["cell_held"]["current"], 7)
            self.assertEqual(stock_metrics["cell_held"]["previous"], 1)
            self.assertEqual(stock_metrics["cell_held"]["delta"], 6)
            self.assertEqual(stock_metrics["module_held"]["current"], 5)
            self.assertEqual(stock["top_holders"]["cell_held"][0]["agency_name"], "Beta")

    def test_static_site_embeds_snapshot_version_for_cache_busting(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db = Database(root / "test.db")
            run_id = db.start_run("2026-08-27T09:00:00+09:00", False, True)
            db.save_scrape(
                run_id,
                observed_at="2026-08-27T09:00:00+09:00",
                metric_values={
                    "cell_manufactured": [
                        {"year": 2026, "month": 8, "value": 1, "source_endpoint": "x"}
                    ]
                },
                manufacturers=[],
            )
            db.save_latest_metrics(run_id, db.latest_nonzero_metrics())
            db.finish_run(
                run_id,
                finished_at="2026-08-27T09:00:01+09:00",
                status="success",
            )

            output = build_site(output_dir=root / "site", database_path=root / "test.db")
            index = (output / "index.html").read_text(encoding="utf-8")
            app = (output / "app.js").read_text(encoding="utf-8")

            self.assertIn('window.DCR_DATA_VERSION = "1"', index)
            self.assertIn("?v=", app)
            self.assertIn("DCR_DATA_VERSION", app)


if __name__ == "__main__":
    unittest.main()
