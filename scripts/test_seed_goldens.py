"""The golden cases' own specs (AU-hartland P2 · S2.2 T1): every `automation/**/tests/*.yaml` is a valid case of
contracts §7 and names only what its recipe has; the seeds are what scripts/seed-goldens.py writes.

    uv run --quiet --with pyyaml python3 -B -m unittest scripts/test_seed_goldens.py      (`just goldens-test`)
"""

from __future__ import annotations

import importlib.util
import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
AUTOMATION = ROOT / "automation"

_spec = importlib.util.spec_from_file_location("seed_goldens", ROOT / "scripts" / "seed-goldens.py")
seed_goldens = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(seed_goldens)

CASE_KEYS = {"case", "recipe", "world", "as_of", "parameters", "keys", "expected", "pinned_from"}
EXPECTED_KEYS = {"verdicts", "actions", "detail_counts"}


def strip_comments(text: str) -> str:
    """The recipe without `//` comments (none of the recipes has `//` inside a string)."""
    return re.sub(r"//[^\n]*", "", text)


def switch_routes(ttrp: Path) -> tuple[set[str], dict[str, set[str]]]:
    """The routes the recipe's switch can emit (its `else:` target included, `none` not) and each route's detail
    contexts — read from the source; `ttrp explain` agrees (automation/tests/recipes.test.mjs)."""
    body = strip_comments(ttrp.read_text())
    m = re.search(r"->\s*switch\s*\{(.*?)\n\s*\}\s*\n\s*\}", body, re.S)
    assert m, f"{ttrp}: no switch"
    routes: set[str] = set()
    details: dict[str, set[str]] = {}
    current = None
    for name, rest in re.findall(r"^\s*([a-z_]+):\s*(.*)$", m.group(1), re.M):
        if name == "mode":
            continue
        if name in ("because", "detail"):  # a continuation line of the route above
            rest = f"{name}: {rest}"
        elif name == "else":
            target = rest.split()[0]
            current = None if target == "none" else target
        else:
            current = name
        if current is None:
            continue
        routes.add(current)
        d = re.search(r"detail:\s*([a-z_, ]+)", rest)
        if d:
            details.setdefault(current, set()).update(x.strip() for x in d.group(1).split(",") if x.strip())
    return routes, details


def recipe_parameters(ttrp: Path) -> set[str]:
    return set(seed_goldens.recipe_parameters(ttrp))


class GoldenCases(unittest.TestCase):
    recipes = seed_goldens.recipe_files()
    cases = sorted(AUTOMATION.rglob("tests/*.yaml"))

    def test_there_are_cases(self) -> None:
        self.assertGreater(len(self.cases), 0)
        self.assertTrue(all(c.parent.parent.name in self.recipes for c in self.cases), "every case sits in a recipe's folder")

    def test_every_case_is_a_contracts_7_case(self) -> None:
        for path in self.cases:
            with self.subTest(case=str(path.relative_to(ROOT))):
                case = yaml.safe_load(path.read_text())
                self.assertIsInstance(case, dict)
                self.assertLessEqual(set(case), CASE_KEYS, "unknown keys")
                for k in ("case", "recipe", "world", "as_of", "parameters", "expected"):
                    self.assertIn(k, case)
                world_suffix = "" if case["world"] == "us" else f".{case['world']}"
                self.assertEqual(f"{case['case']}{world_suffix}.yaml", path.name, "case id = file name")
                self.assertEqual(case["recipe"], path.parent.parent.name, "the recipe is the folder's")
                self.assertIn(case["world"], {"us", "cz"})
                self.assertRegex(case["as_of"], r"^\d{4}-\d{2}-\d{2}")
                self.assertIsInstance(case["parameters"], dict)
                self.assertLessEqual(set(case["expected"]), EXPECTED_KEYS)
                if "pinned_from" in case:
                    self.assertEqual(set(case["pinned_from"]), {"run", "at", "by"}, "a pinned case names run, at, by")

    def test_cases_name_only_what_the_recipe_has(self) -> None:
        for path in self.cases:
            with self.subTest(case=str(path.relative_to(ROOT))):
                case = yaml.safe_load(path.read_text())
                ttrp = self.recipes[case["recipe"]]
                routes, details = switch_routes(ttrp)
                self.assertEqual(set(case["parameters"]), recipe_parameters(ttrp), "the parameters are the recipe's")
                keys = case.get("keys")
                as_key = lambda k: tuple(k) if isinstance(k, list) else k  # noqa: E731
                for v in case["expected"].get("verdicts", []):
                    self.assertIn(v["route"], routes, f"route {v['route']}")
                    if keys is not None:
                        self.assertIn(as_key(v["key"]), {as_key(k) for k in keys}, f"verdict key {v['key']} among the keys")
                key_text = lambda k: ":".join(map(str, k)) if isinstance(k, list) else str(k)  # noqa: E731
                for key, counts in (case["expected"].get("detail_counts") or {}).items():
                    key_routes = {v["route"] for v in case["expected"]["verdicts"] if key_text(v["key"]) == str(key)}
                    allowed = set().union(*(details.get(r, set()) for r in key_routes))
                    self.assertLessEqual(set(counts), allowed, f"detail contexts of {key} (routes {sorted(key_routes)})")

    def test_the_seeds_are_what_seed_goldens_writes(self) -> None:
        for world in ("us", "cz"):
            want = seed_goldens.seeds(world) if (seed_goldens.EXPECTED / world).exists() else {}
            committed = {p for p in self.cases if (p.name.endswith(f".{world}.yaml") if world != "us" else p.name.count(".") == 1)
                         and "pinned_from" not in yaml.safe_load(p.read_text())}
            if world == "cz" and not committed:
                continue  # the cz seeds come with the CZ twins (P3 · S3.3 T5)
            with self.subTest(world=world):
                self.assertEqual({str(p.relative_to(ROOT)) for p in committed}, {str(p.relative_to(ROOT)) for p in want})
                for p in committed:
                    self.assertEqual(p.read_text(), want[p], f"{p.relative_to(ROOT)} is stale: uv run scripts/seed-goldens.py")


if __name__ == "__main__":
    unittest.main()
