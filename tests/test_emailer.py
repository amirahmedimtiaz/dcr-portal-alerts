import unittest

from emailer import build_email_html


class EmailerTests(unittest.TestCase):
    def test_email_has_separate_top_ten_cell_and_module_stock_rankings(self):
        manufacturers = {}
        for index in range(12):
            agency_id = f"maker-{index:02d}"
            manufacturers[agency_id] = {
                "agency_id": agency_id,
                "agency_name": f"Maker {index:02d}",
                "state": f"State {index:02d}",
                "company_type": "Solar Cells and Panels Manufacturer",
                "raw": {
                    "AgencyName": f"Maker {index:02d}",
                    "CellDCR": index + 1,
                    "ModuleDCR": 100 - index,
                },
            }

        email_html = build_email_html(
            observed_at="2026-08-20T09:00:00+09:00",
            metrics=[],
            manufacturer_diff={
                "counts": {"current": 12, "added": 0, "removed": 0, "changed": 0},
                "added": [],
                "removed": [],
                "changed": [],
            },
            current_manufacturers=manufacturers,
            dashboard_url="https://example.com/dashboard/",
        )

        cell_table = email_html.split('id="cell-stock-ranking"', 1)[1].split(
            "</table>", 1
        )[0]
        module_table = email_html.split('id="module-stock-ranking"', 1)[1].split(
            "</table>", 1
        )[0]

        self.assertIn("Top 10 solar cell stock holders", email_html)
        self.assertIn("Top 10 solar module stock holders", email_html)
        self.assertEqual(cell_table.count("<tr>"), 11)
        self.assertEqual(module_table.count("<tr>"), 11)
        self.assertIn(">Maker 11<", cell_table)
        self.assertNotIn(">Maker 00<", cell_table)
        self.assertIn(">Maker 00<", module_table)
        self.assertNotIn(">Maker 11<", module_table)
        self.assertLess(cell_table.index(">Maker 11<"), cell_table.index(">Maker 10<"))
        self.assertLess(module_table.index(">Maker 00<"), module_table.index(">Maker 01<"))


if __name__ == "__main__":
    unittest.main()
