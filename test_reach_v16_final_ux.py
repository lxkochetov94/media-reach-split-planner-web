import pathlib
import re
import unittest

import reach_v16 as r


ROOT = pathlib.Path(__file__).resolve().parent


class ReachV16FinalUxContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = (ROOT / "reach_v16.js").read_text(encoding="utf-8")
        cls.html = (ROOT / "index.html").read_text(encoding="utf-8")

    def test_frequency_notation_is_at_not_reach_n_plus(self):
        surface = self.js + "\n" + self.html
        for k in range(1, 7):
            self.assertNotIn(f"Reach {k}+", surface)
            self.assertIn(f"@{k}+", surface)

    def test_model_map_is_collapsed_by_default(self):
        self.assertIn('<details class="card v16-model-details">', self.html)
        self.assertNotIn('<details class="card v16-model-details" open>', self.html)

    def test_b_d_l_are_defined_in_card_headers(self):
        self.assertIn("B — browser ID на одно web-устройство", self.js)
        self.assertIn("D — устройств на одного человека", self.js)
        self.assertIn("L — стабильность browser ID Chromium", self.js)
        self.assertIn("рассчитывается автоматически по ЦА", self.js)
        self.assertNotIn("Остальное определяется автоматически", self.js)

    def test_l2_details_are_collapsed_by_default(self):
        self.assertIn('<details class="v16-decision ', self.js)
        self.assertNotIn('<details class="v16-decision ${kind}" open>', self.js)

    def test_average_frequency_is_one_decimal_and_spaced(self):
        self.assertIn("num(top.avg_frequency,1)", self.js)
        self.assertIn("num(r.avg_frequency,1)", self.js)
        self.assertIn("на @1+ человека", self.js)
        self.assertIsNone(re.search(r"\d(?:[.,]\d+)?на\s*@", self.js))

    def test_contribution_table_is_business_hierarchy(self):
        self.assertIn("<th>Канал</th><th>Площадка</th><th>Формат</th>", self.js)
        self.assertIn("Итого ${esc(r.channel||'')}", self.js)
        self.assertIn("Вклад в Reach, чел.", self.js)
        self.assertIn("Эксклюзивная аудитория, чел.", self.js)
        self.assertIn("Учтённая часть пересечений, чел.", self.js)
        cell_match = re.search(r"const cell=\(value\)=>\`([^\n]+)\`", self.js)
        self.assertIsNotNone(cell_match)
        self.assertNotIn("человек", cell_match.group(1))

    def test_effective_reach_has_real_curve_and_compact_rows(self):
        self.assertIn("<polyline points=", self.js)
        self.assertIn("v16-profile-grid compact", self.js)
        self.assertIn('aria-label="Кривая Effective Reach @1+…@6+"', self.js)

    def test_user_facing_dedup_is_split_into_people_and_percent(self):
        self.assertIn('Дедупликация<span class="v16-th-sub">чел. · % gross</span>', self.js)
        self.assertIn("v16-dedup-cell", self.js)
        self.assertIn("gross-dedup", self.js)

    def test_quick_k_remains_canonical_default_not_fake_calibration(self):
        catalog = r.model_catalog()
        self.assertEqual(catalog["level2"]["quick_k"], 2.40)
        self.assertIn("фиксированный рабочий model default методологии v1.6", self.js)
        self.assertIn("не измеренный универсальный коэффициент рынка", self.js)


if __name__ == "__main__":
    unittest.main()
