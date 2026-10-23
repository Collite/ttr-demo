"""Specs for scripts/dashboards.py — the bundle rules, the generated kustomization, unpacking an export. No cluster.

    just dashboards-test   # = uv run --with pyyaml python3 -B -m unittest scripts/test_dashboards.py
"""

from __future__ import annotations

import importlib.util
import io
import json
import pathlib
import shutil
import sys
import tempfile
import unittest
import zipfile

import yaml

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("dashboards", HERE / "dashboards.py")
dash = importlib.util.module_from_spec(spec)
sys.modules["dashboards"] = dash
spec.loader.exec_module(dash)

CZ = "2203df78-f233-401a-a338-eb2160b5124b"
DS, CH, DB = "11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222", "33333333-3333-3333-3333-333333333333"


def dataset(**kw) -> dict:
    return {"table_name": "stockouts_monthly_dc", "schema": "obj.query", "sql": None, "uuid": DS,
            "database_uuid": CZ, **kw}


def chart(**kw) -> dict:
    context = json.dumps({"datasource": {"id": 9, "type": "table"}, "form_data": {"viz_type": "big_number_total"}})
    return {"slice_name": "Týdny s výpadkem", "viz_type": "big_number_total", "uuid": CH, "dataset_uuid": DS,
            "params": {}, "query_context": context, **kw}


def board(charts=(CH,), **kw) -> dict:
    position = {f"CHART-{i}": {"type": "CHART", "meta": {"uuid": u}} for i, u in enumerate(charts)}
    return {"dashboard_title": "Výpadky", "uuid": DB, "published": True, "position": position, **kw}


class Tree:
    """A dashboards/ root and a model/ beside it, in a temporary directory."""

    def __init__(self, test: unittest.TestCase):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        test.addCleanup(shutil.rmtree, self.tmp)
        self.root, self.model = self.tmp / "dashboards", self.tmp / "model"
        (self.model / "er").mkdir(parents=True)
        (self.model / "er" / "q.ttrm").write_text("def query stockouts_monthly_dc {\n}\ndef entity warehouse {\n}\n")
        self.write("import.yaml", {"worlds": {"cz": {"database": "hartland_cz", "database_uuid": CZ}},
                                   "dashboards": [{"id": "dc", "worlds": ["cz"]}]})
        (self.root / "dc").mkdir(parents=True)
        (self.root / "dc" / "README.md").write_text("# dc\n")
        self.put("datasets", "stockouts-monthly-dc", dataset())
        self.put("charts", "tydny-s-vypadkem", chart())
        self.put("dashboards", "vypadky", board())

    def write(self, rel: str, obj: dict) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(obj, allow_unicode=True, sort_keys=False))

    def put(self, kind: str, name: str, obj: dict) -> None:
        self.write(f"dc/bundle/cz/{kind}/{name}.yaml", obj)

    def problems(self) -> list[str]:
        return dash.problems(self.root, self.model)


class ShippedBundlesSpec(unittest.TestCase):
    def test_the_shipped_bundles_hold_every_rule(self):
        self.assertEqual(dash.problems(), [])

    def test_the_shipped_kustomization_is_current(self):
        self.assertEqual((dash.ROOT / "kustomization.yaml").read_text(encoding="utf-8"), dash.kustomization())

    def test_two_dashboards_in_both_worlds_on_olymps_database_uuids(self):
        m = dash.manifest()
        self.assertEqual({w: v["database_uuid"] for w, v in m["worlds"].items()},
                         {"cz": CZ, "us": "40b6f2ef-bce7-4e58-aedd-4057a8076b88"})
        self.assertEqual({d["id"]: d["worlds"] for d in m["dashboards"]},
                         {"dc-meltdown-stockouts": ["cz", "us"], "returns-by-category": ["cz", "us"]})


