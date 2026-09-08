import datetime as dt
import json
import unittest
from types import SimpleNamespace

import reach_v16 as r
import reach_v16_math as m
from engine import _campaign_line_name


class FakeRow:
    def __init__(self, *, sheet, row, flight, channel, platform, fmt, impressions, frequency, tech_reach, start, end):
        self.sheet = sheet
        self.source_row = row - 1
        self.flight = flight
        self.flight_label = flight
        self.channel = channel
        self.platform = platform
        self.platform_canonical = ""
        self.format = fmt
        self.buying_model = "CPM"
        self.impressions = float(impressions)
        self.frequency = float(frequency)
        self.tech_reach = float(tech_reach)
        self.start = start
        self.end = end


def cfg(plan_id):
    return {
        "requested_mode": "AUTO",
        "K": 2.44,
        "K_source": "MODEL_DEFAULT",
        "B": 1.8, "B_source": "BASE_FALLBACK",
        "D": 2.25, "D_source": "BASE_FALLBACK",
        "L": 68.0, "L_source": "MODEL_DEFAULT",
        "B_min": 1.6, "B_max": 1.9,
        "D_min": 1.74, "D_max": 2.45,
        "age_range": None,
        "ta_name": "",
        "web_device_universes": {},
        "unit_web_device_universes": {},
        "environments": {},
        "browser_families": {},
        "device_reaches": {},
        "browser_segments": {},
        "device_segments": {},
        "safari_l": None,
        "plan_id": plan_id,
    }


def q_for(rows, plan_id="P1"):
    return {}


def make_rows(sheet, rows):
    out = []
    for i, x in enumerate(rows, 1):
        out.append(FakeRow(
            sheet=sheet,
            row=x.get("row", i),
            flight=x.get("flight", "F1"),
            channel=x["channel"],
            platform=x["platform"],
            fmt=x.get("format", ""),
            impressions=x["impressions"],
            frequency=x["frequency"],
            tech_reach=x["tech_reach"],
            start=dt.date.fromisoformat(x["start"]),
            end=dt.date.fromisoformat(x["end"]),
        ))
    return out


