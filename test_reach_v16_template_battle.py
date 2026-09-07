import datetime as dt
import unittest

import reach_v16 as r
from engine import (
    _invalid_explicit_date_warnings,
    _sheet_scenario_name,
    extract_metadata,
    parse_period,
    parse_period_intervals,
)
from xlsx_reader import SheetData


class FakeRow:
    def __init__(
        self, *, sheet="MediaPlan", row=1, flight="F1", channel="OLV",
        platform="VK", fmt="Video", buying_model="CPM",
        impressions=None, frequency=None, tech_reach=None,
        start=dt.date(2026, 1, 1), end=dt.date(2026, 1, 31),
    ):
        self.sheet = sheet
        self.source_row = row - 1
        self.flight = flight
        self.flight_label = flight
        self.channel = channel
        self.platform = platform
        self.platform_canonical = ""
        self.format = fmt
        self.buying_model = buying_model
        self.impressions = impressions
        self.frequency = frequency
        self.tech_reach = tech_reach
        self.start = start
        self.end = end
        self.budget = 1000.0


class FakePlan:
    def __init__(self, rows):
        self._rows = list(rows)

    def detail_rows(self, flight_ids=None):
        if not flight_ids:
            return list(self._rows)
        allowed = set(flight_ids)
        return [x for x in self._rows if x.flight in allowed]


