"""Frozen-content contract specs, with no catalog connection or real credentials."""
import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_om_layout import FakeCatalog, make_layout
import om_layout as om


class AccountTests(unittest.TestCase):
    def test_user_persona_references_include_names_for_server_sorting(self):
        class NamedPersonas(FakeCatalog):
            def write(self, method, path, body=None):
                if method == 'PATCH' and path.startswith('users/'):
                    for operation in body:
                        if operation['path'] == '/personas':
                            if any(not p.get('name') for p in operation['value']):
                                raise AssertionError('OM sorts persona references by name')
                return super().write(method, path, body)
        fake = NamedPersonas('hartland')
        layout = make_layout(fake, output=lambda _:None, env={})
        self.assertEqual(0, layout.run('apply'))
        # Exercise the existing-user update path as well as fresh account creation.
        fake.values['users/name/petr.novak']['personas'] = []
        self.assertEqual(0, layout.run('apply'))

    def test_plan_does_not_create_passwords_or_log_credentials(self):
        fake, output = FakeCatalog(), []
        layout = make_layout(fake, output=output.append, env={'OM_DEMO_PASSWORD': 'not-a-real-password'})
        layout.run('plan')
        self.assertEqual([], fake.writes)
        self.assertNotIn('not-a-real-password', '\n'.join(output))

    def test_created_users_have_personas_and_second_apply_keeps_passwords(self):
        fake = FakeCatalog()
        layout = make_layout(fake, output=lambda _: None, env={})
        layout.run('apply')
        jana = fake.get('users/name/jana.dvorakova')
        self.assertEqual('Jana Dvořáková', jana['displayName'])
        self.assertIn('ttr-model-reader', jana['defaultPersona']['id'])
        self.assertTrue(fake.get('users/name/tatrman-maintainer')['isBot'])
        creates = [w for w in fake.writes if w[:2] == ('POST', 'users')]
        passwords = [w[2]['password'] for w in creates if not w[2]['isBot']]
        self.assertEqual(2, len(set(passwords)))
        before = copy.deepcopy(fake.writes)
        layout.run('apply')
        self.assertEqual([w for w in before if w[1]=='users'], [w for w in fake.writes if w[1]=='users'])
        self.assertEqual(4, sum(k.startswith('domains/name/') for k in fake.values))


if __name__ == '__main__':
    unittest.main()

