"""XM rig regressions use invented catalog fixtures and fake kubectl responses."""

import importlib.util
import io
import json
import os
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "xm_rig", Path(__file__).with_name("verify_openmetadata.py")
)
rig = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rig)

FQN = "hartland-pg.hartland_us.public.store_sales"
TERM = "hartland Entities.store_sales"
ZERO = dict(not_modified=False, snapshot="fixture-1", created=0, updated=0, deprecated=0, linked=0, warnings=0)


def catalog():
    table = {
        "fullyQualifiedName": FQN,
        "extension": {
            "ttrQname": "db.dbo.store_sales",
            "ttrUrl": "https://studio.hartland.collite.cz/m/hartland/s/db",
        },
        "tags": [{"tagFQN": "Tatrman.Grounded"}, {"tagFQN": TERM, "source": "Glossary"}],
        "columns": [
            {
                "name": "ss_item_sk",
                "extension": {"ttrQname": "db.dbo.store_sales.ss_item_sk"},
                "tags": [{"tagFQN": "Tatrman.Grounded"}],
            }
        ],
    }
    term = {
        "fullyQualifiedName": TERM,
        "glossary": {"name": "hartland Entities"},
        "extension": {"ttrQname": "er.entity.store_sales", "ttrUrl": "https://studio.hartland.collite.cz/m/hartland/s/er"},
    }
    metric = {
        "extension": {"ttrQname": "md.measure.revenue", "ttrAdditivity": "additive", "ttrUrl": "https://studio.hartland.collite.cz/m/hartland/s/md"},
        "metricExpression": {"code": "sum"},
    }

    for item, label in ((table, "database"), (term, "E-R"), (metric, "dimensional")):
        item["extension"]["ttrStudioLink"] = {
            "url": item["extension"]["ttrUrl"], "displayText": f"Open {label} model in Studio"
        }

    class FakeCatalog:
        def get(self, path):
            if path == "metadata/types/name/hyperlink-cp":
                return {"id": "native-hyperlink-type"}
            if path == "metadata/types/name/string":
                return {"id": "string-type"}
            if path.startswith("metadata/types/"):
                return {"customProperties": [
                    {"name": "ttrStudioLink", "propertyType": {"id": "native-hyperlink-type"}},
                    {"name": "ttrUrl", "propertyType": {"id": "string-type"}},
                ]}
            return {"version": "2.0.6"}

        def tables(self):
            return [table, {"fullyQualifiedName": FQN.replace("hartland_us", "hartland_cz")}]

        def terms(self):
            return [term]

        def store_sales(self):
            return table

        def listing(self, *args):
            return [metric]

    return FakeCatalog()


def jobs():
    return [
        {
            "metadata": {"name": f"fixture-{n}", "creationTimestamp": f"2026-10-25T0{n}:00:00Z"},
            "status": {
                "succeeded": 1,
                "startTime": f"2026-10-25T0{n}:00:00Z",
                "completionTime": f"2026-10-25T0{n}:01:00Z",
            },
        }
        for n in (1, 2)
    ]


def pod_response(name):
    return json.dumps({"items": [
        {"metadata": {"name": name + "-failed"}, "status": {"phase": "Failed"}},
        {"metadata": {"name": name}, "status": {"phase": "Succeeded"}},
    ]})