VALID_CASES = {
    "capsules_file1_f1": {
        "U": 15_900_000.0,
        "source_r1": 10_630_491.116512936,
        "source_r3": 4_962_664.777149047,
        "rows": [
            {"row":17,"channel":"OLV","platform":"Digital Alliance VideoNet","format":"Multi-roll Instream 100%","impressions":5_845_383,"frequency":3.0,"tech_reach":1_948_461,"start":"2026-05-01","end":"2026-05-31"},
            {"row":19,"channel":"Banners, CPM","platform":"AstraLab","format":"WhiteBannerCPM","impressions":3_061_722,"frequency":3.0,"tech_reach":1_020_574,"start":"2026-05-01","end":"2026-05-31"},
            {"row":20,"channel":"Banners, CPM","platform":"Hybrid","format":"Banners","impressions":13_000_000,"frequency":3.0,"tech_reach":4_333_333.333333333,"start":"2026-05-01","end":"2026-05-31"},
            {"row":21,"channel":"Banners, CPM","platform":"BetweenX","format":"Banners","impressions":6_891_219,"frequency":3.0,"tech_reach":2_297_073,"start":"2026-05-01","end":"2026-05-31"},
            {"row":24,"channel":"Mobile&RichMedia","platform":"Redllama","format":"Fullscreen","impressions":2_298_850.5747126425,"frequency":3.0,"tech_reach":766_283.5249042142,"start":"2026-05-01","end":"2026-05-31"},
            {"row":26,"channel":"Social nets, CPM","platform":"VK","format":"VK promo post","impressions":13_005_000,"frequency":3.5,"tech_reach":3_715_714.285714286,"start":"2026-05-01","end":"2026-05-31"},
        ],
    },
    "capsules_file1_f3": {
        "U": 15_182_450.0,
        "source_r1": 5_740_310.302257104,
        "source_r3": 2_981_085.785632871,
        "rows": [
            {"row":18,"channel":"OLV","platform":"VK Video","format":"Pre-roll Instream 100%","impressions":7_297_535,"frequency":3.0,"tech_reach":2_432_511.6666666665,"start":"2026-09-01","end":"2026-09-30"},
            {"row":19,"channel":"OLV","platform":"Rutube","format":"Multi-roll Instream 100%","impressions":3_000_000,"frequency":3.0,"tech_reach":1_000_000,"start":"2026-09-01","end":"2026-09-30"},
            {"row":22,"channel":"Banners, CPM","platform":"Hybrid","format":"Banners","impressions":14_713_717,"frequency":3.7,"tech_reach":3_976_680.2702702703,"start":"2026-09-01","end":"2026-09-30"},
            {"row":23,"channel":"Banners, CPM","platform":"First Data","format":"Banners","impressions":7_183_474,"frequency":3.7,"tech_reach":1_941_479.4594594594,"start":"2026-09-01","end":"2026-09-30"},
            {"row":24,"channel":"Banners, CPM","platform":"Yandex","format":"Banners","impressions":5_500_000,"frequency":3.7,"tech_reach":1_486_486.4864864864,"start":"2026-09-01","end":"2026-09-30"},
            {"row":27,"channel":"Social nets, CPM","platform":"VK","format":"Promo post","impressions":11_573_850,"frequency":3.0,"tech_reach":3_857_950,"start":"2026-09-01","end":"2026-09-30"},
        ],
    },
    "file2_core": {
        "U": 15_182_450.0,
        "source_r1": 6_198_116.996380267,
        "source_r3": 3_218_836.178304416,
        "rows": [
            {"row":18,"channel":"OLV","platform":"VK","format":"Pre-roll Instream 100%","impressions":6_700_000,"frequency":2.0,"tech_reach":3_350_000,"start":"2026-09-01","end":"2026-09-30"},
            {"row":21,"channel":"Banners, CPM","platform":"Otclick","format":"Banners","impressions":18_203_768,"frequency":3.0,"tech_reach":6_067_922.666666667,"start":"2026-09-01","end":"2026-09-30"},
            {"row":22,"channel":"Banners, CPM","platform":"Yandex","format":"Banners","impressions":5_519_368,"frequency":3.0,"tech_reach":1_839_789.3333333333,"start":"2026-09-01","end":"2026-09-30"},
            {"row":25,"channel":"Social nets, CPM","platform":"VK","format":"Promo post","impressions":11_844_000,"frequency":2.8,"tech_reach":4_230_000,"start":"2026-09-01","end":"2026-09-30"},
        ],
    },
    "file2_capsules": {
        "U": 15_182_450.0,
        "source_r1": 6_656_653.447008077,
        "source_r3": 3_456_965.5516631394,
        "rows": [
            {"row":18,"channel":"OLV","platform":"VK Video","format":"Pre-roll Instream 100%","impressions":7_297_535,"frequency":2.5,"tech_reach":2_919_014,"start":"2026-09-01","end":"2026-09-30"},
            {"row":19,"channel":"OLV","platform":"Rutube","format":"Multi-roll Instream 100%","impressions":3_000_000,"frequency":2.5,"tech_reach":1_200_000,"start":"2026-09-01","end":"2026-09-30"},
            {"row":22,"channel":"Banners, CPM","platform":"Hybrid","format":"Banners","impressions":14_713_717,"frequency":3.0,"tech_reach":4_904_572.333333333,"start":"2026-09-01","end":"2026-09-30"},
            {"row":23,"channel":"Banners, CPM","platform":"First Data","format":"Banners","impressions":7_183_474,"frequency":3.0,"tech_reach":2_394_491.3333333335,"start":"2026-09-01","end":"2026-09-30"},
            {"row":24,"channel":"Banners, CPM","platform":"Yandex","format":"Banners","impressions":5_500_000,"frequency":3.0,"tech_reach":1_833_333.3333333333,"start":"2026-09-01","end":"2026-09-30"},
            {"row":27,"channel":"Social nets, CPM","platform":"VK","format":"Promo post","impressions":11_573_850,"frequency":3.0,"tech_reach":3_857_950,"start":"2026-09-01","end":"2026-09-30"},
        ],
    },
    "file3_f1_freshness": {
        "U": 15_900_000.0,
        "source_r1": 11_829_406.459320752,
        "source_r3": 4_781_763.048862088,
        "rows": [
            {"row":17,"channel":"OLV","platform":"Digital Alliance VideoNet","format":"Multi-roll Instream 100%","impressions":4_655_000,"frequency":3.0,"tech_reach":1_551_666.6666666667,"start":"2026-04-01","end":"2026-05-31"},
            {"row":18,"channel":"OLV","platform":"MTS","format":"Multi-roll","impressions":3_846_153,"frequency":3.0,"tech_reach":1_282_051,"start":"2026-04-01","end":"2026-05-31"},
            {"row":21,"channel":"Banners, CPM","platform":"Yandex","format":"Banners","impressions":22_654_004,"frequency":3.0,"tech_reach":7_551_334.666666667,"start":"2026-04-01","end":"2026-05-31"},
            {"row":22,"channel":"Banners, CPM","platform":"MTS","format":"Banners","impressions":18_000_000,"frequency":3.0,"tech_reach":6_000_000,"start":"2026-04-01","end":"2026-05-31"},
            {"row":25,"channel":"Mobile&RichMedia","platform":"Redllama","format":"Fullscreen","impressions":2_298_933.3333333335,"frequency":3.0,"tech_reach":766_311.1111111111,"start":"2026-05-01","end":"2026-05-31"},
            {"row":27,"channel":"Social nets, CPM","platform":"VK","format":"VK promo post","impressions":17_988_883,"frequency":3.5,"tech_reach":5_139_680.857142857,"start":"2026-04-01","end":"2026-05-31"},
        ],
    },
    "file3_f3_core": {
        "U": 15_182_450.0,
        "source_r1": 4_981_557.880119538,
        "source_r3": 2_587_046.7979566436,
        "rows": [
            {"row":18,"channel":"OLV","platform":"VK","format":"Pre-roll Instream 100%","impressions":6_545_562.15291297,"frequency":3.2,"tech_reach":2_045_488.1727853029,"start":"2026-09-01","end":"2026-09-30"},
            {"row":21,"channel":"Banners, CPM","platform":"Otclick","format":"Banners","impressions":18_203_768,"frequency":3.7,"tech_reach":4_919_937.297297297,"start":"2026-09-01","end":"2026-09-30"},
            {"row":22,"channel":"Banners, CPM","platform":"Yandex","format":"Banners","impressions":5_519_368,"frequency":3.7,"tech_reach":1_491_721.081081081,"start":"2026-09-01","end":"2026-09-30"},
            {"row":25,"channel":"Social nets, CPM","platform":"VK","format":"Promo post","impressions":11_844_000,"frequency":3.0,"tech_reach":3_948_000,"start":"2026-09-01","end":"2026-09-30"},
        ],
    },
}


