import datetime as dt
import math
import unittest
from types import SimpleNamespace

import reach_v16 as r


def ent(name, reach, impressions=None, start=None, end=None, common=False):
    if impressions is None:
        impressions = reach * 2.0
    f = impressions / reach if reach else 1.0
    return {
        "name": name,
        "reach_1p": float(reach),
        "impressions": float(impressions),
        "freq_dist": r.poisson_lognormal_exact(f),
        "start": start,
        "end": end,
        "is_common": common,
    }


class FakeRow:
    def __init__(self, impressions=None, frequency=None, tech_reach=None, row=1):
        self.impressions = impressions
        self.frequency = frequency
        self.tech_reach = tech_reach
        self.sheet = "Test"
        self.source_row = row - 1


class ReachV16Tests(unittest.TestCase):
    def test_model_catalog_exposes_agreed_ranges(self):
        c = r.model_catalog()
        self.assertEqual(c["level2"]["quick_k"], 2.40)
        self.assertEqual(c["level2"]["chromium_l_days"], 68.0)
        self.assertEqual(c["level3"]["temporal_rho_profiles"]["BASE"], 0.65)
        self.assertEqual(c["level3"]["sigma_default"], 2.50)
        self.assertEqual(c["level3"]["sigma_calibration_iqr"], [2.42, 2.90])
        self.assertEqual(c["level5"]["rho_channel_target"], -0.35)
        self.assertEqual(c["level6"]["residual_cap"], 0.10)

    def test_shapley_and_exclusive_contributions_sum_to_union(self):
        U = 10_000_000
        es = [ent("A", 2_000_000), ent("B", 2_500_000), ent("C", 1_500_000)]
        pt = {(0,1): 500_000, (0,2): 300_000, (1,2): 375_000}
        out = r.merge_entities(es, U, pair_targets=pt, model_path="TEST")
        contrib = out["contributions"]
        self.assertEqual(len(contrib), 3)
        self.assertAlmostEqual(sum(x["shapley_people"] for x in contrib), out["reach_1p"], delta=1e-3)
        self.assertTrue(all(x["exclusive_people"] >= 0 for x in contrib))
        self.assertGreaterEqual(out["dedup_rate"], 0.0)

    def test_advanced_age_weighted_defaults_for_25_45(self):
        rec = r.recommended_advanced_factors("Ж 25-45 ВС")
        self.assertAlmostEqual(rec["B"], (10*1.90 + 10*1.90 + 1*1.75) / 21, places=6)
        self.assertAlmostEqual(rec["D"], (10*2.35 + 10*2.25 + 1*2.15) / 21, places=6)
        self.assertEqual(rec["B_source"], "AGE_WIDTH_APPROXIMATION")
        self.assertEqual(rec["D_source"], "AGE_WIDTH_APPROXIMATION")
        self.assertEqual(rec["B_min"], 1.75)
        self.assertEqual(rec["B_max"], 1.90)
        self.assertEqual(rec["D_min"], 2.15)
        self.assertEqual(rec["D_max"], 2.35)

    def test_advanced_web_level2_invariants(self):
        out = r.level2_advanced_web(
            rtech=3_000_000,
            U=15_000_000,
            T=28,
            F=3.0,
            U_D=18_000_000,
            B=1.90,
            D=2.30,
            L=68,
        )
        self.assertGreater(out["R_stable"], 0)
        self.assertGreater(out["R_device"], 0)
        self.assertGreater(out["R_people"], 0)
        self.assertLessEqual(out["R_people"], 15_000_000)
        self.assertGreaterEqual(out["K_time"], 1.0)

    def test_advanced_web_requires_capacity_validity(self):
        with self.assertRaises(r.V16Error):
            r.level2_advanced_web(
                rtech=10_000_000,
                U=1_000_000,
                T=28,
                F=3.0,
                U_D=1_000_000,
                B=1.0,
                D=1.0,
                L=68,
            )

    def test_json_serializes_nested_dates(self):
        payload = {
            "lines": [{
                "flights": [{
                    "start": dt.date(2026, 1, 1),
                    "end": dt.datetime(2026, 1, 31, 12, 30),
                }]
            }]
        }
        encoded = r._json(payload)
        self.assertIn('"start":"2026-01-01"', encoded)
        self.assertIn('"end":"2026-01-31T12:30:00"', encoded)

    def test_l1_frequency_below_one_is_error(self):
        row = FakeRow(impressions=1000, frequency=0.8, tech_reach=None)
        with self.assertRaises(r.V16Error):
            r.level1_technical(row, [])

    def test_l1_inconsistent_triad_is_error(self):
        row = FakeRow(impressions=1000, frequency=2.0, tech_reach=800)
        with self.assertRaises(r.V16Error):
            r.level1_technical(row, [])

    def test_l2_k_domain_and_universe(self):
        with self.assertRaises(r.V16Error):
            r.level2_quick(1000, 1000, 0.99)
        with self.assertRaises(r.V16Error):
            r.level2_quick(2500, 1000, 2.0)
        self.assertAlmostEqual(r.level2_quick(2400, 1000, 2.4), 1000)

    def test_frequency_exactly_one_is_degenerate(self):
        self.assertEqual(r.poisson_lognormal_exact(1.0), [1, 0, 0, 0, 0, 0])

    def test_frequency_curve_is_valid(self):
        g = r.poisson_lognormal_exact(3.0)
        self.assertAlmostEqual(sum(g), 1.0, places=8)
        self.assertTrue(all(x >= 0 for x in g))
        cumulative = [sum(g[i:]) for i in range(6)]
        self.assertTrue(all(cumulative[i] >= cumulative[i+1] for i in range(5)))

    def test_l5_common_lambda_relaxation(self):
        U = 10_000_000
        channels = [ent("A", 5_000_000), ent("B", 5_000_000), ent("C", 5_000_000)]
        diagnostics = []
        out = r.level5_flight(channels, U, diagnostics)
        self.assertLessEqual(out["reach_1p"], U + 1e-6)
        self.assertGreaterEqual(out["relaxation_lambda"], 0)
        self.assertLessEqual(out["relaxation_lambda"], 1)
        if out["relaxation_lambda"] < 1 - 1e-6:
            self.assertTrue(any(d.get("code") == "DEFAULT_RELAXED_FOR_GLOBAL_FEASIBILITY" and d.get("level") == 5 for d in diagnostics))

    def test_l6_long_gap_has_nonzero_residual_but_cap(self):
        U = 15_000_000
        a = ent("A", 3_000_000, start=dt.date(2026,1,1), end=dt.date(2026,1,31))
        b = ent("B", 3_000_000, start=dt.date(2026,5,1), end=dt.date(2026,5,31))
        j, meta = r._l6_pair_basic(a, b, U)
        self.assertEqual(meta["q_temporal"], 0.0)
        self.assertGreater(j, 0.0)
        self.assertLessEqual(meta["J_residual"], 0.10 * 3_000_000 + 1e-6)
        self.assertAlmostEqual(j, 300_000, delta=1)

    def test_l6_three_flights_can_override_residual_cap_only_for_feasibility(self):
        U = 10_000_000
        flights = [
            ent("F1", 4_000_000, start=dt.date(2026,1,1), end=dt.date(2026,1,31)),
            ent("F2", 4_000_000, start=dt.date(2026,5,1), end=dt.date(2026,5,31)),
            ent("F3", 4_000_000, start=dt.date(2026,9,1), end=dt.date(2026,9,30)),
        ]
        diagnostics = []
        out = r.level6_line(flights, U, diagnostics)
        self.assertLessEqual(out["reach_1p"], U + 1e-5)
        self.assertGreater(out["flight_relaxation_lambda"], 1.0)
        self.assertTrue(any(d.get("code") == "RESIDUAL_CAP_OVERRIDDEN_BY_GLOBAL_FEASIBILITY" for d in diagnostics))

    def test_two_aon_are_normal_simultaneous_pair(self):
        U = 10_000_000
        a = ent("AON1", 3_000_000, start=dt.date(2026,1,1), end=dt.date(2026,12,31), common=True)
        b = ent("AON2", 2_000_000, start=dt.date(2026,1,1), end=dt.date(2026,12,31), common=True)
        diagnostics = []
        _, meta = r._l6_pair(a, b, U, diagnostics)
        self.assertFalse(meta.get("aon_staged", False))
        self.assertFalse(any(d.get("code") == "AON_STAGED_MERGE" for d in diagnostics))

    def test_aon_burst_without_temporal_slice_is_blocked(self):
        U = 10_000_000
        aon = ent("AON", 5_000_000, start=dt.date(2026,1,1), end=dt.date(2026,12,31), common=True)
        burst = ent("Burst", 2_000_000, start=dt.date(2026,2,1), end=dt.date(2026,2,28), common=False)
        diagnostics = []
        with self.assertRaisesRegex(r.V16Error, "AON_TEMPORAL_APPROXIMATION_REQUIRED"):
            r._l6_pair(aon, burst, U, diagnostics)

    def test_maxent_merge_preserves_invariants(self):
        U = 10_000_000
        es = [ent("A", 2_000_000), ent("B", 2_500_000), ent("C", 1_500_000)]
        pt = {(0,1): 500_000, (0,2): 300_000, (1,2): 375_000}
        out = r.merge_entities(es, U, pair_targets=pt, model_path="TEST")
        self.assertLessEqual(out["reach_1p"], U + 1e-6)
        vals = [out[f"reach_{i}p"] for i in range(1,7)]
        self.assertTrue(all(vals[i] >= vals[i+1] - 1e-6 for i in range(5)))

    def test_pair_input_priority_and_normalization(self):
        U = 10_000_000
        es = [
            {"name":"A", "reach_1p":3_000_000, "addressable_universe":U},
            {"name":"B", "reach_1p":2_000_000, "addressable_universe":U},
        ]
        specs = [
            {"a":"A","b":"B","source":"CUSTOM","J":700_000},
            {"a":"A","b":"B","source":"MEASURED","union":4_600_000},
        ]
        raw = r._pair_raw_by_index(es, specs)
        self.assertEqual(raw[(0,1)]["source"], "MEASURED")
        norm = r._normalized_pair_details(es, U, specs, default_rho=0.0)
        self.assertAlmostEqual(norm[(0,1)]["J"], 400_000)
        self.assertEqual(norm[(0,1)]["source"], "MEASURED")

    def test_brand_scope_contract_and_identity(self):
        U = 10_000_000
        a = ent("L1", 3_000_000, start=dt.date(2026,1,1), end=dt.date(2026,3,31))
        a.update({
            "ta_name":"Women 25-55","brand":"X","plan_id":"P1","universe":U,
            "addressable_universe":U,"addressable_universe_assumed":True,
        })
        q = {
            "brand_scope_confirmed": True,
            "brand_master_ta": "Women 25-55",
            "brand_master_geo": "РФ",
            "brand_horizon_start": "2026-01-01",
            "brand_horizon_end": "2026-12-31",
        }
        out = r._brand_merge([a], U, [], q)
        self.assertAlmostEqual(out["reach_1p"], a["reach_1p"])
        self.assertEqual(out["brand_master_geo"], "РФ")

    def test_ta_mismatch_blocks_brand_total(self):
        U = 10_000_000
        a = ent("L1", 3_000_000, start=dt.date(2026,1,1), end=dt.date(2026,3,31))
        b = ent("L2", 2_000_000, start=dt.date(2026,4,1), end=dt.date(2026,6,30))
        a.update({"ta_name":"Women 25-55","brand":"X","plan_id":"P1"})
        b.update({"ta_name":"Women 18-34","brand":"X","plan_id":"P2"})
        q = {
            "brand_scope_confirmed": True,
            "brand_master_ta": "Women 25-55",
            "brand_master_geo": "РФ",
            "brand_horizon_start": "2026-01-01",
            "brand_horizon_end": "2026-12-31",
        }
        with self.assertRaisesRegex(r.V16Error, "TA_NORMALIZATION_REQUIRED"):
            r._brand_merge([a,b], U, [], q)


    def test_reach_buying_model_scope_is_automatic(self):
        def row(model, *, platform="Test", placement_class="Баннеры"):
            return SimpleNamespace(
                buying_model=model, platform=platform, platform_canonical="",
                placement_class=placement_class, placement_class_reason="",
            )
        self.assertTrue(r._reach_buying_model_eligible(row("CPM")))
        self.assertTrue(r._reach_buying_model_eligible(row("CPV", placement_class="OLV")))
        for model in ("CPC", "CPR", "CPA", "CPI", "CPO", "CPL", "CPCV", "CPE", "CPS", "OTHER"):
            with self.subTest(model=model):
                self.assertFalse(r._reach_buying_model_eligible(row(model)))
        self.assertFalse(r._reach_buying_model_eligible(row("CPM", platform="Adriver", placement_class="")))

    def test_promopages_buying_model_controls_reach_and_channel(self):
        def row(model, fmt):
            return SimpleNamespace(
                buying_model=model, platform="Яндекс ПромоСтраницы", platform_canonical="",
                format=fmt, raw_text="", placement_class="Статьи",
                placement_class_reason="", channel="Статьи",
            )
        cpc = row("CPC", "Статья")
        cpr = row("CPR", "Статья")
        cpm = row("CPM", "Медийный баннер")
        cpv = row("CPV", "Video pre-roll")
        cpcv = row("CPCV", "Video pre-roll")
        self.assertFalse(r._reach_buying_model_eligible(cpc))
        self.assertFalse(r._reach_buying_model_eligible(cpr))
        self.assertFalse(r._reach_buying_model_eligible(cpcv))
        self.assertTrue(r._reach_buying_model_eligible(cpm))
        self.assertTrue(r._reach_buying_model_eligible(cpv))
        self.assertEqual(r._reach_channel(cpm), "Banners")
        self.assertEqual(r._reach_channel(cpv), "OLV")

    def test_avito_native_does_not_inherit_olv_section(self):
        row = SimpleNamespace(
            buying_model="CPM", platform="Avito", platform_canonical="",
            format="Нативный формат", raw_text="", placement_class="Native",
            placement_class_reason="", channel="OLV",
        )
        self.assertEqual(r._reach_channel(row), "Native")
        self.assertEqual(r._auto_environment([row]), "WEB")

    def test_environment_is_inferred_from_plan_text(self):
        base = dict(
            buying_model="CPM", platform_canonical="", raw_text="",
            placement_class="", placement_class_reason="", channel="Banners",
        )
        web = SimpleNamespace(**base, platform="Avito", format="Нативный формат")
        app = SimpleNamespace(**base, platform="Test", format="Mobile app interstitial")
        ctv = SimpleNamespace(**base, platform="Test", format="Smart TV CTV video")
        unknown = SimpleNamespace(**base, platform="Test", format="Generic inventory")
        self.assertEqual(r._auto_environment([web]), "WEB")
        self.assertEqual(r._auto_environment([app]), "MOBILE_APP")
        self.assertEqual(r._auto_environment([ctv]), "CTV")
        self.assertEqual(r._auto_environment([unknown]), "WEB")

    def test_aon_slice_is_modelled_automatically_from_source_delivery(self):
        U = 10_000_000.0
        aon_row = SimpleNamespace(
            sheet="Plan", source_row=9, flight="FA", flight_label="Always-on",
            channel="Banners", platform="Test Platform", platform_canonical="",
            format="Banner", buying_model="CPM", placement_class="Баннеры",
            placement_class_reason="", raw_text="",
            impressions=12_000_000.0, frequency=3.0, tech_reach=4_000_000.0,
            start=dt.date(2026, 1, 1), end=dt.date(2026, 12, 31),
        )
        flights = [
            {
                "name":"Always-on", "flight_id":"FA", "is_common":True,
                "start":dt.date(2026,1,1), "end":dt.date(2026,12,31),
            },
            {
                "name":"Flight 1", "flight_id":"F1", "is_common":False,
                "start":dt.date(2026,2,1), "end":dt.date(2026,2,28),
            },
        ]
        cfg = {
            "requested_mode":"AUTO", "K":2.4, "K_source":"MODEL_DEFAULT",
            "B":1.8, "B_source":"BASE_FALLBACK",
            "D":2.25, "D_source":"BASE_FALLBACK",
            "L":68.0, "L_source":"MODEL_DEFAULT",
            "B_min":1.6, "B_max":1.9, "D_min":1.74, "D_max":2.45,
            "age_range":None, "ta_name":"",
            "web_device_universes":{}, "unit_web_device_universes":{},
            "environments":{}, "browser_families":{}, "device_reaches":{},
            "browser_segments":{}, "device_segments":{}, "safari_l":None,
            "plan_id":"P1",
        }
        diagnostics = []
        r._attach_aon_slices(
            flights, {}, "P1", diagnostics,
            source_rows_by_flight={"FA":[aon_row]}, U=U, cfg=cfg,
        )
        slices = flights[0].get("temporal_slices") or []
        self.assertEqual(len(slices), 1)
        self.assertEqual(slices[0]["burst_flight_id"], "F1")
        self.assertEqual(slices[0]["source"], "MODELLED_FROM_SOURCE_DELIVERY")
        self.assertGreater(slices[0]["human_reach_1p_slice"], 0)
        self.assertLess(slices[0]["human_reach_1p_slice"], 4_000_000)
        self.assertTrue(any(d.get("code") == "AON_TEMPORAL_FOOTPRINT" for d in diagnostics))


if __name__ == "__main__":
    unittest.main()
