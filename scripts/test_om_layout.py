"""Offline LD contract specs. The fake models server defaults, ids and unrelated content."""
import copy
import json
import sys
import shutil
import weakref
import tempfile
import unittest
from urllib.parse import urlsplit, parse_qs, unquote
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import om_layout as om


class FakeCatalog:
    def __init__(self):
        self.writes = []
        self.temp = tempfile.mkdtemp()
        self.pack = Path(self.temp) / "pack"
        shutil.copytree(om.PACK, self.pack, ignore=shutil.ignore_patterns("build"))
        self.values = {
            'system/version': {'version': '2.0.6'},
            'users/loggedInUser?fields=personas,defaultPersona': {
                'id': 'admin-id', 'isAdmin': True, 'personas': [],
            },
            'system/settings/customUiThemePreference': {
                'config_type': 'customUiThemePreference',
                'config_value': {'customTheme': {'errorColor': '#ab1234'}, 'customLogoConfig': {}}},
            'system/settings/glossaryTermRelationSettings': {
                'config_type': 'glossaryTermRelationSettings',
                'config_value': {'relationTypes': [
                    {'name': 'system' + str(i), 'isSystemDefined': True, 'opaque': [i, {'x': True}]}
                    for i in range(10)] + [{'name': 'unrelated', 'isSymmetric': True}]}},
        }

        self.base = "https://openmetadata.192-168-1-38.nip.io/api/v1/"
        weakref.finalize(self, shutil.rmtree, self.temp, True)
        self.seed_content()

    def seed_content(self):
        specs = om.read_json(om.PACK / 'content.json')
        for i, spec in enumerate(specs['terms']):
            name = spec['qname']
            item = {'id': 'term-' + str(i), 'name': name, 'fullyQualifiedName': 'demo ' + spec['glossary'] + '.' + name,
                    'glossary': {'name': 'demo ' + spec['glossary']},
                    'extension': {'ttrQname': name, 'foreign': 'keep'}, 'entityStatus': 'Approved',
                    'relatedTerms': [], 'reviewers': [], 'tags': []}
            self.values['glossaryTerms/name/' + item['fullyQualifiedName']] = item
        customer = self.values['glossaryTerms/name/demo Concepts.cn.role.Customer']
        sale = self.values['glossaryTerms/name/demo Concepts.cn.event.Sale']
        customer['relatedTerms'] = [{'term': {'id': sale['id'], 'type': 'glossaryTerm'}, 'relationType': 'relatedTo'}]
        sale['relatedTerms'] = [{'term': {'id': customer['id'], 'type': 'glossaryTerm'}, 'relationType': 'relatedTo'}]
        spec = specs['table']
        self.values['tables/name/' + spec['fqn']] = {'id': 'table', 'name': 'customer',
            'fullyQualifiedName': spec['fqn'], 'extension': {'ttrQname': spec['qname']}}
        for name in ['revenue', 'quantity', 'orderCount', 'lineCount', 'returnAmount']:
            self.values['metrics/name/' + name] = {'id': 'metric-' + name, 'name': name,
                'fullyQualifiedName': name, 'extension': {'ttrQname': 'md.measure.' + name}, 'tags': []}

    def get(self, path, missing=False):
        parsed = urlsplit(path)
        resource = unquote(parsed.path)
        if resource in self.values:
            return copy.deepcopy(self.values[resource])
        if path in self.values:
            return copy.deepcopy(self.values[path])
        if resource in ('glossaryTerms', 'metrics', 'tasks', 'announcements'):
            items = [copy.deepcopy(v) for k, v in self.values.items() if k.startswith(resource + '/name/')]
            query = parse_qs(parsed.query)
            if resource == 'tasks' and 'aboutEntity' in query:
                items = [v for v in items if v['about']['fullyQualifiedName'] == query['aboutEntity'][0]]
            if resource == 'announcements' and 'entityLink' in query:
                items = [v for v in items if v['entityLink'] == query['entityLink'][0]]
            return {'data': items, 'paging': {}}
        if '/' in resource and '/name/' not in resource:
            identity = resource.rsplit('/', 1)[1]
            for value in self.values.values():
                if value and value.get('id') == identity:
                    return copy.deepcopy(value)
        return None

    def write(self, method, path, body=None):
        self.writes.append((method, path, copy.deepcopy(body)))
        resource = path.split('?')[0]
        if resource == 'system/settings':
            self.values[resource + '/' + body['config_type']] = copy.deepcopy(body)
        elif method == 'POST' and resource == 'tasks':
            number = 'TASK-' + str(1 + sum(k.startswith('tasks/name/') for k in self.values)).zfill(5)
            customer = next(v for v in self.values.values() if v and v.get('extension', {}).get('ttrQname') == 'cn.role.Customer')
            item = dict(copy.deepcopy(body), id=number, name=number, taskId=number, status='Open',
                about={'id': customer['id'], 'fullyQualifiedName': customer['fullyQualifiedName']},
                assignees=[{'id': self.get('users/name/petr.novak')['id'], 'type': 'user', 'name': 'petr.novak'}], comments=[],
                taskFormSchemaId=self.get('taskFormSchemas/name/ttrSuggestChange')['id'],
                workflowStageId='review', availableTransitions=[{'id': 'approve', 'label': 'Approve'}])
            self.values['tasks/name/' + number] = item
            return copy.deepcopy(item)
        elif method == 'POST' and resource.startswith('tasks/'):
            item = next(v for v in self.values.values() if v and v.get('id') == resource.split('/')[1])
            if resource.endswith('/resolve'):
                transition = body['transitionId']
                if transition == 'approve':
                    item.update(status='InProgress', workflowStageId='publication', availableTransitions=[{'id': 'publish', 'label': 'Published with the model'}])
                elif transition == 'publish':
                    item.update(status='Completed', workflowStageId='published', availableTransitions=[])
                else:
                    raise AssertionError('unexpected transition')
                if body.get('payload', {}).get('assignees'):
                    item['assignees'] = copy.deepcopy(body['payload']['assignees'])
                if body.get('comment') and not (transition == 'publish' and getattr(self, 'omit_terminal_comment', False)):
                    item['comments'].append({'message': body['comment']})
            else:
                item['comments'].append({'message': body['message']})
            return copy.deepcopy(item)
        elif method in ('POST', 'PUT') and resource in ('personas', 'docStore', 'users', 'teams', 'domains', 'governance/workflowDefinitions', 'taskFormSchemas', 'announcements'):
            key = body.get('fullyQualifiedName', body['name'])
            existing = self.values.get(resource + '/name/' + key, {})
            stored = {k: v for k, v in body.items() if k not in ('password', 'confirmPassword', 'createPasswordType')}
            item = dict(copy.deepcopy(stored), id=existing.get('id', resource.replace('/', '-') + '-id-' + key), version=0.1, updatedAt=123)
            self.values[resource + '/name/' + key] = item
            return copy.deepcopy(item)
        elif method in ('PATCH', 'DELETE'):
            identity = resource.rsplit('/', 1)[1]
            key = next(k for k, value in self.values.items() if value and value.get('id') == identity)
            if method == 'DELETE':
                del self.values[key]
            else:
                for op in body:
                    field = op['path'][1:]
                    if op['op'] == 'remove':
                        self.values[key].pop(field, None)
                    else:
                        self.values[key][field] = copy.deepcopy(op['value'])
                return copy.deepcopy(self.values[key])
        else:
            self.values[resource] = copy.deepcopy(body)


