"""Specs for scripts/bi-one-number.py's pure half (the case schema, reading the number off a leg) — no cluster.

    just bi-one-number-test   # = uv run --with pyyaml --with httpx python3 -B -m unittest scripts/test_bi_one_number.py
"""

from __future__ import annotations

import copy
import decimal
import importlib.util
import pathlib
import shutil
import sys
import tempfile
import unittest

import yaml

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("bi_one_number", HERE / "bi-one-number.py")
bon = importlib.util.module_from_spec(spec)
sys.modules["bi_one_number"] = bon
spec.loader.exec_module(bon)

CASE = HERE.parent / "run-set" / "bi-one-number" / "stockout-weeks-dc5-2025.yaml"


class ShippedCaseSpec(unittest.TestCase):
    def test_the_shipped_cases_have_no_schema_problems(self):
        cases, problems = bon.load_cases(CASE.parent)
        self.assertEqual(problems, [])
        self.assertEqual([c["id"] for c in cases], ["stockout-weeks-dc5-2025"])

    def test_the_number_is_the_seed_incident_and_the_oracle_is_act_3_5s(self):
        c = yaml.safe_load(CASE.read_text())
        self.assertEqual((c["expect"], c["dc"]), (17, 5))
        self.assertEqual(c["oracle"], "../routing/validation/dc5-stockout-weeks-2025.yaml")

    def test_every_path_is_a_leg_and_the_tile_is_read_by_both_personas(self):
        legs = {leg["id"]: leg for leg in yaml.safe_load(CASE.read_text())["legs"]}
        self.assertEqual({leg["via"] for leg in legs.values()}, {"edge", "iris", "superset"})
        self.assertEqual(legs["edge-dc-manager"]["dcs"], [5])  # the row rule: the DC manager sees DC 5 only
        self.assertEqual(legs["saved-query"]["pattern"], "warehouse_stockout_week_count")
        self.assertEqual(legs["superset-analyst"]["chart"], legs["superset-dc-manager"]["chart"])
        self.assertEqual({legs[i]["persona"] for i in ("superset-analyst", "superset-dc-manager")}, {"analyst", "dc_manager"})
        self.assertEqual(legs["superset-analyst"]["value"], "stockout_weeks_sum")
        self.assertIn("obj.query.stockouts_monthly_dc", legs["edge-analyst"]["sql"])


