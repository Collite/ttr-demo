"""Specs for scripts/bi-one-number.py's pure half (the case schema, reading the number off a leg) — no cluster.

    just bi-one-number-test   # = uv run --with pyyaml --with httpx python3 -B -m unittest scripts/test_bi_one_number.py
"""

from __future__ import annotations

import copy
import decimal
import importlib.util
import json
import pathlib
import shutil
import sys
import tempfile
import types
import unittest

import httpx
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
        # review-131 R4: the tile is 17 for one DC or five; the per-DC table says whom Superset read as.
        self.assertEqual((legs["superset-analyst"]["dcs"], legs["superset-dc-manager"]["dcs"]), (5, 1))
        self.assertEqual(legs["superset-analyst"]["dc_chart"], legs["superset-dc-manager"]["dc_chart"])


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

    def test_a_superset_leg_counts_the_dcs_on_the_tiles_per_dc_table(self):
        c = copy.deepcopy(self.case)
        del self.leg(c, "superset-dc-manager")["dcs"]
        self.assertTrue(any("dcs must be the number of DCs" in p for p in self.problems(c)))
        c = copy.deepcopy(self.case)
        self.leg(c, "superset-dc-manager")["dcs"] = [5]  # a list of keys is the edge's; the table shows labels
        self.assertTrue(any("dcs must be the number of DCs" in p for p in self.problems(c)))
        c = copy.deepcopy(self.case)
        del self.leg(c, "superset-analyst")["dc_chart"]
        self.assertTrue(any("dc_chart needs one uuid per world" in p for p in self.problems(c)))
        c = copy.deepcopy(self.case)
        self.leg(c, "superset-analyst")["dc_chart"]["cz"] = "65572edb-2694-4098-b3ef-761b8ee7e738"  # the tile itself
        self.assertTrue(any("is a big_number_total, not a table" in p for p in self.problems(c)))

    def test_the_table_must_be_on_the_tiles_dashboard(self):
        other = next(u for u, ch in bon.bundle_charts("cz").items()
                     if ch["viz"] == "table" and u != "4fe88cbc-d951-4118-b6d8-f444f54690fc")  # returns-by-category's
        c = copy.deepcopy(self.case)
        self.leg(c, "superset-analyst")["dc_chart"]["cz"] = other
        self.assertTrue(any("on no dashboard together" in p for p in self.problems(c)))

    def test_a_key_of_another_via_is_unknown(self):
        # review-131 R10: one key set for every via let a `chart` on an edge leg pass.
        c = copy.deepcopy(self.case)
        self.leg(c, "edge-analyst")["chart"] = self.leg(c, "superset-analyst")["chart"]
        self.leg(c, "saved-query")["dcs"] = 5
        ps = self.problems(c)
        self.assertTrue(any("unknown key 'chart' for a edge leg" in p for p in ps), ps)
        self.assertTrue(any("unknown key 'dcs' for a iris leg" in p for p in ps), ps)

    def test_pending_says_why(self):
        c = copy.deepcopy(self.case)
        self.leg(c, "superset-analyst")["pending"] = " "
        self.assertTrue(any("pending must say" in p for p in self.problems(c)))

    def test_two_legs_with_one_id_are_caught(self):
        c = copy.deepcopy(self.case)
        c["legs"].append(copy.deepcopy(c["legs"][0]))
        self.assertTrue(any("twice" in p for p in self.problems(c)))


class BundleChartsSpec(unittest.TestCase):
    def setUp(self):
        bon.bundle_charts.cache_clear()
        self.addCleanup(bon.bundle_charts.cache_clear)

    def test_only_the_bundles_import_yaml_lists_are_read(self):
        # review-131 R10: a glob over */bundle/<world>/charts/ also read bundles the import never sees.
        tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        (tmp / "import.yaml").write_text(yaml.safe_dump({"worlds": {"cz": {}}, "dashboards": [{"id": "dc", "worlds": ["cz"]}]}))
        for did, u in (("dc", "11111111-1111-1111-1111-111111111111"), ("stray", "22222222-2222-2222-2222-222222222222")):
            (tmp / did / "bundle" / "cz" / "charts").mkdir(parents=True)
            (tmp / did / "bundle" / "cz" / "charts" / "c.yaml").write_text(yaml.safe_dump({"uuid": u, "viz_type": "table"}))
        real = bon.dash.bundle_files
        bon.dash.bundle_files = lambda root=tmp: real(root)
        self.addCleanup(setattr, bon.dash, "bundle_files", real)
        self.assertEqual(set(bon.bundle_charts("cz")), {"11111111-1111-1111-1111-111111111111"})

    def test_the_shipped_tile_and_table_share_the_dc_meltdown_dashboard(self):
        charts = bon.bundle_charts("cz")
        tile, table = charts["65572edb-2694-4098-b3ef-761b8ee7e738"], charts["4fe88cbc-d951-4118-b6d8-f444f54690fc"]
        self.assertEqual((tile["viz"], table["viz"]), ("big_number_total", "table"))
        self.assertTrue(tile["dashboards"] & table["dashboards"])


