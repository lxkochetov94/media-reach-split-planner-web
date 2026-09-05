import json
import unittest
from pathlib import Path

import web_api
from engine import FlightInfo, ParsedPlan


class WebApiAuditTests(unittest.TestCase):
    def setUp(self):
        self.previous_plan = web_api.PLAN
        flight = FlightInfo(
            id="F1",
            label="Flight 1",
            sheet="Plan",
            universe=10_000_000.0,
        )
        web_api.PLAN = ParsedPlan(
            path=Path("dummy.xlsx"),
            placements=[],
            sheet_meta={},
            tables=[],
            universe=10_000_000.0,
            period_start=None,
            period_end=None,
            warnings=[],
            flights=[flight],
            display_name="Audit plan",
        )

    def tearDown(self):
        web_api.PLAN = self.previous_plan

    def test_empty_flight_selection_stays_empty(self):
        result = json.loads(web_api.calculate(json.dumps({
            "selected_flights": [],
            "universe": 10_000_000,
            "selected_frequencies": [1, 3],
            "effective_frequency": 3,
            "intersection_mode": "total",
            "manual_intersection": 0.85,
        })))
        self.assertEqual(result["summary"]["selected_flights"], [])
        self.assertIsNone(result["summary"]["budget"])

    def test_invalid_universe_is_rejected(self):
        with self.assertRaises(ValueError):
            web_api.calculate(json.dumps({
                "selected_flights": [],
                "universe": 0,
            }))

    def test_invalid_manual_intersection_is_rejected(self):
        with self.assertRaises(ValueError):
            web_api.calculate(json.dumps({
                "selected_flights": [],
                "universe": 10_000_000,
                "intersection_mode": "total",
                "manual_intersection": 1.2,
            }))

    def test_invalid_reachability_is_rejected(self):
        with self.assertRaises(ValueError):
            web_api.calculate(json.dumps({
                "selected_flights": [],
                "universe": 10_000_000,
                "reachability": {"3": 1.1},
            }))


if __name__ == "__main__":
    unittest.main()