class SchemaSpec(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.root = self.tmp / "bi-one-number"
        self.root.mkdir()
        (self.tmp / "routing" / "validation").mkdir(parents=True)
        shutil.copy(CASE.parent.parent / "routing" / "validation" / "dc5-stockout-weeks-2025.yaml",
                    self.tmp / "routing" / "validation")
        self.case = yaml.safe_load(CASE.read_text())

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def problems(self, case: dict, stem: str = "stockout-weeks-dc5-2025") -> list[str]:
        (self.root / f"{stem}.yaml").write_text(yaml.safe_dump(case, allow_unicode=True))
        return bon.load_cases(self.root)[1]

    def leg(self, case: dict, lid: str) -> dict:
        return next(leg for leg in case["legs"] if leg["id"] == lid)

    def test_a_copy_of_the_shipped_case_is_clean(self):
        self.assertEqual(self.problems(self.case), [])

    def test_the_id_is_the_filename_stem(self):
        self.assertTrue(any("filename stem" in p for p in self.problems(self.case, "other")))

    def test_a_missing_oracle_and_a_non_number_are_caught(self):
        c = copy.deepcopy(self.case)
        c["oracle"], c["expect"] = "../routing/validation/nope.yaml", "seventeen"
        ps = self.problems(c)
        self.assertTrue(any("is not a file" in p for p in ps))
        self.assertTrue(any("expect must be a number" in p for p in ps))

    def test_a_leg_must_say_how_and_as_whom(self):
        c = copy.deepcopy(self.case)
        self.leg(c, "edge-analyst")["via"] = "jdbc"
        self.leg(c, "saved-query")["persona"] = "cfo"
        del self.leg(c, "edge-dc-manager")["dcs"]
        del self.leg(c, "iris-monthly")["question"]["en"]
        ps = self.problems(c)
        for want in ("via 'jdbc'", "persona 'cfo'", "dcs must be", "both languages"):
            self.assertTrue(any(want in p for p in ps), (want, ps))

    def test_a_superset_leg_names_a_big_number_tile_of_each_worlds_bundle(self):
        c = copy.deepcopy(self.case)
        del self.leg(c, "superset-analyst")["chart"]["us"]
        self.assertTrue(any("one uuid per world" in p for p in self.problems(c)))
        c = copy.deepcopy(self.case)
        self.leg(c, "superset-analyst")["chart"]["cz"] = "00000000-0000-0000-0000-000000000000"
        self.assertTrue(any("in no cz bundle" in p for p in self.problems(c)))
        c = copy.deepcopy(self.case)
        self.leg(c, "superset-analyst")["chart"]["cz"] = "dd74b7a4-1e5a-49c2-ae3c-4a7864bb2c6e"  # the cz bars
        self.assertTrue(any("not a big-number tile" in p for p in self.problems(c)))

    def test_pending_says_why(self):
        c = copy.deepcopy(self.case)
        self.leg(c, "superset-analyst")["pending"] = " "
        self.assertTrue(any("pending must say" in p for p in self.problems(c)))

    def test_two_legs_with_one_id_are_caught(self):
        c = copy.deepcopy(self.case)
        c["legs"].append(copy.deepcopy(c["legs"][0]))
        self.assertTrue(any("twice" in p for p in self.problems(c)))


class ReadingSpec(unittest.TestCase):
    EDGE = [{"warehouse": 1, "stockout_weeks": decimal.Decimal("0")}, {"warehouse": 5, "stockout_weeks": decimal.Decimal("17")}]

    def test_the_dc_row_gives_the_number(self):
        self.assertEqual(bon.per_dc(self.EDGE, "stockout_weeks", 5, 2), (17.0, [1, 5], None))

    def test_the_dc_manager_seeing_another_dc_is_a_failure_even_with_the_right_number(self):
        got, seen, err = bon.per_dc(self.EDGE, "stockout_weeks", 5, [5])
        self.assertIsNone(got)
        self.assertIn("should see [5]", err)

    def test_a_missing_dc_and_a_wrong_count_are_failures(self):
        self.assertIn("DC 5 is not in the rows", bon.per_dc(self.EDGE[:1], "stockout_weeks", 5, 1)[2])
        self.assertIn("should see 5", bon.per_dc(self.EDGE, "stockout_weeks", 5, 5)[2])
        self.assertEqual(bon.per_dc([], "stockout_weeks", 5, 1)[2], "no rows")

    def test_the_composer_names_the_column_so_a_part_of_the_name_finds_it(self):
        months = [{"warehouse_name": "Brno DC", "mesic": "2025-08-01", "pocet_tydnu_stockout": 5},
                  {"warehouse_name": "Brno DC", "mesic": "2025-09-01", "pocet_tydnu_stockout": "4"}]
        self.assertEqual(bon.summed(months, "stockout"), (9.0, None))

    def test_an_exact_name_wins_over_a_longer_one(self):
        rows = [{"stockout_weeks": 17, "stockout_weeks_share": 0.3}]
        self.assertEqual(bon.summed(rows, "stockout_weeks"), (17.0, None))

    def test_an_ambiguous_or_absent_column_and_a_non_number_are_failures(self):
        self.assertIn("names 2 columns", bon.summed([{"stockout_a": 1, "stockout_b": 2}], "stockout")[1])
        self.assertIn("no column named like", bon.summed([{"weeks": 1}], "stockout")[1])
        self.assertIn("not a number", bon.summed([{"stockout_weeks": "n/a"}], "stockout")[1])

    def test_the_verdict_is_the_number_against_expect(self):
        self.assertEqual(bon.judge(17.0, None, 17.0), (True, None))
        self.assertEqual(bon.judge(16.0, None, 17.0), (False, "16 ≠ 17"))
        self.assertEqual(bon.judge(None, "no rows", 17.0), (False, "no rows"))


if __name__ == "__main__":
    unittest.main()
