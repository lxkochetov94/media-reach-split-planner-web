import pathlib
import re
import unittest

import reach_v16 as r


ROOT = pathlib.Path(__file__).resolve().parent


class ReachV16FinalUxContractTests(unittest.TestCase):
    """Small independent smoke contract for the *current* final Reach v1.6 surface.

    Deeper behavior lives in test_reach_v16.py and the LAB/Persil/template fixtures.
    This file intentionally checks only stable user-facing decisions so it does not
    become a second stale specification of the entire UI.
    """

    @classmethod
    def setUpClass(cls):
        cls.js = (ROOT / "reach_v16.js").read_text(encoding="utf-8")
        cls.css = (ROOT / "reach_v16.css").read_text(encoding="utf-8")
        cls.html = (ROOT / "index.html").read_text(encoding="utf-8")
        cls.py = (ROOT / "reach_v16.py").read_text(encoding="utf-8")

    def test_frequency_notation_is_at_not_reach_n_plus(self):
        surface = self.js + "\n" + self.html
        for k in range(1, 7):
            self.assertNotIn(f"Reach {k}+", surface)
            self.assertIn(f"@{k}+", surface)

    def test_model_and_level2_details_are_collapsed_by_default(self):
        self.assertIn('<details class="card v16-model-details">', self.html)
        self.assertNotIn('<details class="card v16-model-details" open>', self.html)
        self.assertIn('<details class="v16-decision ', self.js)
        self.assertNotIn('<details class="v16-decision ${kind}" open>', self.js)

    def test_b_d_l_copy_matches_current_detailed_web_contract(self):
        self.assertIn("B — browser ID на одно web-устройство", self.js)
        self.assertIn("D — устройств на одного человека", self.js)
        self.assertIn("L — период стабильности browser ID Chromium", self.js)
        self.assertIn("рассчитывается автоматически по ЦА", self.js)
        self.assertIn("AUTO использует только K как пользовательский параметр", self.js)

    def test_average_frequency_is_one_decimal_and_spaced(self):
        self.assertIn("num(top.avg_frequency,1)", self.js)
        self.assertIn("num(r.avg_frequency,1)", self.js)
        self.assertIn("на @1+ человека", self.js)
        self.assertIsNone(re.search(r"\d(?:[.,]\d+)?на\s*@", self.js))

    def test_hierarchy_replaces_old_standalone_contribution_table(self):
        surface = self.js + "\n" + self.html
        self.assertNotIn("v16ContributionTable", surface)
        self.assertNotIn("Вклад в Reach, чел.", self.js)
        self.assertIn("v16-hierarchy-toggle", self.js)
        self.assertIn("Показать площадки", self.js)
        self.assertIn("Уровень / объект", self.js)
        self.assertIn("v16-platform-child hidden", self.js)

    def test_effective_reach_is_svg_curve_on_fixed_0_100_axis(self):
        self.assertIn("v16-er-chart", self.js)
        self.assertIn("<polyline points=", self.js)
        self.assertIn('aria-label="Кривая Effective Reach @1+…@6+"', self.js)
        self.assertIn("const grid=[0,25,50,75,100]", self.js)
        self.assertNotIn("const maxPct=Math.max", self.js)
        self.assertIn("fill:#fff1d6", self.css)
        self.assertIn("stroke:#d59a24", self.css)

    def test_user_facing_dedup_uses_people_and_percent_of_gross_reach(self):
        self.assertIn(
            'Дедупликация<span class="v16-th-sub">чел. · % Gross Reach</span>',
            self.js,
        )
        self.assertIn("v16-dedup-cell", self.js)
        self.assertIn("gross-dedup", self.js)

    def test_k_default_and_source_reach_contract_are_current(self):
        catalog = r.model_catalog()
        self.assertEqual(catalog["level2"]["quick_k"], 2.44)
        self.assertIn("function currentK(){return Number($(ids.k)?.value||2.44)}", self.js)
        self.assertIn("SOURCE_REACH_COMPARISON", self.py)
        self.assertNotIn("SOURCE_REACH_CALIBRATION", self.py)
        self.assertIn("Готовый Reach из медиаплана не входит в формулу", self.js)


if __name__ == "__main__":
    unittest.main()
