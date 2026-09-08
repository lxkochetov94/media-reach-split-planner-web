import copy
import datetime as dt
import json
import math
import unittest

import reach_v16 as r
import reach_v16_math as m


U = 15_182_450.0
SOURCE_MP_R1 = 7_563_991.2379
SOURCE_MP_R3 = 3_928_168.6137

# Normalized from the supplied workbook "Mediaplan PHD Digital TEST(2).xlsx".
# Audience Family labels below are test-only confirmed mappings, not facts inferred by the engine.
ROWS = [
    ("August","OLV","VK Video",979591.0,326530.3333333333),
    ("August","OLV","VK Video",297926.0,99308.66666666667),
    ("September","OLV","VK Video",7248825.929622917,2416275.309874306),
    ("September","OLV","VK Video",782166.0,260722.0),
    ("October","OLV","VK Video",1346938.0,448979.3333333333),
    ("October","OLV","VK Video",410400.0,136800.0),
    ("August","OLV","Media Today",2757551.0204081633,919183.6734693878),
    ("September","OLV","Media Today",5000000.0,1666666.6666666667),
    ("October","OLV","Media Today",3791632.6530612246,1263877.5510204083),
    ("August","Banners, CPM","Otclick",3250899.0,1083633.0),
    ("September","Banners, CPM","Otclick",12190872.0,4063624.0),
    ("October","Banners, CPM","Otclick",4469986.0,1489995.3333333333),
    ("August","Banners, CPM","Solta",1481631.0,493877.0),
    ("September","Banners, CPM","Solta",5808450.756607339,1936150.2522024463),
    ("October","Banners, CPM","Solta",2037244.0,679081.3333333334),
    ("August","Social nets, CPM","VK Social",1142857.0,380952.3333333333),
    ("August","Social nets, CPM","VK Social",489795.0,163265.0),
    ("September","Social nets, CPM","VK Social",4285714.0,1428571.3333333333),
    ("September","Social nets, CPM","VK Social",1836734.0,612244.6666666666),
    ("October","Social nets, CPM","VK Social",1571428.0,523809.3333333333),
    ("October","Social nets, CPM","VK Social",673469.0,224489.66666666666),
]

DATES = {
    "August": (dt.date(2026,8,24), dt.date(2026,8,31)),
    "September": (dt.date(2026,9,1), dt.date(2026,9,30)),
    "October": (dt.date(2026,10,1), dt.date(2026,10,11)),
}


def atomic_entity(idx, month, channel, family, impressions, rtech):
    # Source Frequency is 3.00 for every normalized row.
    l1 = m.level1_technical(impressions, 3.00, rtech, frequency_precision=2)
    # "desktop+mobile" does not prove WEB vs APP; canonical AUTO therefore remains Quick.
    l2 = m.level2_quick(l1["R_tech"], U, m.K_DEFAULT)
    # No weekly deduplicated Human Reach is supplied in the workbook.
    l3a = m.aggregate_flight_reach_mode(l2["R_people"], U)
    l3b = m.level3_effective_reach(l3a["R_1p"], impressions)
    return {
        "name": f"row-{idx}",
        "family": family,
        "channel": channel,
        "reach_1p": l3b["reach_1p"],
        "reach_2p": l3b["reach_2p"],
        "reach_3p": l3b["reach_3p"],
        "reach_4p": l3b["reach_4p"],
        "reach_5p": l3b["reach_5p"],
        "reach_6p": l3b["reach_6p"],
        "impressions": l3b["impressions"],
        "freq_dist": l3b["freq_dist"],
        "exact_counts": l3b["exact_counts"],
        "avg_frequency": l3b["avg_frequency"],
    }


def calculate_fixture():
    atoms = [
        (row[0], atomic_entity(i+1, *row))
        for i, row in enumerate(ROWS)
    ]
    flights = []
    detail = []
    for month in ("August","September","October"):
        month_atoms = [ent for mth, ent in atoms if mth == month]
        channels = []
        for channel_name in ("OLV","Banners, CPM","Social nets, CPM"):
            ch_atoms = [x for x in month_atoms if x["channel"] == channel_name]
            by_family = {}
            for ent in ch_atoms:
                by_family.setdefault(ent["family"], []).append(ent)
            families = []
            for family_name, family_atoms in by_family.items():
                fam = m.audience_merge(
                    family_atoms, U,
                    neutral_unstructured=True,
                    model_path="L4A_FAMILY",
                )
                fam["name"] = family_name
                fam["addressable_universe"] = U
                families.append(fam)
            channel = m.audience_merge(
                families, U,
                neutral_unstructured=True,
                model_path="L4B_CHANNEL",
            )
            channel["name"] = channel_name
            channel["addressable_universe"] = U
            channels.append(channel)
            detail.append({
                "month": month,
                "channel": channel_name,
                "families": len(families),
                "reach_1p": channel["reach_1p"],
                "reach_3p": channel["reach_3p"],
            })
        flight = m.level5_flight(channels, U)
        flight.update({
            "name": month,
            "start": DATES[month][0],
            "end": DATES[month][1],
            "is_common": False,
            "addressable_universe": U,
        })
        flights.append(flight)

    line = m.level6_line(flights, U)
    line["name"] = "Сила Актив"
    line["addressable_universe"] = U
    line["addressable_universe_assumed"] = True
    brand = m.level7_brand([line], U)
    return atoms, flights, line, brand, detail