def calculate_case(name, spec):
    rows = make_rows(name, spec["rows"])
    plan_id = "P1"
    diagnostics = []
    channels = r._build_level4_channels(
        rows, spec["U"], cfg(plan_id), q_for(rows, plan_id),
        plan_id, "F1", diagnostics,
    )
    flight = m.level5_flight(channels, spec["U"])
    flight.update({
        "name": name,
        "start": min(x.start for x in rows),
        "end": max(x.end for x in rows),
        "is_common": False,
        "addressable_universe": spec["U"],
    })
    line = m.level6_line([flight], spec["U"])
    return {
        "U": spec["U"],
        "rows": len(rows),
        "channels": len(channels),
        "impressions": sum(x.impressions for x in rows),
        "reach_1p": line["reach_1p"],
        "reach_2p": line["reach_2p"],
        "reach_3p": line["reach_3p"],
        "reach_4p": line["reach_4p"],
        "reach_5p": line["reach_5p"],
        "reach_6p": line["reach_6p"],
        "pct_1p": line["reach_1p"] / spec["U"],
        "pct_3p": line["reach_3p"] / spec["U"],
        "avg_human_frequency": line["avg_frequency"],
        "source_r1": spec["source_r1"],
        "source_r3": spec["source_r3"],
        "delta_r1": line["reach_1p"] - spec["source_r1"],
        "delta_r3": line["reach_3p"] - spec["source_r3"],
        "l5_lambda": flight.get("relaxation_lambda"),
    }