def make_layout(fake, **kwargs):
    return om.Layout(fake, pack=fake.pack, **kwargs)


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
            make_layout(catalog)
        self.assertEqual([], catalog.writes)

    def test_wrong_version_refused(self):
        catalog = FakeCatalog()
        catalog.values['system/version']['version'] = '2.0.5'
        with self.assertRaisesRegex(om.LayoutError, '2.0.6'):
            make_layout(catalog)

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
        layout = make_layout(fake, output=output.append)
        with patch.object(layout, 'operations', return_value=[operation]):
            self.assertEqual(0, layout.run())
        self.assertEqual(['create test'], [x for x in output if not x.startswith('skip ')])
        self.assertEqual([], fake.writes)

    def test_after_apply_second_plan_only_unchanged(self):
        fake = FakeCatalog()
        layout = make_layout(fake, output=lambda _: None)
        def operations():
            return [om.Operation('test', 'PUT', 'test', {'value': 1},
                                 fake.get('test'), {'value': 1})]
        with patch.object(layout, 'operations', side_effect=operations):
            layout.run('apply')
            output = []
            layout.output = output.append
            layout.run('plan')
        self.assertEqual(['unchanged test'], [x for x in output if not x.startswith('skip ')])
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
        make_layout(fake, output=lambda _: None).run('remove')
        self.assertEqual([], fake.writes)

    def test_execute_is_rejected_for_other_verbs(self):
        with self.assertRaisesRegex(om.LayoutError, 'only for remove'):
            om.main(['apply', '--target', 'bp-dsk', '--execute'], {})


class PackTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeCatalog()
        self.output = []
        self.layout = make_layout(self.fake, output=self.output.append)

    def test_whole_plan_is_read_only_and_lists_real_objects(self):
        self.assertEqual(0, self.layout.run('plan'))
        self.assertEqual([], self.fake.writes)
        self.assertTrue(any(line.startswith('create persona ') for line in self.output))
        self.assertTrue(any(line.startswith('create document ') for line in self.output))

    def test_apply_twice_then_plan_is_unchanged_and_keeps_system_types_byte_identical(self):
        before = json.dumps(self.fake.values['system/settings/glossaryTermRelationSettings']['config_value']['relationTypes'])
        self.assertEqual(0, self.layout.run('apply'))
        first_writes = len(self.fake.writes)
        self.output.clear()
        self.assertEqual(0, self.layout.run('apply'))
        self.assertTrue(all(w[1].startswith("announcements/") for w in self.fake.writes[first_writes:]))
        self.assertTrue(all(line.startswith('unchanged ') or 'renew end time' in line or 'OM_DEMO_PASSWORD absent' in line for line in self.output), self.output)
        self.output.clear()
        self.layout.run('plan')
        self.assertTrue(all(line.startswith('unchanged ') or 'renew end time' in line or 'OM_DEMO_PASSWORD absent' in line for line in self.output), self.output)
        after = self.fake.values['system/settings/glossaryTermRelationSettings']['config_value']['relationTypes']
        self.assertEqual(before, json.dumps(after[:11]))
        self.assertEqual(8, len(after[11:]))

    def test_remove_preview_with_every_object_present_has_no_writes(self):
        self.layout.run('apply')
        before = copy.deepcopy(self.fake.values)
        self.fake.writes.clear()
        self.output.clear()
        self.layout.run('remove')
        self.assertEqual([], self.fake.writes)
        self.assertEqual(before, self.fake.values)
        self.assertTrue(any(line.startswith('would delete document ') for line in self.output))
        self.assertTrue(any(line.startswith('would delete persona ') for line in self.output))
        self.assertTrue(any('relation types' in line for line in self.output))

    def test_remove_execute_only_deletes_owned_objects_and_preserves_unowned_settings(self):
        self.layout.run('apply')
        self.fake.values['personas/name/someone-else'] = {'id': 'someone-id', 'name': 'someone-else'}
        admin = self.fake.values['users/loggedInUser?fields=personas,defaultPersona']
        admin['personas'].append({'id': 'someone-id', 'type': 'persona'})
        self.layout.run('remove', execute=True)
        self.assertIn('personas/name/someone-else', self.fake.values)
        self.assertEqual([{'id': 'someone-id', 'type': 'persona'}], admin['personas'])
        self.assertNotIn('defaultPersona', admin)
        self.assertFalse(any(k.startswith('docStore/') for k in self.fake.values))
        theme = self.fake.values['system/settings/customUiThemePreference']['config_value']
        self.assertEqual('#ab1234', theme['customTheme']['errorColor'])
        self.assertEqual('', theme['customTheme']['primaryColor'])
        self.assertEqual(11, len(self.fake.values['system/settings/glossaryTermRelationSettings']['config_value']['relationTypes']))
        self.fake.writes.clear()
        self.layout.run('remove', execute=True)
        self.assertEqual([], self.fake.writes)

    def test_verify_reports_each_contract_violation_and_returns_failed_count(self):
        self.layout.run('apply')
        self.fake.values['system/settings/customUiThemePreference']['config_value']['customTheme']['hoverColor'] = '#ffffff'
        self.fake.values['personas/name/ttr-model-reader']['displayName'] = 'Wrong'
        doc = self.fake.values['docStore/name/persona.ttr-model-steward']
        doc['data']['navigation'][0]['isHidden'] = True
        doc['data']['pages'][0]['tabs'][1]['displayName'] = 'Wrong'
        self.fake.values['system/settings/glossaryTermRelationSettings']['config_value']['relationTypes'][-1].pop('inverseRelation')
        self.output.clear()
        self.fake.writes.clear()
        self.assertEqual(5, self.layout.run('verify'))
        self.assertEqual(5, sum(line.startswith('FAIL ') for line in self.output))
        self.assertEqual([], self.fake.writes)

    def test_existing_personas_are_patched_and_other_fields_survive(self):
        self.fake.values['personas/name/ttr-model-steward'] = {
            'id': 'existing-id', 'name': 'ttr-model-steward', 'displayName': 'Old',
            'description': 'Keep this', 'users': [{'id': 'someone-id'}]}
        self.layout.run('apply')
        persona = self.fake.values['personas/name/ttr-model-steward']
        self.assertEqual('existing-id', persona['id'])
        self.assertEqual('Keep this', persona['description'])
        self.assertEqual([{'id': 'someone-id'}], persona['users'])
        self.assertEqual('Model steward', persona['displayName'])