class FrozenContentTests(unittest.TestCase):
    def setUp(self):
        self.fake, self.output = FakeCatalog(), []
        self.layout = make_layout(self.fake, output=self.output.append, env={})

    def test_missing_neighbours_skip_fields_and_relations_without_creating_replacements(self):
        optional = ['cn.event.Sale', 'cn.event.OrderPlaced', 'cn.phase.DebtorCustomer',
                    'er.entity.customer', 'db.dbo.customer', 'md.measure.revenue', 'md.measure.quantity']
        for qname in optional:
            with self.subTest(qname=qname):
                fake, output = FakeCatalog('hartland'), []
                key = next(k for k,v in fake.values.items() if v.get('extension',{}).get('ttrQname') == qname)
                missing = fake.values.pop(key)
                layout = make_layout(fake, output=output.append, env={})
                self.assertEqual(0, layout.run('plan'))
                self.assertIn('skip ' + qname + ': not in this catalog', output)
                self.assertEqual([], fake.writes)
                self.assertEqual(0, layout.run('apply'))
                self.assertNotIn(key, fake.values)
                self.assertFalse(any(w[1].split('?')[0].endswith('/' + missing['id']) for w in fake.writes))
                self.assertFalse(any(w[0] == 'POST' and w[1] in ('glossaryTerms','tables','metrics') for w in fake.writes))
                output.clear()
                fake.writes.clear()
                self.assertEqual(0, layout.run('verify'))
                self.assertEqual(16, len(output))
                self.assertTrue(any(line.startswith('ok ') and '; skip ' + qname + ': not in this catalog' in line for line in output))
                self.assertEqual([], fake.writes)

    def test_missing_customer_and_duplicate_neighbour_are_errors(self):
        for qname in ('cn.role.Customer', 'cn.event.OrderPlaced'):
            with self.subTest(qname=qname):
                fake = FakeCatalog()
                key = next(k for k,v in fake.values.items() if v.get('extension',{}).get('ttrQname') == qname)
                if qname == 'cn.role.Customer':
                    del fake.values[key]
                else:
                    fake.values[key + '-duplicate'] = dict(fake.values[key], id='duplicate')
                with self.assertRaisesRegex(om.LayoutError, 'expected one projected term: ' + qname):
                    make_layout(fake, output=lambda _:None).objects()

    def test_reviewers_follow_all_tasks_and_other_fields_precede_them(self):
        self.assertEqual(0, self.layout.run('apply'))
        writes = self.fake.writes
        first_task = next(i for i, w in enumerate(writes) if w[:2] == ('POST', 'tasks'))
        last_task = max(i for i, w in enumerate(writes) if w[1].startswith('tasks') and not w[1].startswith('tasks/APPROVAL'))
        customer_id = self.layout.customer()['id']
        patches = [(i, w[2]) for i, w in enumerate(writes) if w[:2] == ('PATCH', 'glossaryTerms/' + customer_id)]
        reviewer = next(i for i, patch in patches if any(p['path'] == '/reviewers' for p in patch))
        self.assertGreater(reviewer, last_task)
        content = [(i, patch) for i, patch in patches if any(p['path'] == '/description' for p in patch)]
        self.assertEqual(1, len(content))
        self.assertLess(content[0][0], first_task)
        self.assertTrue(all(i < first_task for i, w in enumerate(writes) if w[1].startswith(('tables/', 'metrics/'))))

    def test_typed_relations_replace_plain_pairs_and_second_run_does_not_touch_terms(self):
        customer = self.layout.customer()
        foreign = {'term': {'id': 'foreign'}, 'relationType': 'foreignRelation'}
        self.fake.values['glossaryTerms/name/' + customer['fullyQualifiedName']]['relatedTerms'].append(foreign)
        self.assertEqual(0, self.layout.run('apply'))
        customer = self.layout.customer()
        self.assertIn(foreign, customer['relatedTerms'])
        self.assertEqual({'involvedIn', 'hasPhase', 'definedBy', 'groundedBy', 'foreignRelation'},
                         {r['relationType'] for r in customer['relatedTerms']})
        self.fake.writes.clear()
        self.output.clear()
        self.assertEqual(0, self.layout.run('apply'))
        self.assertTrue(all(w[1].startswith('announcements/') for w in self.fake.writes))
        self.assertTrue(all(l.startswith('unchanged ') or 'renew end time' in l for l in self.output))

    def test_three_tasks_reused_by_term_and_value_at_exact_stages_with_comments(self):
        self.assertEqual(0, self.layout.run('apply'))
        tasks = self.layout.task_list()
        by_word = {t['payload']['value']: t for t in tasks}
        self.assertEqual(3, len(tasks))
        self.assertEqual(('Completed', 'published', 3), (by_word['klient']['status'], by_word['klient']['workflowStageId'], len(by_word['klient']['comments'])))
        self.assertEqual(('InProgress', 'publication', 3), (by_word['kupující']['status'], by_word['kupující']['workflowStageId'], len(by_word['kupující']['comments'])))
        self.assertEqual(('Open', 'review', 0), (by_word['odběratel']['status'], by_word['odběratel']['workflowStageId'], len(by_word['odběratel']['comments'])))
        self.fake.writes.clear()
        # A fresh applier has no local state and must find the same three tasks.
        self.assertEqual(0, make_layout(self.fake, env={}, output=lambda _:None).run('apply'))
        self.assertFalse(any(w[1].startswith('tasks') for w in self.fake.writes))
        self.assertEqual({t['id'] for t in tasks}, {t['id'] for t in self.layout.task_list()})

    def test_no_password_plan_names_admin_fallback_without_signing_in(self):
        self.layout.run('plan')
        self.assertTrue(any('OM_DEMO_PASSWORD absent; admin performs all task actions' in l for l in self.output))
        self.assertEqual([], self.fake.writes)
        for actor in ('jana.dvorakova', 'petr.novak', 'tatrman-maintainer'):
            self.assertIs(self.fake, self.layout.actor(actor))

    def test_terminal_resolution_without_saved_comment_is_repaired_once(self):
        self.fake.omit_terminal_comment = True
        self.assertEqual(0, self.layout.run('apply'))
        task = self.layout.task_for(self.layout.content['tasks'][0])
        self.assertEqual(['Agreed.', 'Model check passed.', 'Published with the model.'],
                         [c['message'] for c in task['comments']])
        self.fake.writes.clear()
        self.assertEqual(0, self.layout.run('apply'))
        self.assertFalse(any(w[1].startswith('tasks/') for w in self.fake.writes))

    def test_duplicate_task_is_refused_instead_of_raised_again(self):
        self.layout.run('apply')
        old = self.layout.task_list()[0]
        self.fake.values['tasks/name/another'] = dict(old, id='duplicate')
        self.fake.writes.clear()
        with self.assertRaisesRegex(om.LayoutError, 'duplicate demo task'):
            list(self.layout.tasks())
        self.assertEqual([], self.fake.writes)

    def test_partial_walk_recovers_without_duplicate_approval_or_comment(self):
        self.layout.run('apply')
        task = self.layout.task_for(self.layout.content['tasks'][1])
        item = self.fake.values['tasks/name/' + task['name']]
        item['comments'] = item['comments'][:1]
        self.fake.writes.clear()
        self.layout.walk_task(self.layout.content['tasks'][1])
        self.assertEqual(2, len(self.fake.writes))
        self.assertTrue(all(w[1].endswith('/comments') for w in self.fake.writes))
        self.assertEqual(3, len(item['comments']))

    def test_verify_is_read_only_and_checks_content_instead_of_only_existence(self):
        self.layout.run('apply')
        customer = self.layout.customer()
        self.fake.values['glossaryTerms/name/' + customer['fullyQualifiedName']]['synonyms'] = ['wrong']
        self.fake.writes.clear()
        self.output.clear()
        self.assertEqual(2, self.layout.run('verify'))
        self.assertEqual(16, len(self.output))
        self.assertTrue(any(l.startswith('FAIL 9 ') for l in self.output))
        self.assertEqual([], self.fake.writes)

    def test_remove_preserves_projected_entities_and_prints_fresh_state_restore(self):
        self.layout.run('apply')
        before = {k: copy.deepcopy(v) for k,v in self.fake.values.items() if k.startswith(('glossaryTerms/', 'tables/', 'metrics/'))}
        self.layout.run('remove', execute=True)
        self.assertEqual(before, {k:v for k,v in self.fake.values.items() if k in before})
        self.assertFalse(any(k.startswith(('users/name/', 'domains/', 'announcements/')) for k in self.fake.values))
        self.assertEqual(['tasks/name/APPROVAL'], [k for k in self.fake.values if k.startswith('tasks/')])
        restore = next(l for l in self.output if l.startswith('restore edited terms:'))
        self.assertIn('--context bp-dsk', restore)
        self.assertIn('--state-file', restore)

    def test_chat_template_is_copied_verbatim_and_build_names_real_task(self):
        source = Path(__file__).resolve().parents[2] / 'project/common/architect/implementation/om-layout-demo/assets/change-1-golem-chat.html'
        if source.exists():
            self.assertEqual(source.read_bytes(), (self.layout.pack / 'change-1-golem-chat.html').read_bytes())
        self.layout.run('apply')
        built = (self.layout.pack / 'build/bp-dsk/change-1-golem-chat.html').read_text()
        task = self.layout.task_for(self.layout.content['tasks'][2])
        self.assertIn('/glossary/demo%20Concepts.cn.role.Customer/activity_feed/tasks', built)
        self.assertIn(task['taskId'], built)
        self.assertNotIn('/tasks/' + task['taskId'], built)
        self.assertNotIn('{{TASK_', built)

    def test_each_targets_chat_build_preserves_the_other_page(self):
        fake = FakeCatalog()
        for target in ('bp-dsk', 'hartland', 'bp-dsk'):
            catalog = FakeCatalog(target)
            catalog.pack = fake.pack
            layout = make_layout(catalog, output=lambda _: None, env={})
            other = 'hartland' if target == 'bp-dsk' else 'bp-dsk'
            other_path = fake.pack / 'build' / other / 'change-1-golem-chat.html'
            before = other_path.read_bytes() if other_path.exists() else None
            self.assertEqual(0, layout.run('apply'))
            built = (fake.pack / 'build' / target / 'change-1-golem-chat.html').read_text()
            self.assertIn(om.ADDRESSES[target] + '/glossary/' + catalog.world + '%20Concepts', built)
            self.assertNotIn(om.ADDRESSES[other], built)
            if before is not None:
                self.assertEqual(before, other_path.read_bytes())

