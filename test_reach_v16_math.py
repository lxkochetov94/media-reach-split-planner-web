import datetime as dt
import math
import unittest

import reach_v16_math as m


def entity(name, reach, impressions=None, freq=None, **extra):
    if impressions is None:
        impressions = reach * (freq or 2.0)
    f = impressions / reach if reach else 1.0
    fd = m.poisson_lognormal_frequency(f)["exact"] if reach else [1, 0, 0, 0, 0, 0]
    out = {
        "name": name,
        "reach_1p": float(reach),
        "impressions": float(impressions),
        "freq_dist": fd,
    }
    out.update(extra)
    return out


class CanonicalReachMathTests(unittest.TestCase):
    def test_l1_precision_aware_validation(self):
        out = m.level1_technical(1000, 2.50, 400, frequency_precision=2)
        self.assertEqual(out["R_tech"], 400)
        self.assertAlmostEqual(out["frequency_tolerance"], 0.005)
        with self.assertRaises(m.ReachValidationError):
            m.level1_technical(1000, 2.52, 400, frequency_precision=2)

    def test_l1_precision_assumed_flag(self):
        out = m.level1_technical(1000, 2.5, None)
        self.assertAlmostEqual(out["R_tech"], 400)
        self.assertTrue(any(d["code"] == "F_PRECISION_ASSUMED" for d in out["diagnostics"]))

    def test_l2_quick_no_clip(self):
        self.assertAlmostEqual(m.level2_quick(2400, 1000)["R_people"], 1000)
        with self.assertRaises(m.ReachValidationError):
            m.level2_quick(2500, 1000)
        with self.assertRaises(m.ReachValidationError):
            m.level2_quick(1000, 1000, .9)

    def test_l2_web_advanced_chain(self):
        out = m.level2_advanced(
            3_000_000, 15_000_000,
            environment="WEB", duration_days=28, frequency=3,
            web_device_universe=18_000_000, B=1.9, D=2.3, L=68,
        )
        self.assertEqual(out["path"], ["2A_BROWSER_CHURN", "2B_BROWSER_SATURATION", "2C_DEVICE_SATURATION"])
        self.assertGreater(out["R_stable"], 0)
        self.assertLessEqual(out["R_people"], 15_000_000)
        self.assertTrue(any(d["code"] == "B_AVERAGED_APPROXIMATION" for d in out["diagnostics"]))

    def test_l2_safari_does_not_use_chromium_l(self):
        out = m.level2_advanced(
            1_000_000, 10_000_000,
            environment="WEB", duration_days=28, frequency=3,
            web_device_universe=12_000_000, B=1.8, D=2.25,
            browser_family="Safari",
        )
        self.assertEqual(out["K_time"], 1.0)
        self.assertTrue(any(d["code"] == "SAFARI_CHURN_NOT_MODELLED" for d in out["diagnostics"]))

    def test_l2_app_requires_device_reach(self):
        with self.assertRaises(m.ReachValidationError):
            m.level2_advanced(1_000_000, 10_000_000, environment="MOBILE_APP", D=2.25)

    def test_l3a_canonical_example(self):
        reaches = [1.8e6, 2.0e6, 2.1e6, 2.0e6, 1.9e6, 1.7e6]
        weekly = [{"week_index": i, "reach": r} for i, r in enumerate(reaches, 1)]
        out = m.temporal_platform_reach(weekly, 10_000_000, profile="BASE")
        self.assertAlmostEqual(out["R_1p"], 4_379_000, delta=5_000)
        self.assertEqual(len(out["incremental"]), 6)
        self.assertTrue(all(
            out["incremental"][i]["cumulative_reach"] <= out["incremental"][i+1]["cumulative_reach"] + 1e-6
            for i in range(5)
        ))

    def test_l3a_neutral_equals_independence(self):
        U = 10_000_000
        rs = [1_000_000, 2_000_000, 1_500_000]
        out = m.temporal_platform_reach(
            [{"week_index": i, "reach": r} for i, r in enumerate(rs, 1)],
            U, profile="NEUTRAL",
        )
        expected = U * (1 - math.prod(1 - r/U for r in rs))
        self.assertAlmostEqual(out["R_1p"], expected, delta=1e-5)

    def test_l3a_gap_decay_uses_active_weeks_only(self):
        out = m.temporal_platform_reach(
            [{"week_index": 1, "reach": 1e6}, {"week_index": 4, "reach": 1e6}],
            10e6, profile="BASE",
        )
        self.assertEqual(out["incremental"][1]["gap_weeks"], 2)
        self.assertAlmostEqual(out["incremental"][1]["rho_eff"], .65**3, places=12)

    def test_aggregate_flight_fallback_is_explicit(self):
        out = m.aggregate_flight_reach_mode(2_000_000, 10_000_000)
        self.assertEqual(out["model_path"], "AGGREGATE_FLIGHT_REACH_MODE")
        self.assertTrue(out["platform_universe_assumed"])

    def test_l3b_frequency_below_one_is_error(self):
        with self.assertRaises(m.ReachValidationError):
            m.level3_effective_reach(1_000_000, 900_000)

    def test_l3b_frequency_one_degenerate(self):
        out = m.level3_effective_reach(1_000_000, 1_000_000)
        self.assertEqual(out["reach_1p"], 1_000_000)
        self.assertEqual(out["reach_2p"], 0)
        self.assertEqual(out["frequency_model"], "DEGENERATE_FREQUENCY_1")

    def test_l3b_poisson_lognormal_curve(self):
        out = m.level3_effective_reach(2_000_000, 6_000_000)
        vals = [out[f"reach_{k}p"] for k in range(1, 7)]
        self.assertTrue(all(vals[i] >= vals[i+1] for i in range(5)))
        self.assertAlmostEqual(sum(out["exact_counts"]), out["reach_1p"], delta=1e-5)
        self.assertAlmostEqual(out["avg_frequency"], 3.0, places=12)
        self.assertLess(abs(out["solver_residual_frequency"]), m.SOLVER_TOL)

    def test_l3b_hard_cap_reoptimizes_mu(self):
        out = m.level3_effective_reach(1_000_000, 3_000_000, hard_cap=4)
        self.assertEqual(out["reach_5p"], 0)
        self.assertEqual(out["reach_6p"], 0)
        with self.assertRaises(m.ReachValidationError):
            m.level3_effective_reach(1_000_000, 5_000_000, hard_cap=4)

    def test_pair_bounds_with_addressability(self):
        lo, hi = m.pair_bounds(6, 6, 10, Ua=8, Ub=8, M=3)
        self.assertEqual(lo, 0)
        self.assertEqual(hi, 3)

    def test_global_feasibility_detects_three_way_infeasible(self):
        U = 10.0
        reaches = [6.0, 6.0, 6.0]
        pairs = {(0,1): 2.0, (0,2): 2.0, (1,2): 2.0}
        out = m.global_feasibility(reaches, U, pairs)
        self.assertFalse(out["feasible"])

    def test_maxent_matches_canonical_three_family_example(self):
        U = 10_000_000
        es = [entity("A", 3_200_000), entity("B", 1_800_000), entity("C", 1_000_000)]
        p = {
            (0,1): {"J": 750_000, "source": "CUSTOM", "rho": 0.1},
            (0,2): {"J": 380_000, "source": "CUSTOM", "rho": 0.1},
            (1,2): {"J": 240_000, "source": "CUSTOM", "rho": 0.1},
        }
        out = m.audience_merge(es, U, pair_details=p, model_path="L4_TEST")
        self.assertTrue(out["feasibility"]["feasible"])
        self.assertTrue(str(out["solver_status"]).startswith("CONVERGED"))
        self.assertAlmostEqual(out["reach_1p"], 4_743_447, delta=3_000)
        self.assertAlmostEqual(sum(x["shapley_people"] for x in out["contributions"]), out["reach_1p"], delta=1e-4)

    def test_unstructured_neutral_uses_closed_form_independence(self):
        U = 10_000_000
        es = [entity("A", 2e6), entity("B", 2e6), entity("C", 2e6)]
        out = m.audience_merge(es, U, neutral_unstructured=True)
        self.assertTrue(out["model_path"].endswith("_INDEPENDENCE"))
        self.assertAlmostEqual(out["reach_1p"], U*(1-.8**3), delta=1e-5)

    def test_l5_relaxes_only_model_default(self):
        U = 10_000_000
        cs = [entity("A", 5e6), entity("B", 5e6), entity("C", 5e6)]
        out = m.level5_flight(cs, U)
        self.assertGreaterEqual(out["relaxation_lambda"], 0)
        self.assertLessEqual(out["relaxation_lambda"], 1)
        self.assertLessEqual(out["reach_1p"], U + 1e-6)

    def test_l6_long_gap_residual_floor(self):
        U = 15_000_000
        a = entity("A", 3e6, start=dt.date(2026,1,1), end=dt.date(2026,1,31), is_common=False)
        b = entity("B", 3e6, start=dt.date(2026,5,1), end=dt.date(2026,5,31), is_common=False)
        meta = m.l6_pair(a, b, U)
        self.assertEqual(meta["q_temporal"], 0)
        self.assertAlmostEqual(meta["J_residual"], 300_000, delta=1)
        self.assertAlmostEqual(meta["J_effective"], 300_000, delta=1)

    def test_l6_aon_requires_real_temporal_slice(self):
        U = 10_000_000
        aon = entity("AON", 5e6, start=dt.date(2026,1,1), end=dt.date(2026,12,31), is_common=True)
        burst = entity("Burst", 2e6, start=dt.date(2026,2,1), end=dt.date(2026,2,28), is_common=False)
        with self.assertRaisesRegex(m.ReachValidationError, "AON_TEMPORAL_APPROXIMATION_REQUIRED"):
            m.l6_pair(aon, burst, U)

    def test_l6_aon_staged_with_upstream_slice(self):
        U = 10_000_000
        aon = entity(
            "AON", 5e6, start=dt.date(2026,1,1), end=dt.date(2026,12,31), is_common=True,
            temporal_slices=[{
                "start": dt.date(2026,2,1), "end": dt.date(2026,2,28),
                "human_reach_1p_slice": 1_000_000, "source": "MEASURED",
            }],
        )
        burst = entity("Burst", 2e6, start=dt.date(2026,2,1), end=dt.date(2026,2,28), is_common=False)
        meta = m.l6_pair(aon, burst, U)
        self.assertTrue(meta["aon_staged"])
        self.assertEqual(meta["A_slice"], 1_000_000)

    def test_two_aon_are_ordinary_simultaneous_pair(self):
        U = 10_000_000
        a = entity("A1", 3e6, start=dt.date(2026,1,1), end=dt.date(2026,12,31), is_common=True)
        b = entity("A2", 2e6, start=dt.date(2026,1,1), end=dt.date(2026,12,31), is_common=True)
        meta = m.l6_pair(a, b, U)
        self.assertFalse(meta.get("aon_staged", False))
        self.assertEqual(meta["gap_days"], 0)

    def test_level7_structured_support(self):
        U = 10_000_000
        lines = [entity("L1", 2e6), entity("L2", 2e6), entity("L3", 1e6)]
        out = m.level7_brand(
            lines, U,
            addressability_map={"forbidden_pairs": [[0, 2]]},
        )
        self.assertEqual(out["brand_addressability_status"], "STRUCTURED")
        self.assertTrue(out["feasibility"]["feasible"])

    def test_impressions_conservation(self):
        U = 10_000_000
        es = [entity("A", 2e6, impressions=4e6), entity("B", 1e6, impressions=3e6)]
        out = m.audience_merge(es, U)
        self.assertEqual(out["impressions"], 7e6)

    def test_normalize_pair_input_union_and_hard_bounds(self):
        out = m.normalize_pair_input(
            {"union": 7_000_000, "source": "MEASURED"},
            4_000_000, 4_000_000, 10_000_000,
        )
        self.assertEqual(out["J"], 1_000_000)
        self.assertEqual(out["source"], "MEASURED")
        with self.assertRaises(m.ReachValidationError):
            m.normalize_pair_input(
                {"J": 5_000_000, "source": "CUSTOM"},
                4_000_000, 4_000_000, 10_000_000,
            )

    def test_l5_measured_addressability_source_is_preserved(self):
        U = 10_000_000
        a = entity("A", 2_000_000, addressable_universe=6_000_000,
                   addressable_intersections={"B": 3_000_000})
        b = entity("B", 2_000_000, addressable_universe=5_000_000)
        pairs, _lam, _diag = m.level5_channel_pairs([a, b], U)
        self.assertEqual(pairs[(0, 1)]["source"], "MEASURED_ADDRESSABLE")
        self.assertEqual(pairs[(0, 1)]["M_source"], "MEASURED_ADDRESSABLE")

    def test_l6_custom_pair_overrides_temporal_default_without_clipping(self):
        U = 10_000_000
        a = entity("A", 3e6, start=dt.date(2026,1,1), end=dt.date(2026,1,31), is_common=False)
        b = entity("B", 3e6, start=dt.date(2026,2,1), end=dt.date(2026,2,28), is_common=False)
        out = m.level6_line(
            [a, b], U,
            custom_pairs={(0,1): {"J": 1_000_000, "source": "MEASURED"}},
        )
        meta = next(iter(out["pair_details"].values()))
        self.assertEqual(meta["J"], 1_000_000)
        self.assertEqual(meta["source"], "MEASURED")
        self.assertAlmostEqual(out["reach_1p"], 5_000_000, delta=1e-5)

    def test_l6_invalid_hard_pair_is_validation_error(self):
        U = 10_000_000
        a = entity("A", 3e6, start=dt.date(2026,1,1), end=dt.date(2026,1,31), is_common=False)
        b = entity("B", 3e6, start=dt.date(2026,2,1), end=dt.date(2026,2,28), is_common=False)
        with self.assertRaises(m.ReachValidationError):
            m.level6_line(
                [a, b], U,
                custom_pairs={(0,1): {"J": 4_000_000, "source": "CUSTOM"}},
            )

    def test_l6_overlap_marks_start_order_attribution(self):
        U = 10_000_000
        a = entity("A", 2e6, start=dt.date(2026,1,1), end=dt.date(2026,1,31), is_common=False)
        b = entity("B", 2e6, start=dt.date(2026,1,15), end=dt.date(2026,2,15), is_common=False)
        out = m.level6_line([a, b], U)
        self.assertTrue(any(d.get("code") == "START_ORDER_ATTRIBUTION" for d in out["diagnostics"]))

    def test_level7_brand_addressability_cells_derive_hard_universes(self):
        U = 10_000_000
        lines = [
            entity("L1", 3_000_000, addressable_universe=U, addressable_universe_assumed=True),
            entity("L2", 2_000_000, addressable_universe=U, addressable_universe_assumed=True),
            entity("L3", 1_000_000, addressable_universe=U, addressable_universe_assumed=True),
        ]
        amap = {"cells": [
            {"cell_id":"all", "population":4_000_000, "eligible_line_mask":["L1","L2","L3"]},
            {"cell_id":"l1", "population":2_000_000, "eligible_line_mask":["L1"]},
            {"cell_id":"l2", "population":1_000_000, "eligible_line_mask":["L2"]},
            {"cell_id":"l3", "population":1_000_000, "eligible_line_mask":["L3"]},
            {"cell_id":"none", "population":2_000_000, "eligible_line_mask":[]},
        ]}
        out = m.level7_brand(lines, U, addressability_map=amap)
        self.assertEqual(out["brand_addressability_status"], "STRUCTURED_CELLS")
        self.assertAlmostEqual(out["derived_line_universes"]["L1"], 6_000_000)
        self.assertAlmostEqual(out["derived_line_universes"]["L2"], 5_000_000)
        self.assertAlmostEqual(out["derived_line_universes"]["L3"], 5_000_000)
        self.assertTrue(out["feasibility"]["feasible"])
        self.assertTrue(str(out["solver_status"]).startswith("CONVERGED"))

    def test_level7_brand_addressability_cells_population_must_equal_brand_u(self):
        lines = [
            entity("L1", 1_000_000, addressable_universe=10_000_000, addressable_universe_assumed=True),
            entity("L2", 1_000_000, addressable_universe=10_000_000, addressable_universe_assumed=True),
        ]
        with self.assertRaises(m.ReachValidationError):
            m.level7_brand(
                lines, 10_000_000,
                addressability_map={"cells":[
                    {"cell_id":"both", "population":5_000_000, "eligible_line_mask":["L1","L2"]},
                ]},
            )

    def test_level7_brand_addressability_cells_reject_reach_above_derived_ul(self):
        U = 10_000_000
        lines = [
            entity("L1", 6_000_000, addressable_universe=U, addressable_universe_assumed=True),
            entity("L2", 1_000_000, addressable_universe=U, addressable_universe_assumed=True),
        ]
        amap = {"cells":[
            {"cell_id":"l1", "population":5_000_000, "eligible_line_mask":["L1"]},
            {"cell_id":"l2", "population":2_000_000, "eligible_line_mask":["L2"]},
            {"cell_id":"none", "population":3_000_000, "eligible_line_mask":[]},
        ]}
        with self.assertRaises(m.ReachValidationError):
            m.level7_brand(lines, U, addressability_map=amap)


if __name__ == "__main__":
    unittest.main()