class RigTests(unittest.TestCase):
    def setUp(self):
        self.env = {"OM_MIN_TABLES": "1", "OM_MIN_ENTITIES": "1", "OM_MIN_METRICS": "1"}

    def test_nine_catalog_checks_pass_with_retained_links(self):
        checks = rig.checks(catalog(), self.env)
        self.assertEqual(len(checks), 10)
        for _, check in checks[:-1]:
            self.assertTrue(check())

    def test_attribute_count_cannot_replace_missing_entity_roots(self):
        cat = catalog()
        cat.terms()[0]["parent"] = {"id": "parent"}
        with self.assertRaises(ValueError):
            dict(rig.checks(cat, self.env))["Entities glossary"]()

    def test_foreign_glossary_tag_cannot_satisfy_term_asset_link(self):
        cat = catalog()
        cat.store_sales()["tags"][1]["tagFQN"] = "foreign.missing"
        with self.assertRaises(ValueError):
            dict(rig.checks(cat, self.env))["term-to-asset link"]()

    def test_url_rejects_the_retired_viewer_route(self):
        cat = catalog()
        cat.store_sales()["extension"]["ttrUrl"] = (
            "https://studio.hartland.collite.cz/viewer?qname=wrong"
        )
        with self.assertRaises(ValueError):
            dict(rig.checks(cat, self.env))["Studio URL"]()

    def test_summary_rejects_absent_duplicate_and_negative_counters(self):
        for text in (
            "",
            "{}",
            json.dumps(ZERO) + "\n" + json.dumps(ZERO),
            json.dumps({**ZERO, "updated": -1}),
        ):
            with self.assertRaises(ValueError):
                rig.summary(text)

    def test_model_links_reject_wrong_workspace_subject_or_extra_query(self):
        for path in ("/m/foreign/s/db", "/m/hartland/s/er", "/m/hartland/s/db?sel=ignored"):
            cat = catalog()
            cat.store_sales()["extension"]["ttrUrl"] = "https://studio.hartland.collite.cz" + path
            with self.assertRaises(ValueError):
                dict(rig.checks(cat, self.env))["Studio URL"]()

    def test_model_link_check_includes_terms_and_metrics(self):
        for target in ("term", "metric"):
            cat = catalog()
            item = cat.terms()[0] if target == "term" else cat.listing("metrics")[0]
            item["extension"]["ttrUrl"] = "https://studio.hartland.collite.cz/m/hartland/s/db"
            with self.assertRaises(ValueError):
                dict(rig.checks(cat, self.env))["Studio URL"]()

    def test_cn_terms_must_not_advertise_a_studio_renderer(self):
        cat = catalog()
        term = cat.terms()[0]
        term["extension"] = {"ttrQname": "cn.kind.Product"}
        check = dict(rig.checks(cat, self.env))["Studio URL"]
        self.assertTrue(check())
        term["extension"]["ttrUrl"] = "https://studio.hartland.collite.cz/m/hartland/s/cnc"
        with self.assertRaises(ValueError):
            check()

    def test_native_hyperlink_missing_malformed_or_wrong_target_is_rejected(self):
        for value in (None, "https://studio.hartland.collite.cz/m/hartland/s/db",
                      {"url": "https://foreign.example", "displayText": "Open model"},
                      {"url": "https://studio.hartland.collite.cz/m/hartland/s/db", "displayText": ""}):
            cat = catalog()
            cat.store_sales()["extension"]["ttrStudioLink"] = value
            with self.assertRaises(ValueError):
                dict(rig.checks(cat, self.env))["Studio URL"]()

    def test_native_hyperlink_registry_type_is_required(self):
        cat = catalog()
        original = cat.get
        cat.get = lambda path: {"customProperties": [{"name": "ttrStudioLink", "propertyType": {"id": "string-type"}}]} if "?fields=customProperties" in path else original(path)
        with self.assertRaises(ValueError):
            dict(rig.checks(cat, self.env))["Studio URL"]()

    def test_cn_terms_must_not_have_native_studio_links(self):
        cat = catalog()
        cat.terms()[0]["extension"] = {"ttrQname": "cn.kind.Product", "ttrStudioLink": {"url": "https://studio.hartland.collite.cz/m/hartland/s/cnc", "displayText": "Unsupported"}}
        with self.assertRaises(ValueError):
            dict(rig.checks(cat, self.env))["Studio URL"]()

    def test_labels_match_the_exact_presenter_steps(self):
        for label in ("Old", "Open database model in Studio"):
            cat = catalog()
            cat.terms()[0]["extension"]["ttrStudioLink"]["displayText"] = label
            with self.assertRaises(ValueError):
                dict(rig.checks(cat, self.env))["Studio URL"]()

    def test_original_url_registry_remains_string_on_all_link_entity_types(self):
        for kind in ("table", "glossaryTerm", "metric"):
            cat = catalog()
            original = cat.get

            def get(path):
                result = original(path)
                if path == f"metadata/types/name/{kind}?fields=customProperties":
                    result["customProperties"][1]["propertyType"]["id"] = "native-hyperlink-type"
                return result

            cat.get = get
            with self.assertRaises(ValueError):
                dict(rig.checks(cat, self.env))["Studio URL"]()

    def test_foreign_glossary_links_are_outside_hartland_acceptance(self):
        cat = catalog()
        foreign = {"glossary": {"name": "foreign Entities"},
                   "extension": {"ttrQname": "er.entity.foreign",
                                 "ttrUrl": "https://studio.example/viewer?qname=old"}}
        terms = cat.terms() + [foreign]
        cat.terms = lambda: terms
        self.assertTrue(dict(rig.checks(cat, self.env))["Studio URL"]())

    def test_deprecated_hartland_terms_have_neither_link(self):
        for glossary in ("hartland Entities", "hartland Concepts"):
            for status in ("entityStatus", "status"):
                for key in ("ttrUrl", "ttrStudioLink"):
                    cat = catalog()
                    term = cat.terms()[0]
                    term["glossary"]["name"] = glossary
                    term[status] = "Deprecated"
                    term["extension"] = {"ttrQname": "er.entity.retired", key: "stale"}
                    check = dict(rig.checks(cat, self.env))["Studio URL"]
                    with self.assertRaises(ValueError):
                        check()
                    del term["extension"][key]
                    self.assertTrue(check())

    def test_noop_requires_two_successful_nonoverlapping_jobs_same_snapshot(self):
        pair = jobs()
        output = [json.dumps({"items": pair}), pod_response("one"), json.dumps({**ZERO, "created": 7}), pod_response("two"), json.dumps(ZERO)]
        commands = []

        def execute(args, **kwargs):
            commands.append(args)
            return output.pop(0)

        self.assertIn("zero", rig.check_noop("hartland", execute))
        self.assertTrue(all(cmd[:3] == ["kubectl", "--context", "hartland"] for cmd in commands))
        log_commands = [c for c in commands if "logs" in c]
        self.assertEqual([c[-3:] for c in log_commands], [["pod/one", "-c", "project"], ["pod/two", "-c", "project"]])
        for mutate in (
            lambda p: p.pop(),
            lambda p: p[-1]["status"].update(succeeded=0),
            lambda p: p[-1]["status"].update(startTime="2026-10-25T01:00:00Z"),
        ):
            pair = jobs()
            mutate(pair)
            with self.assertRaises(ValueError):
                rig.check_noop("hartland", lambda *a, pair=pair, **k: json.dumps({"items": pair}))

    def test_updated_counter_or_changed_source_is_not_noop(self):
        for latest in ({**ZERO, "updated": 1}, {**ZERO, "snapshot": "fixture-2"}):
            output = iter([json.dumps({"items": jobs()}), pod_response("one"), json.dumps(ZERO), pod_response("two"), json.dumps(latest)])
            with self.assertRaises(ValueError):
                rig.check_noop("hartland", lambda *a, output=output, **k: next(output))

    def test_noop_rejects_cached_runs_and_legacy_connector(self):
        for first, second, message in (
            ({**ZERO, "not_modified": True}, ZERO, "first Job did not sync"),
            (ZERO, {**ZERO, "not_modified": True}, "second Job did not sync"),
            (ZERO, {k: v for k, v in ZERO.items() if k != "not_modified"}, "connector >= 0.1.2"),
        ):
            output = iter([json.dumps({"items": jobs()}), pod_response("one"), json.dumps(first),
                           pod_response("two"), json.dumps(second)])
            with self.assertRaisesRegex(ValueError, message):
                rig.check_noop("hartland", lambda *a, **k: next(output))

    def test_deprecated_objects_do_not_satisfy_default_thresholds(self):
        for check_name, count, mark in (
            ("Entities glossary", 40, lambda x: x.update(status="Deprecated")),
            ("Entities glossary", 40, lambda x: x.update(entityStatus="Deprecated")),
            ("metrics", 6, lambda x: x.update(tags=[{"tagFQN": "Tatrman.Deprecated"}])),
        ):
            from copy import deepcopy
            cat = catalog()
            original = cat.terms()[0] if count == 40 else cat.listing()[0]
            items = [deepcopy(original) for _ in range(count)]
            if count == 40:
                cat.terms = lambda: items
            else:
                cat.listing = lambda *args: items
            self.assertTrue(dict(rig.checks(cat, {}))[check_name]())
            mark(items[-1])
            with self.assertRaises(ValueError):
                dict(rig.checks(cat, {}))[check_name]()

    def test_pagination_retains_later_pages_and_rejects_cursor_cycles(self):
        cat = rig.Catalog("https://catalog.example", "secret")
        paths = []

        def page(path):
            paths.append(path)
            return (
                {"data": [2], "paging": {}}
                if "after=" in path
                else {"data": [1], "paging": {"after": "cursor/+"}}
            )

        cat.get = page
        self.assertEqual(cat.listing("tables", "columns"), [1, 2])
        self.assertIn("after=cursor%2F%2B", paths[-1])
        cat = rig.Catalog("https://catalog.example", "secret")
        cat.get = lambda path: {"data": [], "paging": {"after": "same"}}
        with self.assertRaises(ValueError):
            cat.listing("tables", "columns")

    def test_main_counts_failures_without_printing_secrets(self):
        cat = catalog()
        original = cat.get
        cat.get = lambda path: {"version": "wrong"} if path == "system/version" else original(path)
        output = io.StringIO()
        with (
            patch.dict(os.environ, self.env, clear=True),
            patch.object(rig, "Catalog", return_value=cat),
            patch.object(rig, "check_noop", side_effect=ValueError("secret-token")),
            redirect_stdout(output),
        ):
            self.assertEqual(rig.main(), 2)
        self.assertIn("8/10 passed", output.getvalue())
        self.assertNotIn("secret-token", output.getvalue())

    def test_reset_targets_only_named_projections_with_model_ownership(self):
        spec = importlib.util.spec_from_file_location(
            "xm_reset", Path(__file__).with_name("reset_openmetadata.py")
        )
        reset = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"verify_openmetadata": rig}):
            spec.loader.exec_module(reset)

        class Fake:
            def listing(self, resource, fields):
                if resource == "glossaries":
                    return [
                        {"id": "ours", "name": "hartland Entities"},
                        {"id": "other", "name": "foreign Entities"},
                    ]
                return [
                    {
                        "id": "ours-metric",
                        "name": "revenue",
                        "extension": {"ttrQname": "md.measure.revenue"},
                    },
                    {"id": "seventh", "name": "x", "extension": {"ttrQname": "md.measure.x"}},
                    {
                        "id": "foreign-metric",
                        "name": "quantity",
                        "extension": {"ttrQname": "foreign.quantity"},
                    },
                ]

            def get(self, path):
                return {"isAdmin": True}

        self.assertEqual(
            reset.targets(Fake()),
            [("glossaries", "ours", "hartland Entities"), ("metrics", "ours-metric", "revenue"), ("metrics", "seventh", "x")],
        )
        output = io.StringIO()
        with (
            patch.object(sys, "argv", ["reset"]),
            patch.dict(
                os.environ, {"OM_URL": "https://openmetadata.hartland.collite.cz"}, clear=True
            ),
            patch.object(reset, "Catalog", return_value=Fake()),
            patch.object(reset, "build_opener", side_effect=AssertionError("DELETE forbidden")),
            redirect_stdout(output),
        ):
            self.assertEqual(reset.main(), 0)
        self.assertIn("would delete", output.getvalue())
        self.assertNotIn("foreign", output.getvalue())

    def test_reset_rejects_wrong_host_and_nonadmin_before_deletion(self):
        spec = importlib.util.spec_from_file_location(
            "xm_reset", Path(__file__).with_name("reset_openmetadata.py")
        )
        reset = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"verify_openmetadata": rig}):
            spec.loader.exec_module(reset)
        with (
            patch.object(sys, "argv", ["reset", "--execute"]),
            patch.dict(os.environ, {"OM_URL": "https://foreign.example"}, clear=True),
            patch.object(
                reset, "Catalog", side_effect=AssertionError("must reject before connection")
            ),
        ):
            with self.assertRaisesRegex(ValueError, "Hartland"):
                reset.main()
        with (
            patch.object(sys, "argv", ["reset", "--execute"]),
            patch.dict(
                os.environ, {"OM_URL": "https://openmetadata.hartland.collite.cz"}, clear=True
            ),
            patch.object(reset, "Catalog") as factory,
        ):
            factory.return_value.get.return_value = {"isAdmin": False}
            with self.assertRaisesRegex(ValueError, "admin JWT"):
                reset.main()
            factory.return_value.listing.assert_not_called()


if __name__ == "__main__":
    unittest.main()
