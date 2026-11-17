"""Mail selection retains the engine baseline; no missing live row becomes PASS."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('he_s36_verify', HERE / 'verify.py')
verify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify)


class MailProfile(unittest.TestCase):
    def test_mail_profile_fixes_cluster_and_has_separate_state(self):
        with tempfile.NamedTemporaryFile() as ca:
            result = subprocess.run(['bash', '-c',
                'source "$1" --profile mail; echo "$PROFILE|$CONTEXT|$HOST|$STATE"', 'bash', str(HERE.parent / 'verify.sh')],
                env={**os.environ, 'HEBE_VERIFY_CA_FILE': ca.name, 'CONTEXT': 'hartland',
                     'HOST': 'wrong', 'HEBE_VERIFY_STATE': '/tmp/cert-state'}, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('mail|bp-dsk|hebe.192-168-1-38.nip.io|/tmp/cert-state/bp-dsk/mail/marketa.json', result.stdout)

    def test_live_checks_fail_closed_and_unperformed_rows_remain_open(self):
        ready = {'checks': [{'name': name, 'ok': True, 'detail': 'ok'} for name in ['channels', 'delivery', 'mail']]}
        status = {'channels': [{'name': 'email', 'health': 'Up'}]}
        doctor = {'checks': [{'name': 'mail', 'status': 'pass', 'message': 'SMTP and IMAP accept sign-in'}]}
        substrate = {'R1': {'code': 530, 'dataSent': False}, 'R2': {'code': 503, 'dataSent': False}}
        rows = {name: value for name, value, _ in verify.assess(ready, status, doctor, substrate)}
        self.assertTrue(all(rows[n] == 'PASS' for n in ['mail-channels', 'mail-delivery', 'R1', 'R2', 'R3-service']))
        self.assertTrue(all(rows[n] == 'OPEN' for n in ['R3-person', 'R3-negative', 'mail-stranger', 'mail-threads']))
        for broken in [({}, status, doctor, substrate), (ready, {}, doctor, substrate),
                       (ready, status, {}, substrate), (ready, status, doctor, {})]:
            self.assertIn('FAIL', [r[1] for r in verify.assess(*broken)])


if __name__ == '__main__':
    unittest.main()
