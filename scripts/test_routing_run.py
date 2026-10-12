"""Specs for scripts/routing-run.py's pure half (assertions, schema check, verdicts) — no cluster.

    just routing-test      # = uv run --with pyyaml --with httpx python3 -B -m unittest scripts/test_routing_run.py
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import pathlib
import shutil
import sys
import tempfile
import textwrap
import unittest

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("routing_run", HERE / "routing-run.py")
rr = importlib.util.module_from_spec(spec)
sys.modules["routing_run"] = rr  # dataclasses resolve annotations through sys.modules
spec.loader.exec_module(rr)


class AssertionSpec(unittest.TestCase):
    CORE_MONTHS = [{"month": "1", "revenue": "832516610.01"}, {"month": "2", "revenue": "747355959.37"}]

    def test_row_set_matches_keys_and_values_across_column_names(self):
        door = [{"month": 1, "ext_sales_price": 832516610.01}, {"month": 2, "ext_sales_price": 747355959.37}]
        llm = [{"d_year": 2025, "d_moy": 2, "revenue": "747355959.37"}, {"d_year": 2025, "d_moy": 1, "revenue": 832516610.0}]
        a = {"row_set": {"keys": ["month"], "value": "revenue", "tolerance": 0.001}}
        self.assertEqual(rr.evaluate(a, door, "", self.CORE_MONTHS, "cs"), [])
        self.assertEqual(rr.evaluate(a, llm, "", self.CORE_MONTHS, "cs"), [])

    def test_row_set_catches_a_wrong_value_and_a_missing_key(self):
        a = {"row_set": {"keys": ["month"], "value": "revenue", "tolerance": 0.001}}
        wrong = [{"month": 1, "v": 832516610.01}, {"month": 2, "v": 1.0}]
        self.assertTrue(rr.evaluate(a, wrong, "", self.CORE_MONTHS, "cs"))
        missing = [{"month": 1, "v": 832516610.01}]
        self.assertTrue(rr.evaluate(a, missing, "", self.CORE_MONTHS, "cs"))

    def test_row_set_pops_unless_told_the_answer_is_pivoted(self):
        core = [{"year": "2024", "revenue": "100"}, {"year": "2025", "revenue": "90"}]
        pivoted = [{"channel": "marketplace", "y2024": 100, "y2025": 90}]
        popping = {"row_set": {"keys": [], "value": "revenue"}}
        self.assertTrue(rr.evaluate(popping, pivoted, "", core, "cs"))
        self.assertEqual(rr.evaluate({"row_set": {"keys": [], "value": "revenue", "pop": False}}, pivoted, "", core, "cs"), [])

    def test_padded_char_keys_and_date_shaped_months_match(self):
        self.assertTrue(rr.cell_matches_key("Books     ", "Books                    "))
        self.assertTrue(rr.cell_matches_key("2025-03-01T00:00:00Z", "3"))
        self.assertTrue(rr.cell_matches_key(3.0, "3"))
        self.assertFalse(rr.cell_matches_key("2025-04", "3"))

    def test_scalar_accepts_a_fraction_or_a_percentage_and_prose(self):
        core = [{"yoy": "-0.1254"}]
        a = {"scalar": {"value": "yoy", "tolerance": 0.01, "scale": [1, 100]}}
        self.assertEqual(rr.evaluate(a, [{"pct": -12.5}], "", core, "cs"), [])
        self.assertEqual(rr.evaluate(a, [{"pct": -0.1254}], "", core, "cs"), [])
        self.assertTrue(rr.evaluate(a, [{"pct": -8.4}], "", core, "cs"))
        aov = {"scalar": {"value": "aov", "tolerance": 0.002}}
        self.assertEqual(rr.evaluate(aov, [], "Průměrná hodnota objednávky byla 492 883,66 Kč.", [{"aov": "492883.66"}], "cs"), [])
        self.assertEqual(rr.evaluate(aov, [], "The average order value was $21,429.72.", [{"aov": "21429.72"}], "en"), [])

    def test_empty_counts_one_all_null_aggregate_row_as_no_rows(self):
        a = {"empty": True}
        self.assertEqual(rr.evaluate(a, [{"ext_sales_price": None}], "", None, "cs"), [])
        self.assertTrue(rr.evaluate(a, [{"ext_sales_price": 0.0}], "", None, "cs"))

    def test_text_contains_is_per_locale(self):
        a = {"text_contains": {"cs": "nemohu odpovědět", "en": "can't answer"}}
        self.assertEqual(rr.evaluate(a, [], "Na tuto otázku nemohu odpovědět.", None, "cs"), [])
        self.assertTrue(rr.evaluate(a, [], "Na tuto otázku nemohu odpovědět.", None, "en"))

    def test_first_row_and_row_count(self):
        core = [{"dc": "Brno DC", "share": "0.24"}]
        a = {"first_row": {"keys": ["dc"]}, "row_count": {"min": 1, "max": 5}}
        self.assertEqual(rr.evaluate(a, [{"warehouse": "Brno DC", "pct": 24.4}, {"warehouse": "Praha DC"}], "", core, "cs"), [])
        self.assertTrue(rr.evaluate(a, [{"warehouse": "Praha DC"}, {"warehouse": "Brno DC"}], "", core, "cs"))
        self.assertTrue(rr.evaluate({"row_count": 12}, [{"a": 1}], "", None, "cs"))

    def test_a_failed_core_fails_the_assertions_that_need_it(self):
        self.assertTrue(rr.evaluate({"scalar": {"value": "x"}}, [{"a": 1}], "", None, "cs"))


class VerdictSpec(unittest.TestCase):
    def test_xfail_never_reddens_and_an_xpass_is_flagged(self):
        self.assertEqual(rr.verdict(False, True, [], None, "ttr-server#152"), "XFAIL")
        self.assertEqual(rr.verdict(True, True, [], None, "ttr-server#152"), "XPASS")
        self.assertEqual(rr.verdict(True, True, ["row_count 1 not in [12, 12]"], None, None), "FAIL")
        self.assertEqual(rr.verdict(True, True, [], None, None), "PASS")
        self.assertEqual(rr.verdict(False, True, [], "HTTP 502", None), "ERROR")

    def test_route_classes(self):
        self.assertEqual(rr.classify("ROUTE_FAST_PATH"), "FAST")
        self.assertEqual(rr.classify("ROUTE_LLM_COMPOSE"), "LLM")
        self.assertEqual(rr.classify("ROUTE_ASK"), "ASK")
        self.assertEqual(rr.classify("ROUTE_REFUSAL"), "REFUSE")
        self.assertEqual(rr.classify(None), "NONE")

    def test_substitute_reference_date_and_world_params(self):
        sql = "WHERE d >= DATE '{reference_date}' AND name LIKE '%{term}%'"
        out = rr.substitute(sql, dt.date(2026, 10, 12), {"term": "O'Brien"})
        self.assertEqual(out, "WHERE d >= DATE '2026-10-12' AND name LIKE '%O''Brien%'")


class CorpusCheckSpec(unittest.TestCase):
    def setUp(self):
        self.root = pathlib.Path(tempfile.mkdtemp(prefix="routing-spec-"))
        (self.root / "cases").mkdir()
        (self.root / "validation").mkdir()
        (self.root / "personas.yaml").write_text("analyst: {cz: marketa, us: maya}\n")
        (self.root / "validation" / "v.yaml").write_text("core: SELECT 1 AS x\nassert:\n  scalar: {value: x}\n")

    def tearDown(self):
        shutil.rmtree(self.root)

    def write(self, name, body):
        (self.root / "cases" / f"{name}.case.yaml").write_text(textwrap.dedent(body))

    def test_the_real_corpus_is_clean(self):
        _, _, problems = rr.load_corpus(rr.DEFAULT_CORPUS)
        self.assertEqual(problems, [])

    def test_a_good_case_passes(self):
        self.write("ok", """
            id: ok
            title: t
            shape: total
            question: {cs: "Tržby", en: "Revenue"}
            expected_route: FAST
            validation: v.yaml
        """)
        self.assertEqual(rr.load_corpus(self.root)[2], [])

    def test_problems_are_named(self):
        self.write("a", """
            id: b
            title: t
            shape: total
            question: {cs: "Tržby"}
            expected_route: FASTER
            expected_reason: RATIO
            validation: missing.yaml
            persona: cfo
            wat: 1
        """)
        problems = "\n".join(rr.load_corpus(self.root)[2])
        for needle in ("filename stem", "cs AND en", "expected_route", "LLM cases only", "missing.yaml", "persona", "unknown keys"):
            self.assertIn(needle, problems)

    def test_a_resume_needs_a_session_that_asked_first(self):
        self.write("r1", """
            id: r1
            title: t
            shape: homonym
            resume: {pick: place}
            session: s
            expected_route: FAST
        """)
        self.assertIn("is a resume", "\n".join(rr.load_corpus(self.root)[2]))


if __name__ == "__main__":
    unittest.main()
