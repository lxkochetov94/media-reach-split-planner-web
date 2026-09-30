import unittest
from pathlib import Path

from splits import (
    SplitRecord, SplitResult, _canonical_platform, _platform_format_override,
    _month_from_value, _is_social_special_project_text,
)


class SplitsAuditTests(unittest.TestCase):
    def test_aggregate_preserves_plan_and_fact_availability(self):
        result = SplitResult(path=Path("dummy.xlsx"))
        result.records = [
            SplitRecord(
                sheet="Plan", source_row=10, platform="VK", format_group="Social",
                month=1, year=2026, plan_budget=100.0, plan_ac=10.0, plan_total=110.0,
                fact_budget=80.0, fact_ac=8.0, fact_total=88.0, fact_available=True,
            ),
            SplitRecord(
                sheet="Plan", source_row=11, platform="VK", format_group="Social",
                month=2, year=2026, plan_budget=200.0, plan_ac=20.0, plan_total=220.0,
                fact_available=False,
            ),
        ]
        agg = result.aggregate()
        jan = agg["VK"]["Social"][1]
        feb = agg["VK"]["Social"][2]
        self.assertEqual(jan["plan_total"], 110.0)
        self.assertEqual(jan["fact_total"], 88.0)
        self.assertEqual(jan["delta_total"], 22.0)
        self.assertEqual(jan["fact_available_count"], 1.0)

        self.assertEqual(feb["plan_total"], 220.0)
        self.assertEqual(feb["fact_total"], 0.0)
        self.assertEqual(feb["delta_total"], 0.0)
        self.assertEqual(feb["fact_available_count"], 0.0)

    def test_full_date_headers_resolve_real_calendar_month(self):
        self.assertEqual(_month_from_value("01.01.2026 - 31.01.2026"), 1)
        self.assertEqual(_month_from_value("01.02.2026 - 28.02.2026"), 2)
        self.assertEqual(_month_from_value("01.12.2026 - 31.12.2026"), 12)

    def test_lab_split_platform_aliases(self):
        cases = {
            "Go Mobile": "GoMobile",
            "GoMobile": "GoMobile",
            "Mediatuner": "MediaTuner",
            "MediaTuner": "MediaTuner",
            "VOX": "Hybrid",
            "Hybrid": "Hybrid",
            "YABBY": "Yabbi",
            "YABBI": "Yabbi",
            "Yandex.RSYA Ретаргетинг": "Яндекс РСЯ",
            "Promopages.Yandex.ru": "Яндекс ПромоСтраницы",
            "Я. Промостраницы": "Яндекс ПромоСтраницы",
            "Redlama (Тестовая РК)": "RedLlama",
            "RedLlama": "RedLlama",
        }
        for source, expected in cases.items():
            with self.subTest(source=source):
                self.assertEqual(_canonical_platform(source), expected)

    def test_lab_split_format_business_rules(self):
        self.assertEqual(_platform_format_override("GoMobile", "Спецпроекты", "Fullscreen"), "Баннеры")
        self.assertEqual(_platform_format_override("Hybrid", "Спецпроекты", "Native"), "Баннеры")
        self.assertEqual(_platform_format_override("Hybrid", "Техническая строка", "In-image Premium"), "Баннеры")
        self.assertEqual(_platform_format_override("Yabbi", "Social", "Playable Ads"), "Баннеры")
        self.assertEqual(_platform_format_override("Yabbi", "OLV", "True View (Video Placement)"), "OLV")

    def test_social_special_project_detector_for_bloggers(self):
        self.assertTrue(_is_social_special_project_text("Интеграция в канале блогера"))
        self.assertTrue(_is_social_special_project_text("Размещение у блогеров"))

    def test_totals_do_not_treat_missing_fact_as_zero_comparison(self):
        result = SplitResult(path=Path("dummy.xlsx"))
        result.records = [
            SplitRecord(
                sheet="Plan", source_row=10, platform="A", format_group="OLV",
                month=1, year=2026, plan_budget=100.0, plan_ac=0.0, plan_total=100.0,
                fact_budget=80.0, fact_ac=0.0, fact_total=80.0, fact_available=True,
            ),
            SplitRecord(
                sheet="Plan", source_row=11, platform="B", format_group="OLV",
                month=1, year=2026, plan_budget=300.0, plan_ac=0.0, plan_total=300.0,
                fact_available=False,
            ),
        ]
        totals = result.totals()
        self.assertEqual(totals["plan"], 400.0)
        self.assertEqual(totals["fact"], 80.0)
        self.assertEqual(totals["delta"], 20.0)
        self.assertEqual(totals["fact_records"], 1.0)


if __name__ == "__main__":
    unittest.main()
