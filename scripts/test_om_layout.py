"""Offline LD contract specs. The fake models server defaults, ids and unrelated content."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import om_layout as om


class FakeCatalog:
    def __init__(self):
        self.writes = []
        self.values = {
            'system/version': {'version': '2.0.6'},
            'users/loggedInUser?fields=personas,defaultPersona': {
                'id': 'admin-id', 'isAdmin': True, 'personas': [],
            },
        }

    def get(self, path, missing=False):
        return copy.deepcopy(self.values.get(path))

    def write(self, method, path, body=None):
        self.writes.append((method, path, copy.deepcopy(body)))
        self.values[path] = copy.deepcopy(body)


class FrameTests(unittest.TestCase):
    def test_unknown_address_refused_before_credentials_or_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            pack = Path(tmp)
            (pack / 'targets.json').write_text(json.dumps({
                'bp-dsk': {'address': 'https://elsewhere.example', 'enabled': True}}))
            with self.assertRaisesRegex(om.LayoutError, 'outside allow-list'):
                om.Catalog('bp-dsk', {}, pack)

    def test_disabled_and_unknown_targets_refused(self):
        for target in ('hartland', 'another-catalog'):
            with self.subTest(target=target), self.assertRaises(om.LayoutError):
                om.Catalog(target, {})

    def test_non_admin_refused_before_writes(self):
        catalog = FakeCatalog()
        catalog.values['users/loggedInUser?fields=personas,defaultPersona']['isAdmin'] = False
        with self.assertRaisesRegex(om.LayoutError, 'admin'):
            om.Layout(catalog)
        self.assertEqual([], catalog.writes)

    def test_wrong_version_refused(self):
        catalog = FakeCatalog()
        catalog.values['system/version']['version'] = '2.0.5'
        with self.assertRaisesRegex(om.LayoutError, '2.0.6'):
            om.Layout(catalog)

    def test_environment_token_and_file_both_supported(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'credential'
            p.write_text('from-file\n')
            self.assertEqual('from-file', om.credentials({'OM_TOKEN_FILE': str(p)}))
            self.assertEqual('from-env', om.credentials({'OM_TOKEN': 'from-env', 'OM_TOKEN_FILE': str(p)}))

    def test_missing_credentials_do_not_echo_values(self):
        with self.assertRaisesRegex(om.LayoutError, '^cannot read OM_TOKEN_FILE$'):
            om.credentials({'OM_TOKEN_FILE': '/nonexistent/private-secret'})
        with self.assertRaises(om.LayoutError):
            om.credentials({})

    def test_plan_is_default_and_writes_nothing(self):
        fake = FakeCatalog()
        operation = om.Operation('test', 'PUT', 'test', {'value': 1}, None, {'value': 1})
        output = []
        layout = om.Layout(fake, output=output.append)
        with patch.object(layout, 'operations', return_value=[operation]):
            self.assertEqual(0, layout.run())
        self.assertEqual(['create test'], output)
        self.assertEqual([], fake.writes)

    def test_after_apply_second_plan_only_unchanged(self):
        fake = FakeCatalog()
        layout = om.Layout(fake, output=lambda _: None)
        def operations():
            return [om.Operation('test', 'PUT', 'test', {'value': 1},
                                 fake.get('test'), {'value': 1})]
        with patch.object(layout, 'operations', side_effect=operations):
            layout.run('apply')
            output = []
            layout.output = output.append
            layout.run('plan')
        self.assertEqual(['unchanged test'], output)
        self.assertEqual(1, len(fake.writes))

    def test_relation_merge_preserves_unowned_bytes_and_order(self):
        system = [{'name': 'relatedTo', 'isSystemDefined': True, 'unknown': {'a': [3, 1]}},
                  {'name': 'broader', 'isSystemDefined': True, 'color': '#012345'}]
        third_party = {'name': 'other', 'color': '#abcdef'}
        current = {'relationTypes': system + [{'name': 'involves'}] + [third_party], 'other': 7}
        before = json.dumps(current)
        desired = [{'name': 'involves', 'inverseRelation': 'involvedIn'},
                   {'name': 'involvedIn', 'inverseRelation': 'involves'}]
        merged = om.merge_relations(current, desired)
        self.assertEqual(json.dumps(system), json.dumps(merged['relationTypes'][:2]))
        self.assertEqual(third_party, merged['relationTypes'][3])
        self.assertEqual(before, json.dumps(current))
        self.assertEqual(merged, om.merge_relations(merged, desired))
        self.assertEqual(1, sum(t['name'] == 'involves' for t in merged['relationTypes']))

    def test_system_collision_is_refused(self):
        with self.assertRaisesRegex(om.LayoutError, 'system relation'):
            om.merge_relations({'relationTypes': [{'name': 'involves', 'isSystemDefined': True}]},
                               [{'name': 'involves'}])

    def test_remove_without_execute_writes_nothing(self):
        fake = FakeCatalog()
        om.Layout(fake, output=lambda _: None).run('remove')
        self.assertEqual([], fake.writes)

    def test_execute_is_rejected_for_other_verbs(self):
        with self.assertRaisesRegex(om.LayoutError, 'only for remove'):
            om.main(['apply', '--target', 'bp-dsk', '--execute'], {})


if __name__ == '__main__':
    unittest.main()
