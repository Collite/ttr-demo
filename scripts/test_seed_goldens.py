"""The golden cases' own specs (AU-hartland P2 · S2.2 T1): every `automation/**/tests/*.yaml` is a valid case of
contracts §7 and names only what its recipe has; the seeds are what scripts/seed-goldens.py writes.

    uv run --quiet --with pyyaml python3 -B -m unittest scripts/test_seed_goldens.py      (`just goldens-test`)
"""

from __future__ import annotations

import importlib.util
import contextlib
import io
import json
import re
import sqlite3
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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
    cases = sorted(p for p in AUTOMATION.rglob("tests/*.yaml") if not any(part.endswith(".bundle") for part in p.parts))

    def test_there_are_cases(self) -> None:
        self.assertGreater(len(self.cases), 0)
        self.assertTrue(all(c.parent.parent.name in self.recipes for c in self.cases), "every case sits in a recipe's folder")

    def test_both_worlds_have_explicit_unpinned_synthetic_ops_cases(self) -> None:
        for world in ('us', 'cz'):
            for recipe in ('no_run_since', 'obligation_due_passed'):
                suffix = '' if world == 'us' else '.cz'
                for route in ('late', 'none'):
                    source = AUTOMATION / 'ops' / recipe / 'tests' / f'{route}{suffix}.yaml'
                    text = source.read_text()
                    case = yaml.safe_load(text)
                    self.assertIn('SYNTHETIC ops authoring fixture', text)
                    self.assertNotIn('pinned_from', case)
                    self.assertEqual(case['world'], world)
                    self.assertTrue(all(k.startswith(f'stub-{world}-') for k in case['keys']))
                    self.assertEqual(bool(case['expected']['verdicts']), route == 'late')

    def test_inbound_none_keeps_explicit_keys_without_verdict_rows(self) -> None:
        case = yaml.safe_load((AUTOMATION / 'monitor_inbound/tests/none.yaml').read_text())
        self.assertGreater(len(case['keys']), 0)
        self.assertLessEqual(len(case['keys']), 5)
        self.assertEqual(case['expected']['verdicts'], [])

    def test_historical_settlement_documents_do_not_fulfil_without_governed_obligations(self) -> None:
        case = yaml.safe_load((AUTOMATION / 'settle/tests/credit-note-issued.yaml').read_text())
        routes_by_key = {}
        for verdict in case['expected']['verdicts']:
            routes_by_key.setdefault(verdict['key'], set()).add(verdict['route'])
        self.assertTrue(any('money_overdue' in routes for routes in routes_by_key.values()))
        for source in (AUTOMATION / 'settle/tests').glob('*.yaml'):
            verdicts = yaml.safe_load(source.read_text())['expected']['verdicts']
            self.assertFalse({'credit_note_issued', 'money_received', 'goods_shipped'} & {v['route'] for v in verdicts})

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
                    for field in ("run", "at", "by"):
                        self.assertIsInstance(case["pinned_from"][field], str)
                        self.assertTrue(case["pinned_from"][field].strip(), f"pinned_from.{field} is required")

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
            with self.subTest(world=world):
                self.assertEqual({str(p.relative_to(ROOT)) for p in committed}, {str(p.relative_to(ROOT)) for p in want})
                for p in committed:
                    self.assertEqual(p.read_text(), want[p], f"{p.relative_to(ROOT)} is stale: uv run scripts/seed-goldens.py")