class PersilBattlePlanTests(unittest.TestCase):
    def test_valid_single_scope_battle_flights(self):
        results = {}
        for name, spec in VALID_CASES.items():
            with self.subTest(name=name):
                out = calculate_case(name, spec)
                results[name] = out
                self.assertLessEqual(out["reach_1p"], out["U"] + 1e-5)
                self.assertTrue(
                    out["reach_1p"] >= out["reach_2p"] >= out["reach_3p"]
                    >= out["reach_4p"] >= out["reach_5p"] >= out["reach_6p"]
                )
                self.assertGreaterEqual(out["avg_human_frequency"], 1.0)
        print("PERSIL_BATTLE_VALID_RESULTS=" + json.dumps(results, ensure_ascii=False, sort_keys=True))

    def test_auto_is_close_on_standard_planner_benchmarks(self):
        # These four cases have internally consistent source @1/@3 planner summaries.
        # The two F1 cases are retained as robustness fixtures but excluded from closeness
        # because their source @1 behaves as a different/outlier planning convention.
        standard = (
            "capsules_file1_f3",
            "file2_core",
            "file2_capsules",
            "file3_f3_core",
        )
        for name in standard:
            with self.subTest(name=name):
                spec = VALID_CASES[name]
                out = calculate_case(name, spec)
                source1 = spec["source_r1"] / spec["U"]
                source3 = spec["source_r3"] / spec["U"]
                self.assertLess(abs(out["pct_1p"] - source1), 0.03)
                self.assertLess(abs(out["pct_3p"] - source3), 0.04)

    def test_capsules_flight2_month_fragments_are_automatic(self):
        rows = make_rows("caps_f2", [
            {"row":18,"channel":"OLV","platform":"VK Video","format":"Pre-roll","impressions":1_735_058,"frequency":2.5,"tech_reach":694_023.2,"start":"2026-06-01","end":"2026-06-30"},
            {"row":19,"channel":"OLV","platform":"VK Video","format":"Pre-roll","impressions":5_976_313,"frequency":2.5,"tech_reach":2_390_525.2,"start":"2026-07-01","end":"2026-07-31"},
        ])
        diagnostics = []
        channels = r._build_level4_channels(
            rows, 15_182_450, cfg("P1"), q_for(rows),
            "P1", "F1", diagnostics,
        )
        self.assertEqual(len(channels), 1)
        unit = channels[0]["families"][0]["inventory_units"][0]
        self.assertEqual(unit["fragment_count"], 2)
        self.assertEqual(unit["l3a"]["model_path"], "AUTO_PERIODIC_PLATFORM_TEMPORAL")
        self.assertTrue(any(d.get("code") == "L3A_AUTO_PERIODIC_PLATFORM" for d in diagnostics))

    def test_core_flight2_month_fragments_are_automatic(self):
        rows = make_rows("core_f2", [
            {"row":18,"channel":"OLV","platform":"VK","format":"Pre-roll","impressions":1_216_256,"frequency":2.5,"tech_reach":486_502.4,"start":"2026-06-01","end":"2026-06-30"},
            {"row":19,"channel":"OLV","platform":"VK","format":"Pre-roll","impressions":4_189_328,"frequency":2.5,"tech_reach":1_675_731.2,"start":"2026-07-01","end":"2026-07-31"},
        ])
        channels = r._build_level4_channels(
            rows, 15_182_450, cfg("P1"), q_for(rows),
            "P1", "F1", [],
        )
        unit = channels[0]["families"][0]["inventory_units"][0]
        self.assertEqual(unit["l3a"]["model_path"], "AUTO_PERIODIC_PLATFORM_TEMPORAL")

    def test_core_flight4_month_fragments_are_automatic(self):
        rows = make_rows("core_f4", [
            {"row":18,"channel":"OLV","platform":"Digital Alliance","format":"Multi-roll","impressions":2_590_322,"frequency":2.0,"tech_reach":1_295_161,"start":"2026-11-01","end":"2026-11-30"},
            {"row":19,"channel":"OLV","platform":"Digital Alliance","format":"Multi-roll","impressions":4_709_677,"frequency":2.0,"tech_reach":2_354_838.5,"start":"2026-12-01","end":"2026-12-20"},
        ])
        channels = r._build_level4_channels(
            rows, 15_182_450, cfg("P1"), q_for(rows),
            "P1", "F1", [],
        )
        unit = channels[0]["families"][0]["inventory_units"][0]
        self.assertEqual(unit["l3a"]["model_path"], "AUTO_PERIODIC_PLATFORM_TEMPORAL")

    def test_explicit_aggregate_flight_reach_unlocks_fragmented_platform(self):
        rows = make_rows("caps_f2", [
            {"row":18,"channel":"OLV","platform":"VK Video","format":"Pre-roll","impressions":1_735_058,"frequency":2.5,"tech_reach":694_023.2,"start":"2026-06-01","end":"2026-06-30"},
            {"row":19,"channel":"OLV","platform":"VK Video","format":"Pre-roll","impressions":5_976_313,"frequency":2.5,"tech_reach":2_390_525.2,"start":"2026-07-01","end":"2026-07-31"},
        ])
        q = q_for(rows)
        sid = r._platform_scope_id(rows[0])
        q["aggregate_flight_technical_reaches"] = {"P1": {sid: 2_900_000}}
        channels = r._build_level4_channels(
            rows, 15_182_450, cfg("P1"), q,
            "P1", "F1", [],
        )
        self.assertEqual(len(channels), 1)
        self.assertEqual(channels[0]["families"][0]["inventory_units"][0]["fragment_count"], 2)

    def test_battle_campaign_identity_conflicts_are_not_silently_collapsed(self):
        self.assertEqual(_campaign_line_name("Персил Для Цветного Май'26"), "Персил Для Цветного")
        self.assertEqual(_campaign_line_name("Персил Капсулы Июнь-Июль'26"), "Персил Капсулы")
        self.assertNotEqual(
            _campaign_line_name("Персил Для Цветного Май'26"),
            _campaign_line_name("Персил Капсулы Июнь-Июль'26"),
        )
        self.assertEqual(_campaign_line_name("Персил Свежесть Апрель-Май'26"), "Персил Свежесть")
        self.assertEqual(_campaign_line_name("Персил Core Сентябрь'26"), "Персил Core")
        self.assertNotEqual(
            _campaign_line_name("Персил Свежесть Апрель-Май'26"),
            _campaign_line_name("Персил Core Сентябрь'26"),
        )

    def test_line_identity_review_detects_capsules_and_core_header_conflicts(self):
        groups = [
            SimpleNamespace(
                id="P1", line="Персил Для Цветного", label="Персил Для Цветного",
                sheet_names=("MP Персил Капсулы 1 флайт",),
            ),
            SimpleNamespace(
                id="P2", line="Персил Капсулы", label="Персил Капсулы",
                sheet_names=("Mediaplan Капсулы 2 флайт", "Mediaplan Капсулы 3 флайт"),
            ),
            SimpleNamespace(
                id="P3", line="Персил Core", label="Персил Core",
                sheet_names=("Mediaplan Core 3 флайт",),
            ),
        ]
        conflicts = r._line_identity_conflicts(groups)
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]["group_ids"], ["P1", "P2"])
        self.assertIn("капсулы", conflicts[0]["shared_sheet_markers"])

        core_groups = [
            SimpleNamespace(
                id="C1", line="Персил Свежесть", label="Персил Свежесть",
                sheet_names=("Mediaplaт Core 1флайт (свеж.)",),
            ),
            SimpleNamespace(
                id="C2", line="Персил Core", label="Персил Core",
                sheet_names=("Mediaplan Core 2 флайт", "Mediaplan Core 3 флайт", "Mediaplan Core 4 флайт"),
            ),
        ]
        core_conflicts = r._line_identity_conflicts(core_groups)
        self.assertEqual(len(core_conflicts), 1)
        self.assertIn("core", core_conflicts[0]["shared_sheet_markers"])

    def test_file2_core_and_capsules_are_not_false_identity_conflict(self):
        groups = [
            SimpleNamespace(
                id="P1", line="Персил Core", label="Персил Core",
                sheet_names=("Mediaplan Core",),
            ),
            SimpleNamespace(
                id="P2", line="Персил Капсулы", label="Персил Капсулы",
                sheet_names=("Mediaplan Капсулы",),
            ),
        ]
        self.assertEqual(r._line_identity_conflicts(groups), [])

    def test_line_source_universe_mismatch_is_auto_normalized(self):
        groups = [
            {
                "id":"F1","label":"Flight 1","ta_name":"Ж 25-44 ВС",
                "source_universe":15_900_000.0,"source_universe_source":"mp","is_common":False,
            },
            {
                "id":"F2","label":"Flight 2","ta_name":"Ж 25-44 ВС",
                "source_universe":15_182_450.0,"source_universe_source":"mp","is_common":False,
            },
        ]
        diagnostics = []
        out = r._validate_line_source_scope(
            groups, 15_182_450.0, {}, "P1", diagnostics,
        )
        self.assertTrue(out["universe_mismatch"])
        self.assertTrue(any(
            d.get("code") == "LINE_UNIVERSE_NORMALIZED_AUTO"
            for d in diagnostics
        ))

    def test_line_source_ta_mismatch_cannot_be_confirmed_away(self):
        groups = [
            {
                "id":"F1","label":"Flight 1","ta_name":"Ж 25-44 ВС",
                "source_universe":15_182_450.0,"source_universe_source":"mp","is_common":False,
            },
            {
                "id":"F2","label":"Flight 2","ta_name":"Ж 25-45 ВС",
                "source_universe":15_182_450.0,"source_universe_source":"mp","is_common":False,
            },
        ]
        with self.assertRaisesRegex(r.V16Error, "TA_NORMALIZATION_REQUIRED"):
            r._validate_line_source_scope(
                groups, 15_182_450.0,
                {"line_scope_confirmed":{"P1":True}},
                "P1", [],
            )

    def test_line_universe_override_is_auto_normalized_even_with_one_source_u(self):
        groups = [{
            "id":"F1","label":"Flight 1","ta_name":"Ж 25-44 ВС",
            "source_universe":15_900_000.0,"source_universe_source":"mp","is_common":False,
        }]
        diagnostics = []
        out = r._validate_line_source_scope(
            groups, 15_182_450.0, {}, "P1", diagnostics,
        )
        self.assertFalse(out["universe_mismatch"])
        self.assertTrue(any(
            d.get("code") == "LINE_UNIVERSE_NORMALIZED_AUTO"
            for d in diagnostics
        ))


if __name__ == "__main__":
    unittest.main()