class ActorTests(unittest.TestCase):
    def test_person_and_bot_tokens_stay_in_memory_and_login_failure_uses_admin(self):
        class AuthCatalog(FakeCatalog):
            def write(self, method, path, body=None):
                if path == 'users/login':
                    self.login = body
                    return {'accessToken': 'person-token-for-test'}
                return super().write(method, path, body)
            def get(self, path, missing=False):
                if path.startswith('users/token/'):
                    return {'JWTToken': 'bot-token-for-test'}
                return super().get(path, missing)
            def as_token(self, token):
                return ('client', token)
        fake, output = AuthCatalog(), []
        layout = make_layout(fake, env={'OM_DEMO_PASSWORD': 'test-password'}, output=output.append)
        # Only account operations are needed to prepare the bot record.
        for operation in layout.accounts_and_team():
            if operation.action != 'unchanged':
                operation.executor() if operation.executor else fake.write(operation.method, operation.path, operation.body)
        self.assertEqual(('client','person-token-for-test'), layout.actor('petr.novak'))
        self.assertEqual(('client','bot-token-for-test'), layout.actor('tatrman-maintainer'))
        self.assertNotIn('test-password', str(output))
        self.assertNotIn('person-token-for-test', str(output))
        self.assertEqual('petr.novak@hartland.example', fake.login['email'])
        # Failed sign-in is explicit and never changes the intended account's password.
        layout.actors.clear()
        def denied(*args, **kwargs):
            raise om.LayoutError('catalog request failed (HTTP 401)')
        fake.write = denied
        self.assertIs(fake, layout.actor('petr.novak'))
        self.assertIn('admin performs its actions', output[-1])