class FakeSuperset:
    """Superset and Keycloak as the runner meets them: the sign-in form, the chart by uuid, its saved query."""

    BASE = "https://superset.test"

    def __init__(self, tile_rows: list[dict], table_rows: list[dict], data_pages: dict | None = None):
        self.rows = {"10": tile_rows, "11": table_rows}
        self.pages = data_pages or {}  # chart id → a list of responses served before its rows

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/login/keycloak":
            return httpx.Response(200, html='<form id="kc" action="https://keycloak.test/auth?x=1&amp;y=2" method="post">')
        if request.url.host == "keycloak.test":
            return httpx.Response(302, headers={"location": f"{self.BASE}/superset/welcome/"})
        if path == "/superset/welcome/":
            return httpx.Response(200, html="<html>welcome</html>")
        if path.startswith("/api/v1/chart/") and not path.endswith("/data/"):
            uuid = path.rsplit("/", 1)[-1]
            return httpx.Response(200, json={"result": {"id": {"tile": 10, "table": 11}[uuid]}})
        if path.endswith("/data/"):
            cid = path.split("/")[4]
            if self.pages.get(cid):
                return self.pages[cid].pop(0)
            return httpx.Response(200, json={"result": [{"data": self.rows[cid]}]})
        if request.url.host == "oauth.test":
            return httpx.Response(200, html="<html>You can close this window</html>")
        return httpx.Response(404, text="not found")


REDIRECT = httpx.Response(422, json={"errors": [{"error_type": "OAUTH2_REDIRECT", "extra": {"url": "https://oauth.test/hop"}}]})


class SupersetLegSpec(unittest.TestCase):
    ARGS = types.SimpleNamespace(superset=FakeSuperset.BASE, timeout=5.0)
    TILE = [{"stockout_weeks_sum": 17}]

    def leg(self, fake: FakeSuperset, dcs: int):
        return bon.superset_leg(self.ARGS, "petr", "pw", "tile", "table", "stockout_weeks_sum", dcs,
                                transport=httpx.MockTransport(fake))

    def test_the_dc_manager_seeing_five_dcs_fails_although_the_tile_says_17(self):
        five = [{"warehouse_name": f"DC {i}", "stockout_weeks_sum": 17 if i == 5 else 0} for i in range(1, 6)]
        self.assertEqual(self.leg(FakeSuperset(self.TILE, five), 1), (None, 5, "sees 5 DCs, should see 1"))

    def test_the_dc_manager_seeing_one_dc_passes(self):
        self.assertEqual(self.leg(FakeSuperset(self.TILE, [{"warehouse_name": "Brno DC"}]), 1), (17.0, 1, None))

    def test_the_first_read_follows_the_oauth2_hop_and_reads_again(self):
        fake = FakeSuperset(self.TILE, [{"warehouse_name": "Brno DC"}], {"10": [REDIRECT]})
        self.assertEqual(self.leg(fake, 1), (17.0, 1, None))

    def test_a_second_oauth2_redirect_says_the_exchange_did_not_take(self):
        fake = FakeSuperset(self.TILE, [], {"10": [REDIRECT, REDIRECT]})
        got, n, err = self.leg(fake, 1)
        self.assertIsNone(got)
        self.assertIn("the token exchange did not take", err)

    def test_an_html_error_page_is_reported_with_its_status_and_url_not_as_a_json_error(self):
        # review-131 R10: d.json() came before the status, so a 502 from the proxy read as JSONDecodeError.
        fake = FakeSuperset(self.TILE, [], {"10": [httpx.Response(502, html="<html>Bad gateway</html>")]})
        got, n, err = self.leg(fake, 1)
        self.assertIsNone(got)
        self.assertIn("502", err)
        self.assertIn("/api/v1/chart/10/data/", err)
        self.assertNotIn("JSONDecodeError", err)


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