class LabPlanCanonicalFixtureTests(unittest.TestCase):
    def test_uploaded_plan_normalized_fixture_end_to_end(self):
        atoms, flights, line, brand, detail = calculate_fixture()
        self.assertEqual(len(atoms), 21)
        self.assertEqual(len(flights), 3)
        total_i = sum(ent["impressions"] for _m, ent in atoms)
        self.assertAlmostEqual(total_i, sum(x[3] for x in ROWS), delta=1e-5)
        self.assertAlmostEqual(brand["reach_1p"], line["reach_1p"], delta=1e-5)
        self.assertAlmostEqual(brand["reach_3p"], line["reach_3p"], delta=1e-5)
        self.assertTrue(all(
            line[f"reach_{k}p"] >= line[f"reach_{k+1}p"] - 1e-5
            for k in range(1,6)
        ))
        self.assertLessEqual(line["reach_1p"], U + 1e-5)
        self.assertLessEqual(line["reach_3p"], total_i/3 + 1e-5)

        result = {
            "U": U,
            "rows": len(atoms),
            "impressions": total_i,
            "source_workbook_reach_1p": SOURCE_MP_R1,
            "source_workbook_reach_3p": SOURCE_MP_R3,
            "canonical_line_reach_1p": line["reach_1p"],
            "canonical_line_reach_2p": line["reach_2p"],
            "canonical_line_reach_3p": line["reach_3p"],
            "canonical_line_reach_4p": line["reach_4p"],
            "canonical_line_reach_5p": line["reach_5p"],
            "canonical_line_reach_6p": line["reach_6p"],
            "canonical_reach_1p_pct": line["reach_1p"]/U,
            "canonical_reach_3p_pct": line["reach_3p"]/U,
            "avg_human_frequency": line["avg_frequency"],
            "line_dedup_rate": line["dedup_rate"],
            "flight_reach_1p": {f["name"]: f["reach_1p"] for f in flights},
            "flight_reach_3p": {f["name"]: f["reach_3p"] for f in flights},
            "l6_lambda": line.get("flight_relaxation_lambda"),
            "l6_model_path": line.get("model_path"),
            "source_delta_r1": line["reach_1p"] - SOURCE_MP_R1,
            "source_delta_r3": line["reach_3p"] - SOURCE_MP_R3,
            "family_mapping_basis": "TEST_ONLY_CONFIRMED_MAPPING",
            "l2_path": "QUICK_K_2_44_BECAUSE_ENVIRONMENT_NOT_CONFIRMED",
            "l3a_path": "AGGREGATE_FLIGHT_REACH_MODE",
        }
        print("LAB_FIXTURE_RESULT=" + json.dumps(result, ensure_ascii=False, sort_keys=True))

    def test_uploaded_plan_source_curve_calibration_matches_workbook_baseline(self):
        _atoms, _flights, line, _brand, _detail = calculate_fixture()
        source_curve = {
            1: 0.49820623403302366,
            2: 0.32831948449969445,
            3: 0.2587308776679805,
            4: 0.14757881045720347,
        }
        calibrated = copy.deepcopy(line)
        reference = copy.deepcopy(line)
        r._calibrate_result_to_source(calibrated, reference, source_curve, U)
        self.assertTrue(calibrated.get("source_calibrated"))
        self.assertAlmostEqual(calibrated["reach_1p"], SOURCE_MP_R1, delta=2.0)
        self.assertAlmostEqual(calibrated["reach_3p"], SOURCE_MP_R3, delta=2.0)
        self.assertAlmostEqual(calibrated["reach_1p"] / U, source_curve[1], places=8)
        self.assertAlmostEqual(calibrated["reach_3p"] / U, source_curve[3], places=8)


if __name__ == "__main__":
    unittest.main()