class ReferenceSetTests(unittest.TestCase):
    def test_reference_order_does_not_update_or_fail_verification(self):
        fake = FakeCatalog()
        layout = make_layout(fake, env={}, output=lambda _:None)
        self.assertEqual(0, layout.run('apply'))
        metric = fake.values['metrics/name/revenue']
        metric['relatedMetrics'].reverse()
        for index, item in enumerate(metric['relatedMetrics']):
            item.update(name=str(index), href='server-only')
        fake.writes.clear()
        self.assertEqual(0, layout.run('verify'))
        self.assertEqual(0, layout.run('apply'))
        self.assertFalse(any(w[1].startswith('metrics/') for w in fake.writes))
        metric['relatedMetrics'].pop()
        self.assertEqual(1, layout.run('verify'))

    def test_all_owned_reference_lists_are_sets_but_ui_and_comments_stay_ordered(self):
        from om_layout_content import subset, REFERENCE_LISTS
        for field in REFERENCE_LISTS:
            with self.subTest(field=field):
                self.assertTrue(subset({field:[{'id':'b','name':'B'},{'id':'a'}]},
                                       {field:[{'id':'a'},{'id':'b'}]}))
                self.assertFalse(subset({field:[{'id':'a'},{'id':'extra'}]},
                                        {field:[{'id':'a'},{'id':'b'}]}))
        for field in ('comments','nodes','tabs','navigation','synonyms'):
            self.assertFalse(subset({field:['b','a']},{field:['a','b']}))