class RuleSpec(unittest.TestCase):
    def test_a_clean_bundle_has_no_problems(self):
        self.assertEqual(Tree(self).problems(), [])

    def assertProblem(self, tree: Tree, fragment: str):
        found = tree.problems()
        self.assertTrue(any(fragment in p for p in found), f"no problem with {fragment!r} in {found}")

    def test_olymps_files_stay_out_of_a_bundle(self):
        t = Tree(self)
        t.write("dc/bundle/cz/databases/hartland_cz.yaml", {"database_name": "hartland_cz"})
        t.write("dc/bundle/cz/metadata.yaml", {"version": "1.0.0"})
        self.assertProblem(t, "databases: olymp owns it")
        self.assertProblem(t, "metadata.yaml: olymp owns it")

    def test_a_dataset_names_its_worlds_database(self):
        t = Tree(self)
        t.put("datasets", "stockouts-monthly-dc", dataset(database_uuid="40b6f2ef-bce7-4e58-aedd-4057a8076b88"))
        self.assertProblem(t, "is not hartland_cz's")

    def test_a_dataset_reads_a_model_object_of_the_logical_layer_as_it_is(self):
        t = Tree(self)
        t.put("datasets", "stockouts-monthly-dc", dataset(schema="db.dbo"))
        self.assertProblem(t, "schema 'db.dbo'")
        t.put("datasets", "stockouts-monthly-dc", dataset(table_name="no_such_query"))
        self.assertProblem(t, "is not a `def query` of the model")
        t.put("datasets", "stockouts-monthly-dc", dataset(sql="SELECT 1"))
        self.assertProblem(t, "a virtual dataset")

    def test_every_reference_resolves_inside_the_bundle(self):
        t = Tree(self)
        t.put("charts", "tydny-s-vypadkem", chart(dataset_uuid="44444444-4444-4444-4444-444444444444"))
        self.assertProblem(t, "is not in the bundle")
        t = Tree(self)
        t.put("dashboards", "vypadky", board(charts=(CH, "55555555-5555-5555-5555-555555555555")))
        self.assertProblem(t, "the import would skip the dashboard")

    def test_a_chart_on_no_dashboard_or_without_its_saved_query_is_refused(self):
        t = Tree(self)
        t.put("dashboards", "vypadky", board(charts=()))
        self.assertProblem(t, "on no dashboard")
        t = Tree(self)
        t.put("charts", "tydny-s-vypadkem", chart(query_context=None))
        self.assertProblem(t, "no query_context")
        t.put("charts", "tydny-s-vypadkem", chart(viz_type="table"))
        self.assertProblem(t, "another viz type")

    def test_an_unpublished_dashboard_is_refused(self):
        t = Tree(self)
        t.put("dashboards", "vypadky", board(published=False))
        self.assertProblem(t, "published must be true")

    def test_one_uuid_with_two_contents_is_refused(self):
        t = Tree(self)
        t.write("import.yaml", {"worlds": {"cz": {"database": "hartland_cz", "database_uuid": CZ}},
                                "dashboards": [{"id": "dc", "worlds": ["cz"]}, {"id": "other", "worlds": ["cz"]}]})
        (t.root / "other").mkdir()
        (t.root / "other" / "README.md").write_text("# other\n")
        t.write("other/bundle/cz/datasets/stockouts-monthly-dc.yaml", dataset())  # the same object: fine
        t.write("other/bundle/cz/charts/tydny-s-vypadkem.yaml", chart(slice_name="Jiný název"))
        t.write("other/bundle/cz/dashboards/jine.yaml", board(uuid="66666666-6666-6666-6666-666666666666"))
        found = t.problems()
        self.assertEqual([p for p in found if "datasets/" in p], [])
        self.assertTrue(any("one would overwrite the other" in p and "charts/" in p for p in found), found)

    def test_a_directory_import_yaml_does_not_list_is_refused(self):
        t = Tree(self)
        (t.root / "stray").mkdir()
        self.assertProblem(t, "stray/: not listed in import.yaml")


class KustomizationSpec(unittest.TestCase):
    def test_one_key_per_file_named_by_dashboard_world_kind_and_file(self):
        t = Tree(self)
        text = dash.kustomization(t.root)
        self.assertIn("name: superset-dashboards", text)
        self.assertIn("disableNameSuffixHash: true", text)
        self.assertIn("      - dc.cz.charts.tydny-s-vypadkem.yaml=dc/bundle/cz/charts/tydny-s-vypadkem.yaml", text)
        keys = [line.split("=")[0].strip("- ").strip() for line in text.splitlines() if "=dc/bundle/" in line]
        self.assertEqual(len(keys), 3)
        for key in keys:
            self.assertRegex(key, dash.KEY)

    def test_the_import_jobs_re_nesting_reads_the_kind_back(self):
        # olymp platform/bi/superset-dashboards/base/import.sh: kind = the third dot-separated field.
        for key in dash.bundle_files(Tree(self).root):
            self.assertIn(key.split(".")[2], dash.KINDS)


class UnpackSpec(unittest.TestCase):
    def export(self) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            root = "dashboard_export_20261023T080000"
            z.writestr(f"{root}/metadata.yaml", "version: 1.0.0\ntype: Dashboard\n")
            z.writestr(f"{root}/databases/hartland_cz.yaml", "database_name: hartland_cz\n")
            z.writestr(f"{root}/datasets/hartland_cz/stockouts_monthly_dc.yaml", yaml.safe_dump(dataset()))
            z.writestr(f"{root}/charts/Tydny_s_vypadkem_12.yaml", yaml.safe_dump(chart(), allow_unicode=True))
            z.writestr(f"{root}/charts/Tydny_s_vypadkem_13.yaml",
                       yaml.safe_dump(chart(uuid="77777777-7777-7777-7777-777777777777"), allow_unicode=True))
            z.writestr(f"{root}/dashboards/Vypadky_3.yaml", yaml.safe_dump(board(), allow_unicode=True))
        return buf.getvalue()

    def test_files_are_named_after_their_object_and_olymps_are_dropped(self):
        target = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, target)
        (target / "charts").mkdir()
        (target / "charts" / "stale.yaml").write_text("old: true\n")
        written = dash.unpack(self.export(), target)
        self.assertEqual(sorted(written), ["charts/tydny-s-vypadkem-2.yaml", "charts/tydny-s-vypadkem.yaml",
                                           "dashboards/vypadky.yaml", "datasets/stockouts-monthly-dc.yaml"])
        self.assertFalse((target / "charts" / "stale.yaml").exists())
        self.assertFalse((target / "databases").exists())
        self.assertFalse((target / "metadata.yaml").exists())

    def test_slug_keeps_a_czech_title_readable(self):
        self.assertEqual(dash.slug("Týdny s výpadkem zásob v roce 2025"), "tydny-s-vypadkem-zasob-v-roce-2025")
        self.assertEqual(dash.slug("DC meltdown — stock-outs"), "dc-meltdown-stock-outs")


if __name__ == "__main__":
    unittest.main()