class RelationTests(unittest.TestCase):
    def test_four_reciprocal_pairs_are_associative_cross_glossary_and_not_symmetric(self):
        items = om.read_json(om.PACK / 'relation-types.json')
        by_name = {item['name']: item for item in items}
        self.assertEqual(8, len(by_name))
        for name, inverse in [('involves', 'involvedIn'), ('phaseOf', 'hasPhase'),
                              ('definedBy', 'defines'), ('grounds', 'groundedBy')]:
            self.assertEqual(inverse, by_name[name]['inverseRelation'])
            self.assertEqual(name, by_name[inverse]['inverseRelation'])
        for item in items:
            self.assertEqual('associative', item['category'])
            self.assertIs(False, item['isSymmetric'])
            self.assertIs(True, item['isCrossGlossaryAllowed'])


class PersonaTests(unittest.TestCase):
    def test_export_has_only_create_fields_and_original_ui_keys(self):
        for path in (om.PACK / 'persona-ui').glob('*.json'):
            doc = om.read_json(path)
            self.assertEqual({'name', 'fullyQualifiedName', 'entityType', 'data'}, set(doc))
            self.assertEqual(['GlossaryTerm'], [p['pageType'] for p in doc['data']['pages']])
            tabs = doc['data']['pages'][0]['tabs']
            self.assertEqual(['overview', 'glossary_terms', 'assets', 'relations_graph',
                              'activity_feed', 'custom_properties'], [t['id'] for t in tabs])
            self.assertTrue(tabs[0]['layout'][0]['children'])

    def test_membership_preserves_other_personas_and_chooses_stock(self):
        fake = FakeCatalog()
        admin = fake.values['users/loggedInUser?fields=personas,defaultPersona']
        admin['personas'] = [{'id': 'other-id', 'type': 'persona', 'name': 'other'}]
        for i, persona in enumerate(om.read_json(om.PACK / 'personas.json')):
            fake.values['personas/name/' + persona['name']] = dict(persona, id=str(i))
        operation = make_layout(fake).membership()
        self.assertEqual('other-id', operation.body[0]['value'][0]['id'])
        self.assertEqual('2', operation.body[1]['value']['id'])
        self.assertEqual(4, len(operation.body[0]['value']))
        admin['personas'] = operation.body[0]['value']
        admin['defaultPersona'] = operation.body[1]['value']
        self.assertEqual('unchanged', make_layout(fake).membership().action)


class SkinTests(unittest.TestCase):
    def test_theme_keeps_unowned_values_and_embeds_svg(self):
        current = {'customTheme': {'errorColor': '#112233', 'infoColor': '#445566',
                                  'successColor': '#778899', 'primaryColor': '#000000'},
                   'customLogoConfig': {}}
        layout = make_layout(FakeCatalog(), output=lambda _: None)
        desired = layout.theme_value(current)
        self.assertEqual('#16283F', desired['customTheme']['primaryColor'])
        self.assertEqual('#16283F', desired['customTheme']['panelBackgroundColor'])
        self.assertEqual('#F2A200', desired['customTheme']['warningColor'])
        self.assertEqual('', desired['customTheme']['selectedColor'])
        self.assertEqual('', desired['customTheme']['hoverColor'])
        for key in ('errorColor', 'infoColor', 'successColor'):
            self.assertEqual(current['customTheme'][key], desired['customTheme'][key])
        for value in desired['customLogoConfig'].values():
            self.assertTrue(value.startswith('data:image/svg+xml;base64,'))
        self.assertEqual(desired, layout.theme_value(desired))
        self.assertEqual('#000000', current['customTheme']['primaryColor'])

    def test_theme_remove_clears_only_owned_fields(self):
        layout = make_layout(FakeCatalog(), output=lambda _: None)
        original = {'customTheme': {'errorColor': '#123456'}, 'customLogoConfig': {}}
        removed = layout.theme_value(layout.theme_value(original), removing=True)
        self.assertEqual('#123456', removed['customTheme']['errorColor'])
        self.assertEqual('', removed['customTheme']['primaryColor'])
        self.assertTrue(all(value == '' for value in removed['customLogoConfig'].values()))


if __name__ == '__main__':
    unittest.main()