class ApprovalTests(unittest.TestCase):
    def setUp(self):
        self.fake, self.output = FakeCatalog(), []
        self.layout = make_layout(self.fake, env={}, output=self.output.append)

    def test_reviewers_raise_an_approval_and_apply_approves_once(self):
        self.assertEqual(0, self.layout.run('apply'))
        customer = self.layout.customer()
        self.assertEqual('Approved', customer['entityStatus'])
        self.assertEqual(self.layout.reference('users','petr.novak','user')['id'], customer['reviewers'][0]['id'])
        approval = self.fake.values['tasks/name/APPROVAL']
        self.assertEqual('Approved', approval['status'])
        reviewer_index = next(i for i,w in enumerate(self.fake.writes) if w[0]=='PATCH' and any(p.get('path')=='/reviewers' for p in w[2] if isinstance(p,dict)))
        approval_index = next(i for i,w in enumerate(self.fake.writes) if w[1]=='tasks/APPROVAL/resolve')
        self.assertGreater(approval_index, reviewer_index)
        self.fake.writes.clear()
        self.output.clear()
        self.assertEqual(0, self.layout.run('apply'))
        self.assertFalse(any(w[1]=='tasks/APPROVAL/resolve' for w in self.fake.writes))
        self.assertTrue(all(l.startswith('unchanged ') or 'renew end time' in l for l in self.output))

    def test_existing_in_review_customer_is_repaired_without_rewriting_reviewer(self):
        self.layout.run('apply')
        customer = self.layout.customer()
        self.fake.values['glossaryTerms/name/' + customer['fullyQualifiedName']]['entityStatus']='In Review'
        self.fake.values['tasks/name/APPROVAL'].update(status='Open', availableTransitions=[{'id':'approve'}])
        self.fake.writes.clear()
        fresh = make_layout(self.fake, env={}, output=lambda _:None)
        self.assertEqual(0, fresh.run('apply'))
        self.assertEqual('Approved', fresh.customer()['entityStatus'])
        self.assertEqual(1, sum(w[1]=='tasks/APPROVAL/resolve' for w in self.fake.writes))
        self.assertFalse(any(w[0]=='PATCH' and w[1].startswith('glossaryTerms/') for w in self.fake.writes))

    def test_both_accounts_refused_removes_reviewer_and_plan_reports_skip(self):
        self.layout.run('apply')
        customer = self.layout.customer()
        self.fake.values['glossaryTerms/name/' + customer['fullyQualifiedName']]['entityStatus']='In Review'
        self.fake.values['tasks/name/APPROVAL'].update(status='Open', availableTransitions=[{'id':'approve'}])
        self.fake.deny_approval = True
        class RefusedPetr:
            calls = 0
            def write(client, *args):
                client.calls += 1
                raise om.LayoutError('catalog request failed (HTTP 403)', status=403)
        petr = RefusedPetr()
        self.layout.env={'OM_DEMO_PASSWORD':'test-only'}
        self.layout.actors['petr.novak']=petr
        self.fake.writes.clear()
        self.layout.approve_customer()
        self.assertEqual(1, petr.calls)
        self.assertEqual('Approved', self.layout.customer()['entityStatus'])
        self.assertEqual([], self.layout.customer()['reviewers'])
        self.assertFalse(any(p.get('path')=='/entityStatus' for w in self.fake.writes if w[0]=='PATCH' for p in w[2]))
        self.output.clear()
        self.fake.writes.clear()
        self.layout.run('plan')
        self.assertTrue(any('skip Customer reviewer: approval refused: HTTP 403, HTTP 403' in l for l in self.output))
        self.assertEqual([], self.fake.writes)
        # A fresh process can recognize the catalog's remaining open approval.
        fresh = make_layout(self.fake, env={}, output=lambda _:None)
        self.assertTrue(fresh.reviewer_skip(fresh.customer()))
        self.assertTrue(fresh.content_checks()[3][1]())

    def test_network_failure_does_not_remove_reviewer(self):
        self.layout.run('apply')
        customer = self.layout.customer()
        self.fake.values['glossaryTerms/name/' + customer['fullyQualifiedName']]['entityStatus']='In Review'
        self.fake.values['tasks/name/APPROVAL'].update(status='Open', availableTransitions=[{'id':'approve'}])
        original = self.fake.write
        def unreachable(method,path,body=None):
            if path=='tasks/APPROVAL/resolve':raise om.LayoutError('catalog request failed; check connection')
            return original(method,path,body)
        self.fake.write=unreachable
        with self.assertRaisesRegex(om.LayoutError,'check connection'):
            self.layout.approve_customer()
        self.assertTrue(self.layout.customer()['reviewers'])

