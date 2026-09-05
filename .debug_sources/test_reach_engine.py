import unittest
from pathlib import Path

from engine import (
    ReachParams,
    Placement,
    FlightInfo,
    ParsedPlan,
    apply_reach,
    calculate_reach,
    calculate_reach_from_target_1p,
    combine_reach_union,
    flight_channel_kpi_summary,
    _synthesize_missing_channel_totals,
)


class ReachEngineAuditTests(unittest.TestCase):
    U = 10_000_000.0

    def test_three_flights_union_is_bounded_and_expected(self):
        parts = [
            {"target_1p": 6_000_000.0, "target_pct_1p": 0.60,
             "target_3p": 3_000_000.0, "target_pct_3p": 0.30},
            {"target_1p": 6_000_000.0, "target_pct_1p": 0.60,
             "target_3p": 3_000_000.0, "target_pct_3p": 0.30},
            {"target_1p": 6_000_000.0, "target_pct_1p": 0.60,
             "target_3p": 3_000_000.0, "target_pct_3p": 0.30},
        ]
        out = combine_reach_union(parts, self.U, coefficient=0.85, frequencies=(1, 3))
        expected_1p = (1 - (1 - 0.60) ** 3) * 0.85
        expected_3p = (1 - (1 - 0.30) ** 3) * 0.85
        self.assertAlmostEqual(out["target_pct_1p"], expected_1p, places=12)
        self.assertAlmostEqual(out["target_pct_3p"], expected_3p, places=12)
        self.assertLess(out["target_pct_1p"], 1.0)
        self.assertLess(out["target_pct_3p"], out["target_pct_1p"])

    def test_union_is_order_invariant(self):
        a = {"target_1p": 2_000_000.0, "target_3p": 700_000.0}
        b = {"target_1p": 4_000_000.0, "target_3p": 1_500_000.0}
        x = combine_reach_union([a, b], self.U, coefficient=0.9, frequencies=(1, 3))
        y = combine_reach_union([b, a], self.U, coefficient=0.9, frequencies=(1, 3))
        self.assertAlmostEqual(x["target_1p"], y["target_1p"], places=9)
        self.assertAlmostEqual(x["target_3p"], y["target_3p"], places=9)

    def test_single_set_coefficient_one_preserves_people(self):
        src = {"target_1p": 4_000_000.0, "target_3p": 1_500_000.0}
        out = combine_reach_union([src], self.U, coefficient=1.0, frequencies=(1, 3))
        self.assertAlmostEqual(out["target_1p"], 4_000_000.0, places=6)
        self.assertAlmostEqual(out["target_3p"], 1_500_000.0, places=6)

    def test_zero_coefficient_is_valid_zero_reach(self):
        src = {"target_1p": 4_000_000.0, "target_3p": 1_500_000.0}
        out = combine_reach_union([src], self.U, coefficient=0.0, frequencies=(1, 3))
        self.assertEqual(out["target_1p"], 0.0)
        self.assertEqual(out["target_3p"], 0.0)

    def test_invalid_union_coefficient_is_rejected_not_clipped(self):
        src = {"target_1p": 4_000_000.0}
        with self.assertRaises(ValueError):
            combine_reach_union([src], self.U, coefficient=1.01, frequencies=(1,))

    def test_impossible_source_reach_is_rejected_not_clipped(self):
        src = {"target_1p": self.U}
        with self.assertRaises(ValueError):
            combine_reach_union([src], self.U, coefficient=1.0, frequencies=(1,))

    def test_source_target_reach_equal_universe_is_rejected(self):
        p = ReachParams(universe=self.U, selected_frequencies=(1, 3))
        with self.assertRaises(ValueError):
            calculate_reach_from_target_1p(self.U, p, avg_frequency=3.0)

    def test_frequency_curve_is_monotonic(self):
        p = ReachParams(
            universe=self.U,
            lag_visible_share=0.65,
            cookie_people=2.4,
            target_affinity=0.65,
            selected_frequencies=(1, 2, 3, 4, 5, 6),
        )
        out = calculate_reach(
            8_000_000.0,
            p,
            impressions=24_000_000.0,
            avg_frequency=3.0,
        )
        vals = [out[f"target_{f}p"] for f in range(1, 7)]
        for left, right in zip(vals, vals[1:]):
            self.assertGreater(left, right)
        self.assertLess(out["target_pct_1p"], 1.0)

    def test_source_frequency_curve_is_monotonic(self):
        p = ReachParams(universe=self.U, selected_frequencies=(1, 2, 3, 4, 5, 6))
        out = calculate_reach_from_target_1p(6_000_000.0, p, avg_frequency=3.0)
        vals = [out[f"target_{f}p"] for f in range(1, 7)]
        for left, right in zip(vals, vals[1:]):
            self.assertGreater(left, right)

    def test_missing_channel_subtotal_never_adds_reach_uu(self):
        flight = FlightInfo(
            id="F1",
            label="Flight 1",
            sheet="Plan",
            universe=self.U,
        )
        rows = [
            Placement(
                sheet="Plan", source_row=1, flight="F1", flight_label="Flight 1",
                channel="OLV", platform="Platform A", buying_model="CPM",
                budget=1_000_000.0, impressions=10_000_000.0, tech_reach=5_000_000.0,
            ),
            Placement(
                sheet="Plan", source_row=2, flight="F1", flight_label="Flight 1",
                channel="OLV", platform="Platform B", buying_model="CPM",
                budget=1_000_000.0, impressions=10_000_000.0, tech_reach=5_000_000.0,
            ),
        ]
        placements = _synthesize_missing_channel_totals(rows, flight)
        synthetic = [x for x in placements if x.synthetic_total]
        self.assertEqual(len(synthetic), 1)
        self.assertIsNone(synthetic[0].tech_reach)

        plan = ParsedPlan(
            path=Path("dummy.xlsx"),
            placements=placements,
            sheet_meta={},
            tables=[],
            universe=self.U,
            period_start=None,
            period_end=None,
            warnings=[],
            flights=[flight],
        )
        p = ReachParams(
            universe=self.U,
            lag_visible_share=0.65,
            cookie_people=2.4,
            target_affinity=0.65,
            selected_frequencies=(1, 3),
        )
        apply_reach(plan, p)
        summary = flight_channel_kpi_summary(plan, "F1", "OLV", p)
        self.assertIn("target_pct_1p", summary["reach"])
        self.assertLess(summary["reach"]["target_pct_1p"], 1.0)
        self.assertLess(summary["reach"]["target_pct_3p"], summary["reach"]["target_pct_1p"])


if __name__ == "__main__":
    unittest.main()
