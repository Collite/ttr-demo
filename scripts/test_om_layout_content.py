"""Frozen-content contract specs, with no catalog connection or real credentials."""
import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_om_layout import FakeCatalog, make_layout
import om_layout as om


class AccountTests(unittest.TestCase):
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

    def test_reviewers_follow_all_tasks_and_other_fields_precede_them(self):
        self.assertEqual(0, self.layout.run('apply'))
        writes = self.fake.writes
        first_task = next(i for i, w in enumerate(writes) if w[:2] == ('POST', 'tasks'))
        last_task = max(i for i, w in enumerate(writes) if w[1].startswith('tasks'))
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
        self.assertEqual(15, len(self.output))
        self.assertTrue(any(l.startswith('FAIL 9 ') for l in self.output))
        self.assertEqual([], self.fake.writes)

    def test_remove_preserves_projected_entities_and_prints_fresh_state_restore(self):
        self.layout.run('apply')
        before = {k: copy.deepcopy(v) for k,v in self.fake.values.items() if k.startswith(('glossaryTerms/', 'tables/', 'metrics/'))}
        self.layout.run('remove', execute=True)
        self.assertEqual(before, {k:v for k,v in self.fake.values.items() if k in before})
        self.assertFalse(any(k.startswith(('tasks/', 'users/name/', 'domains/', 'announcements/')) for k in self.fake.values))
        restore = next(l for l in self.output if l.startswith('restore edited terms:'))
        self.assertIn('--context bp-dsk', restore)
        self.assertIn('--state-file', restore)

    def test_chat_template_is_copied_verbatim_and_build_names_real_task(self):
        source = Path(__file__).resolve().parents[2] / 'project/common/architect/implementation/om-layout-demo/assets/change-1-golem-chat.html'
        if source.exists():
            self.assertEqual(source.read_bytes(), (self.layout.pack / 'change-1-golem-chat.html').read_bytes())
        self.layout.run('apply')
        built = (self.layout.pack / 'build/change-1-golem-chat.html').read_text()
        task = self.layout.task_for(self.layout.content['tasks'][2])
        self.assertIn('/tasks/' + task['taskId'], built)
        self.assertNotIn('{{TASK_', built)

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