class BotTokenTests(unittest.TestCase):
    def test_nearly_expired_owned_bot_token_is_renewed_in_memory(self):
        class TokenCatalog(FakeCatalog):
            def get(self,path,missing=False):
                if path.startswith('users/token/'):
                    return {'JWTToken':'expired-test-token','JWTTokenExpiresAt':1}
                return super().get(path,missing)
            def write(self,method,path,body=None):
                if path=='users/generateToken':
                    self.renewal=(method,body)
                    return {'JWTToken':'renewed-test-token'}
                return super().write(method,path,body)
            def as_token(self,token):
                return ('client',token)
        fake=TokenCatalog()
        fake.values['users/name/tatrman-maintainer']={'id':'bot-id','name':'tatrman-maintainer'}
        output=[]
        layout=make_layout(fake,env={'OM_DEMO_PASSWORD':'test-only'},output=output.append)
        self.assertEqual(('client','renewed-test-token'),layout.actor('tatrman-maintainer'))
        self.assertEqual(('POST',{'id':'bot-id','JWTTokenExpiry':'OneHour'}),fake.renewal)
        self.assertEqual([],output)


class ActionFallbackTests(unittest.TestCase):
    def test_refused_named_action_uses_admin_without_changing_permissions(self):
        fake=FakeCatalog()
        layout=make_layout(fake,env={'OM_DEMO_PASSWORD':'test-only'},output=lambda _:None)
        class Refused:
            def write(self,*args):
                raise om.LayoutError('catalog request failed (HTTP 403)',status=403)
        layout.actors['tatrman-maintainer']=Refused()
        output=[]
        layout.output=output.append
        layout.write_as('tatrman-maintainer','PUT','test-action',{'safe':'value'})
        self.assertEqual([('PUT','test-action',{'safe':'value'})],fake.writes)
        self.assertIn('admin performs the refused action',output[0])
        self.assertFalse(any(w[1].startswith(('users/','roles/','policies/')) for w in fake.writes))


class ChatRouteTests(unittest.TestCase):
    def test_chat_verification_requires_odberatel_to_be_the_opened_task(self):
        fake=FakeCatalog()
        layout=make_layout(fake,env={},output=lambda _:None)
        self.assertEqual(0,layout.run('apply'))
        other=copy.deepcopy(layout.task_list()[-1])
        other.update(id='other-open-task',name='OTHER',status='Open',createdAt=other['createdAt']+1000)
        other['payload']['value']='unowned suggestion'
        fake.values['tasks/name/OTHER']=other
        self.assertEqual(1,layout.run('verify'))