class MixedTemplateBattleTests(unittest.TestCase):
    def test_mixed_funnel_rows_only_ready_rows_enter_reach_scope(self):
        rows = [
            FakeRow(row=1, platform="VK", impressions=3_000_000, frequency=3.0, tech_reach=1_000_000),
            FakeRow(row=2, platform="SlickJump", impressions=2_000_000, frequency=2.0, tech_reach=1_000_000),
            FakeRow(row=3, platform="Yandex.Direct", channel="Perfomance", buying_model="CPC",
                    impressions=4_000_000, frequency=None, tech_reach=None),
            FakeRow(row=4, platform="ORM", channel="Other", buying_model="OTHER",
                    impressions=None, frequency=None, tech_reach=None),
        ]
        plan = FakePlan(rows)
        units = r._inventory_units(plan)
        excluded = r._excluded_reach_rows(rows)
        self.assertEqual([x["platform"] for x in units], ["VK", "SlickJump"])
        self.assertEqual(len(excluded), 2)
        self.assertEqual(excluded[0]["reason"], "BUYING_MODEL_NOT_REACH_ELIGIBLE")
        self.assertEqual(excluded[1]["reason"], "BUYING_MODEL_NOT_REACH_ELIGIBLE")

    def test_cpc_awareness_row_without_frequency_is_not_given_invented_reach(self):
        row = FakeRow(
            platform="Mobidriven", channel="Rich Media", buying_model="CPC",
            impressions=3_287_000, frequency=None, tech_reach=None,
        )
        state = r._reach_row_state(row)
        self.assertFalse(state["ready"])
        self.assertEqual(state["reason"], "BUYING_MODEL_NOT_REACH_ELIGIBLE")

    def test_platform_month_fragments_are_exposed_as_one_level3_scope(self):
        rows = [
            FakeRow(row=18, flight="F2", channel="OLV", platform="VK Video",
                    impressions=1_735_058, frequency=2.5, tech_reach=694_023.2,
                    start=dt.date(2026, 6, 1), end=dt.date(2026, 6, 30)),
            FakeRow(row=19, flight="F2", channel="OLV", platform="VK Video",
                    impressions=5_976_313, frequency=2.5, tech_reach=2_390_525.2,
                    start=dt.date(2026, 7, 1), end=dt.date(2026, 7, 31)),
        ]
        units = r._inventory_units(FakePlan(rows))
        reqs = r._platform_scope_requirements(units)
        self.assertEqual(len(reqs), 1)
        self.assertEqual(reqs[0]["fragment_count"], 2)
        self.assertEqual(reqs[0]["platform"], "VK Video")
        self.assertIsNone(reqs[0]["required_input"])
        self.assertEqual(reqs[0]["auto_path"], "AUTO_PERIODIC_PLATFORM_TEMPORAL")

    def test_vernel_battle_ta_mismatch_is_hard_error(self):
        groups = [
            {"id":"F1","label":"1 флайт","ta_name":"Ж 25-45 BC","source_universe":15_851_000.0,
             "source_universe_source":"mp","is_common":False},
            {"id":"F2","label":"2 флайт","ta_name":"Ж 25-35 BC","source_universe":7_333_270.0,
             "source_universe_source":"mp","is_common":False},
            {"id":"F3","label":"3 флайт","ta_name":"Ж 25-45 BC","source_universe":15_182_450.0,
             "source_universe_source":"mp","is_common":False},
        ]
        with self.assertRaisesRegex(r.V16Error, "TA_NORMALIZATION_REQUIRED"):
            r._validate_line_source_scope(
                groups, 15_182_450.0,
                {"line_scope_confirmed":{"P1":True}},
                "P1", [],
            )

    def test_sila_active_battle_universe_mismatch_needs_confirmation(self):
        groups = [
            {"id":"F1","label":"1 флайт","ta_name":"Ж 25-45 BC","source_universe":15_968_000.0,
             "source_universe_source":"mp","is_common":False},
            {"id":"F3","label":"3 флайт","ta_name":"Ж 25-45 BC","source_universe":15_182_450.0,
             "source_universe_source":"mp","is_common":False},
        ]
        with self.assertRaisesRegex(r.V16Error, "L6_SCOPE_UNIVERSE_MISMATCH"):
            r._validate_line_source_scope(groups, 15_182_450.0, {}, "P1", [])
        self.assertTrue(
            r._validate_line_source_scope(
                groups, 15_182_450.0,
                {"line_scope_confirmed":{"P1":True}},
                "P1", [],
            )["universe_mismatch"]
        )

    def test_source_reach_curve_invalid_is_detected_not_repaired(self):
        sheet = SheetData("Mediaplan 1 флайт", [
            [None, None, "Охват аудитории Ж 25-45 BC, %@1+", 0.21404589943574448],
            [None, None, "Охват аудитории Ж 25-45 BC, %@3+", 0.5025129759719775],
        ])
        meta = extract_metadata(sheet, 2026)
        self.assertAlmostEqual(meta.source_reach_pct_curve[1], 0.21404589943574448)
        self.assertAlmostEqual(meta.source_reach_pct_curve[3], 0.5025129759719775)
        self.assertTrue(any("SOURCE_REACH_CURVE_INVALID" in x for x in meta.source_validation_warnings))

    def test_valid_source_reach_curve_has_no_curve_error(self):
        sheet = SheetData("Valid", [
            [None, None, "Охват аудитории Ж 25-45 BC, %@1+", 0.2559230334342674],
            [None, None, "Охват аудитории Ж 25-45 BC, %@3+", 0.13290719090341777],
        ])
        meta = extract_metadata(sheet, 2026)
        self.assertFalse(any("SOURCE_REACH_CURVE_INVALID" in x for x in meta.source_validation_warnings))

    def test_explicit_reversed_year_range_is_not_silently_swapped(self):
        bad = "24.02.2025 - 28.02.2024"
        self.assertEqual(parse_period_intervals(bad, 2025), [])
        self.assertEqual(parse_period(bad, 2025), (None, None))
        sheet = SheetData("MediaPlan", [[bad]])
        warnings = _invalid_explicit_date_warnings(sheet, 2025)
        self.assertEqual(len(warnings), 1)
        self.assertIn("SOURCE_DATE_RANGE_INVALID", warnings[0])
        self.assertIn("A1", warnings[0])

    def test_additional_budget_sheet_is_explicit_scenario(self):
        self.assertEqual(_sheet_scenario_name("MediaPlan_доп бюджет"), "Доп. бюджет")
        self.assertEqual(_sheet_scenario_name("MediaPlan"), "")
        self.assertEqual(_sheet_scenario_name("MediaPlan additional budget"), "Доп. бюджет")


if __name__ == "__main__":
    unittest.main()
