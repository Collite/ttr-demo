"""T3 correlates exactly one body-free receipt and two empty, spaced polls; no resend."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('he_s36_fixture', HERE / 'fixture.py')
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


def receipt():
    return {'seq': 12, 'sessionId': 'email', 'turnId': '<stranger@example.test>', 'tool': 'mail.dropped', 'ok': True,
            'argsRedacted': json.dumps({'messageId': '<stranger@example.test>', 'sender': fixture.customer.CUSTOMER, 'reason': 'sender is not the bound user'})}


def state(deployment):
    return {'runId': 'cert-run-001', 'deployment': deployment, 'phase': 'complete', 'receiptSeq': 12,
            'fixture': {'to': fixture.customer.MARKETA, 'messageId': '<complaint@example.test>'},
            'stranger': {'to': fixture.customer.HEBE, 'messageId': '<stranger@example.test>', 'sentAt': '2030-01-01T12:00:00Z'},
            'polls': [{'at': '2030-01-01T12:00:25Z', 'replies': 0}, {'at': '2030-01-01T12:00:50Z', 'replies': 0}]}


class Stranger(unittest.TestCase):
    def test_receipt_requires_exact_sender_id_reason_and_no_body_or_duplicate(self):
        good = receipt()
        self.assertEqual(fixture.drop([good], good['turnId'])['seq'], 12)
        self.assertIsNone(fixture.drop([good], '<other@example.test>'))
        self.assertIsNone(fixture.drop([good, good], good['turnId']))
        bad = receipt()
        args = json.loads(bad['argsRedacted'])
        args['body'] = 'must never be stored'
        bad['argsRedacted'] = json.dumps(args)
        self.assertIsNone(fixture.drop([bad], good['turnId']))

    def test_missing_poll_receipt_or_wrong_run_never_pass_and_reply_fails(self):
        current = {'deployed': 'exact'}
        good = state(current)
        self.assertEqual(fixture.assess(good, 'cert-run-001', current, [receipt()], [])[0], 'PASS')
        self.assertEqual(fixture.assess(None, 'cert-run-001', current, [], [])[0], 'OPEN')
        self.assertEqual(fixture.assess(good, 'other-run', current, [receipt()], [])[0], 'FAIL')
        self.assertEqual(fixture.assess(good, 'cert-run-001', current, [], [])[0], 'OPEN')
        self.assertEqual(fixture.assess(good, 'cert-run-001', current, [receipt()], [{'messageId': 'reply'}])[0], 'FAIL')
        bad = copy.deepcopy(good)
        bad['polls'][1]['at'] = '2030-01-01T12:00:26Z'
        self.assertEqual(fixture.assess(bad, 'cert-run-001', current, [receipt()], [])[0], 'OPEN')

    def test_checkpoint_never_blindly_repeats_completed_or_uncertain_sends(self):
        baseline = json.loads(fixture.qualification.BASELINE.read_text())
        deployment = fixture.walk_record.deployment(baseline, 'admission-hash')
        with tempfile.TemporaryDirectory() as temporary, patch.object(fixture, 'console', return_value={}), \
             patch.object(fixture.qualification, 'verify', return_value=('PASS', 'matched', 'admission-hash')), \
             patch.object(fixture, 'receipts', return_value=[receipt()]), patch.object(fixture.live, 'run') as live:
            path = Path(temporary) / 'fixture.json'
            value = state(deployment)
            fixture.save(path, value)
            self.assertEqual(fixture.prepare('cert-run-001', path)['receiptSeq'], 12)
            live.assert_not_called()
            value['fixture'] = {'pending': True}
            fixture.save(path, value)
            with self.assertRaisesRegex(RuntimeError, 'uncertain prior send'):
                fixture.prepare('cert-run-001', path)
            live.assert_not_called()


if __name__ == '__main__':
    unittest.main()
