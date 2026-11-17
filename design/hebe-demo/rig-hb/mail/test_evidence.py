"""D33: missing provenance, drift and mismatched/incomplete human records cannot pass."""
import copy
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent


def load(name):
    spec = importlib.util.spec_from_file_location('he_d33_' + name, HERE / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


qualification, walk, rows = load('qualification'), load('walk_record'), load('rows')


def record(deployment):
    def step(**values):
        return {'at': '2030-01-01T12:10:00Z', 'result': 'PASS', **values}
    def thread(n):
        return {'rootMessageId': '<root-' + str(n) + '@example.test>', 'threadSubject': '[4711] Kontrola'}
    steps = {
        'sso': step(mailbox='marketa@hartland.example'),
        'card_read': step(**thread(1), taskId='task1', instanceId='instance1', taskLink='https://process.test/task/task1', detailRows=10, moreRows=2, replyInstructions=True),
        'card_reply': step(**thread(1), taskId='task1', instanceId='instance1', receiptId='answer1', command='schválit', answeredBy='marketa', instanceState='COMPLETED'),
        'console_outcome': step(**thread(2), taskId='task2', instanceId='instance2', receiptId='answer2'),
        'claimed_elsewhere': step(**thread(3), taskId='task3', instanceId='instance3', claimant='bora', handledElsewhere=True, fixtureCompleted=True),
        'free_text': step(**thread(1), notUnderstood=True, noModelCall=True, modelEvidenceRef='audit/window-1'),
        'forward_start': step(**thread(4), proposalId='proposal4', instanceId='instance4', receiptId='start4', confirmation='ano', instruction='spusť kontrolu', ttr_note='spusť kontrolu\n\nJana: reklamace4711', ttr_source='mail:<forward@example.test>', fixtureCompleted=True),
        'bare_forward': step(**thread(5), threeWayQuestion=True, replyCommand='3', closed=True, noInstance=True),
    }
    return {'actor': 'marketa', 'runId': 'cert-run-001', 'deployment': deployment,
            'startedAt': '2030-01-01T12:00:00Z', 'completedAt': '2030-01-01T12:30:00Z', 'steps': steps}


class Qualification(unittest.TestCase):
    def setUp(self):
        self.baseline = json.loads(qualification.BASELINE.read_text())
        self.current = qualification.expected_observation(self.baseline)

    def test_all_sources_and_live_inputs_match_before_inherited_pass(self):
        verdict, detail, fingerprint = qualification.evaluate(self.current, self.baseline)
        self.assertEqual(verdict, 'PASS')
        self.assertIn('inherited qualification', detail)
        self.assertEqual(len(fingerprint), 64)
        self.assertEqual(self.baseline['clients']['hebe']['default'], ['acr', 'basic', 'email', 'profile', 'roles', 'web-origins'])
        self.assertIn('service_account', self.current['policy']['clients']['hebe']['default'])

    def test_each_missing_case_or_unavailable_comparison_is_open(self):
        for case in qualification.CASES:
            bad = copy.deepcopy(self.baseline)
            del bad['cases'][case]
            with self.subTest(case=case):
                self.assertEqual(qualification.evaluate(self.current, bad)[0], 'OPEN')
        self.assertEqual(qualification.evaluate({}, self.baseline)[0], 'OPEN')

    def test_policy_image_tls_and_client_drift_fail_without_changing_baseline(self):
        for key in ['jamesImage', 'webmailImage', 'caSha256', 'jamesFiles', 'webmailRuntime', 'keycloakImageID']:
            bad = copy.deepcopy(self.current)
            bad[key] = 'changed'
            self.assertEqual(qualification.evaluate(bad, self.baseline)[0], 'FAIL', key)
        bad = copy.deepcopy(self.current)
        bad['policy']['clients']['hebe']['default'].append('mail')
        self.assertEqual(qualification.evaluate(bad, self.baseline)[0], 'FAIL')
        bad = copy.deepcopy(self.current)
        bad['policy']['mailAssociations']['optional'].append('other-client')
        self.assertEqual(qualification.evaluate(bad, self.baseline)[0], 'FAIL')
        bad = copy.deepcopy(self.current)
        bad['policy']['mailScope']['mappers'][0]['config']['included.custom.audience'] = 'wrong'
        self.assertEqual(qualification.evaluate(bad, self.baseline)[0], 'FAIL')


class HumanRecord(unittest.TestCase):
    def setUp(self):
        baseline = json.loads(qualification.BASELINE.read_text())
        self.deployment = walk.deployment(baseline, 'qualified-policy-hash')
        self.now = datetime(2030, 1, 1, 13, tzinfo=timezone.utc)

    def validate(self, value, run='cert-run-001'):
        return walk.validate(value, run, self.deployment, self.now)[0]

    def test_missing_template_and_incomplete_action_never_pass(self):
        self.assertEqual(self.validate(None), 'OPEN')
        self.assertEqual(self.validate(walk.template('cert-run-001', self.deployment)), 'OPEN')
        for action in ['sso', 'card_read', 'card_reply', 'console_outcome', 'claimed_elsewhere', 'free_text', 'forward_start', 'bare_forward']:
            value = record(self.deployment)
            del value['steps'][action]
            self.assertEqual(self.validate(value), 'OPEN', action)
        value = record(self.deployment)
        del value['steps']['card_reply']['receiptId']
        self.assertEqual(self.validate(value), 'OPEN')

    def test_complete_matching_human_record_passes(self):
        self.assertEqual(self.validate(record(self.deployment)), 'PASS')
        self.assertIsNone(walk.deployment({}, None))

    def test_wrong_deployment_actor_or_run_fails_and_cross_thread_is_open(self):
        for field, replacement in [('hebeDigest', 'old'), ('admissionFingerprint', 'changed')]:
            value = record(copy.deepcopy(self.deployment))
            value['deployment'][field] = replacement
            self.assertEqual(self.validate(value), 'FAIL')
        self.assertEqual(self.validate(record(self.deployment), run='other-run'), 'FAIL')
        value = record(self.deployment)
        value['actor'] = 'bora'
        self.assertEqual(self.validate(value), 'FAIL')
        value = record(self.deployment)
        value['steps']['card_reply']['rootMessageId'] = '<different@example.test>'
        self.assertEqual(self.validate(value), 'OPEN')


class PreWalk(unittest.TestCase):
    def test_only_named_walk_rows_can_be_open_and_command_remains_non_success(self):
        observations = {n: ('PASS', 'observed') for n in rows.ROWS}
        for n in ['R3-person', 'mail-stranger', 'mail-threads']:
            observations[n] = ('OPEN', 'human/walk not yet performed')
        result = rows.table(observations)
        self.assertTrue(rows.pre_walk(result))
        self.assertEqual(rows.exit_code(result), 3)
        observations['R3-negative'] = ('OPEN', 'comparison missing')
        self.assertFalse(rows.pre_walk(rows.table(observations)))
        observations['R3-negative'] = ('FAIL', 'drift')
        self.assertFalse(rows.pre_walk(rows.table(observations)))


if __name__ == '__main__':
    unittest.main()