class PinnedSeedPreservation(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for folder in ('automation', 'data/automation/expected', 'data/automation/recon', 'authoring-stubs'):
            shutil.copytree(ROOT / folder, self.root / folder)
        for name, value in {
            'ROOT': self.root, 'AUTOMATION': self.root / 'automation',
            'EXPECTED': self.root / 'data/automation/expected', 'RECON': self.root / 'data/automation/recon',
        }.items():
            mock = patch.object(seed_goldens, name, value)
            mock.start()
            self.addCleanup(mock.stop)

    def run_cli(self, *args: str) -> tuple[int, str]:
        with patch('sys.argv', ['seed-goldens.py', *args]), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as err:
            status = seed_goldens.main()
        return status, err.getvalue()

    def pin(self, world: str) -> tuple[Path, str]:
        suffix = '' if world == 'us' else '.cz'
        path = self.root / f'automation/monitor_inbound/tests/none{suffix}.yaml'
        case = yaml.safe_load(path.read_text())
        case['pinned_from'] = {'run': 'observed-run', 'at': '2026-10-24T18:00:00Z', 'by': 'bora'}
        text = '# Observed silent keys; preserve this evidence exactly.\n' + yaml.safe_dump(case, sort_keys=False)
        path.write_text(text)
        return path, text

    def test_generation_and_check_preserve_pinned_cases_in_both_worlds(self) -> None:
        for world in ('us', 'cz'):
            with self.subTest(world=world):
                path, text = self.pin(world)
                self.assertEqual(self.run_cli('--world', world)[0], 0)
                self.assertEqual(path.read_text(), text)
                self.assertEqual(self.run_cli('--world', world, '--check')[0], 0)
                self.assertNotIn(path, seed_goldens.seeds(world))

    def test_stale_unpinned_case_still_fails_read_only_check(self) -> None:
        pinned, text = self.pin('us')
        stale = self.root / 'automation/monitor_inbound/tests/complete.yaml'
        stale.write_text(stale.read_text() + '# stale\n')
        before = stale.read_bytes()
        status, error = self.run_cli('--check')
        self.assertEqual(status, 3)
        self.assertIn('complete.yaml', error)
        self.assertEqual(stale.read_bytes(), before)
        self.assertEqual(pinned.read_text(), text)

    def test_invalid_pin_or_identity_refuses_before_any_seed_is_written(self) -> None:
        pinned, _ = self.pin('us')
        original = yaml.safe_load(pinned.read_text())
        for change in ({'pinned_from': None}, {'pinned_from': {'run': '', 'at': 'now', 'by': 'bora'}},
                       {'world': 'cz'}, {'recipe': 'settle'}, {'case': 'wrong'}):
            with self.subTest(change=change):
                pinned.write_text(yaml.safe_dump(original | change))
                other = self.root / 'automation/decide_return/tests/reject.yaml'
                other.write_text('case: untouched\n')
                before = {p: p.read_bytes() for p in self.root.rglob('*.yaml')}
                status, error = self.run_cli()
                self.assertEqual(status, 2)
                self.assertIn(str(pinned.relative_to(self.root)), error)
                self.assertEqual({p: p.read_bytes() for p in self.root.rglob('*.yaml')}, before)


class SettleObligationGate(unittest.TestCase):
    """Execute the emitted leaf reads and combine SQL against isolated in-memory tables."""

    bundle = AUTOMATION / 'settle/settle.bundle'

    def setUp(self) -> None:
        self.db = sqlite3.connect(':memory:')
        self.addCleanup(self.db.close)
        schemas = {
            'return_request_line': 'line_id request_number line_no item quantity unit_price reason requested_resolution requested_variant state way customer',
            'return_request': 'request_number customer order_number channel requested_date state',
            'credit_note': 'credit_note_id line_id customer issued_date amount status',
            'refund_payment': 'payment_id credit_note_id paid_date amount',
            'replacement_shipment': 'shipment_id line_id shipped_date',
            'obligation': 'id recipe run entity key kind due state fulfilled_by fulfilled_at created_at',
            'date_dim': 'cal_date working_day',
        }
        for name, columns in schemas.items():
            self.db.execute(f'CREATE TABLE "{name}" ({", ".join(columns.split())})')
        self.db.execute("INSERT INTO return_request_line (line_id, request_number, state, way) VALUES (1, 10, 'settling', 'refund_no_return')")
        self.db.execute('INSERT INTO return_request (request_number, customer) VALUES (10, 20)')
        self.db.execute("INSERT INTO credit_note (credit_note_id, line_id, issued_date) VALUES (30, 1, '2026-11-19')")
        self.db.execute("INSERT INTO refund_payment (payment_id, credit_note_id, paid_date) VALUES (40, 30, '2026-11-19')")
        self.db.execute("INSERT INTO replacement_shipment (shipment_id, line_id, shipped_date) VALUES (50, 1, '2026-11-19')")
        for part in (self.bundle / 'parts').glob('*.sql'):
            sql = part.read_text().replace(':as_of', "'2026-11-19'")
            self.db.execute(f'CREATE TEMP VIEW "{part.stem}" AS {sql}')

    def obligation(self, kind, state='open', entity='er.entity.return_request_line', key='{"line_id":1}'):
        self.db.execute('INSERT INTO obligation (id, entity, key, kind, state) VALUES (?, ?, ?, ?, ?)',
                        (str(self.db.total_changes), entity, key, kind, state))

    def routes(self):
        manifest = json.loads((self.bundle / 'manifest.json').read_text())
        outputs = next(i for i in manifest['islands'] if i['name'] == 'settlement')['outputs']
        result = {}
        for output in outputs:
            if '.' not in output['port']:
                sql = (self.bundle / output['file']).read_text()
                result[output['port']] = self.db.execute(sql, {'as_of': '2026-11-19'}).fetchall()
        return result

    def test_historical_documents_do_not_fulfil(self):
        routes = self.routes()
        for route in ('credit_note_issued', 'money_received', 'goods_shipped'):
            self.assertEqual(routes[route], [])
        self.assertEqual(len(routes['closed']), 1)

    def test_each_kind_matches_only_its_route_in_every_active_state(self):
        mapping = {'credit_note': 'credit_note_issued', 'payment': 'money_received', 'replacement': 'goods_shipped'}
        for kind, expected in mapping.items():
            for state in ('open', 'overdue', 'reopened'):
                with self.subTest(kind=kind, state=state):
                    self.db.execute('DELETE FROM obligation')
                    self.obligation(kind, state)
                    routes = self.routes()
                    for route in mapping.values():
                        self.assertEqual(len(routes[route]), int(route == expected))

    def test_closed_wrong_kind_and_noncanonical_identities_do_not_fulfil(self):
        for kind in ('credit_note', 'payment', 'replacement'):
            for state in ('fulfilled', 'cancelled'):
                self.obligation(kind, state)
            self.obligation(kind, entity='return_request_line')
            self.obligation(kind, key='1')
            self.obligation(kind, key='{"line_id":2}')
        self.obligation('inbound')
        for route in ('credit_note_issued', 'money_received', 'goods_shipped'):
            self.assertEqual(self.routes()[route], [])

    def test_multiple_kinds_and_duplicate_obligations_do_not_multiply_routes(self):
        for kind in ('credit_note', 'payment', 'replacement'):
            self.obligation(kind)
            self.obligation(kind, 'overdue')
        routes = self.routes()
        for route in ('credit_note_issued', 'money_received', 'goods_shipped', 'closed'):
            self.assertEqual(len(routes[route]), 1)

    def test_obligation_without_document_does_not_fulfil(self):
        for kind in ('credit_note', 'payment', 'replacement'):
            self.obligation(kind)
        for table in ('credit_note', 'refund_payment', 'replacement_shipment'):
            self.db.execute(f'DELETE FROM {table}')
        for route in ('credit_note_issued', 'money_received', 'goods_shipped'):
            self.assertEqual(self.routes()[route], [])


if __name__ == "__main__":
    unittest.main()
