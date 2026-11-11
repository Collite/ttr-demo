"""Exercise multipart deployment, guarded cleanup and credential-safe scratch lifecycle."""
import base64
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import deploy
import probe


class Deploy(unittest.TestCase):
    def remote(self, cleanup=False, active=0):
        self.requests = []
        def open_request(req, **kwargs):
            self.requests.append(req)
            if '/deployment/create' in req.full_url:
                response = {'id': 'fixture-id', 'name': 'hebe-p2-cert'}
            elif '/deployment?' in req.full_url:
                response = [{'id': 'fixture-id'}]
            elif '/count?' in req.full_url:
                response = {'count': active}
            else:
                response = None
            return contextlib.closing(io.BytesIO(json.dumps(response).encode()))
        payload = {'token': 'private-bearer', 'cleanup': cleanup, 'bpmn': '<saved-fixture/>',
                   'reconciler': 'import os\ndef main():\n assert os.environ["TTR_BEARER"] == "private-bearer"\n print("reconciled")'}
        output = io.StringIO()
        with patch('sys.stdin', io.StringIO(json.dumps(payload))), contextlib.redirect_stdout(output), \
             patch('urllib.request.urlopen', side_effect=open_request), patch.dict(os.environ):
            exec(deploy.REMOTE, {})
        return json.loads(output.getvalue())

    def test_multipart_duplicate_filter_and_existing_reconciler(self):
        result = self.remote()
        req, = self.requests
        self.assertEqual(req.get_method(), 'POST')
        self.assertTrue(req.full_url.endswith('/engine-rest/deployment/create'))
        self.assertIn('multipart/form-data; boundary=', req.headers['Content-type'])
        body = req.data.decode()
        for value in ['enable-duplicate-filtering', 'deploy-changed-only', 'true',
                      'hebe-p2-cert.bpmn', '<saved-fixture/>']:
            self.assertIn(value, body)
        self.assertEqual(result['authorization'], 'reconciled')
        self.assertNotIn('private-bearer', json.dumps(result))

    def test_cleanup_refuses_active_instance_and_never_cascades(self):
        with self.assertRaises(RuntimeError):
            self.remote(cleanup=True, active=1)
        self.assertFalse(any(r.get_method() == 'DELETE' for r in self.requests))
        self.assertEqual(self.remote(cleanup=True)['removed'], 1)
        deleted = [r.full_url for r in self.requests if r.get_method() == 'DELETE']
        self.assertEqual(deleted, ['http://process-engine.process-engine.svc/engine-rest/deployment/fixture-id?cascade=false'])

    def test_operator_token_requires_private_file_and_personal_bora(self):
        claims = base64.urlsafe_b64encode(json.dumps({'preferred_username': 'bora'}).encode()).decode().rstrip('=')
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, clear=True):
            path = Path(tmp, 'bearer')
            path.write_text('header.' + claims + '.signature')
            os.environ['TTR_BEARER_FILE'] = str(path)
            path.chmod(0o644)
            with self.assertRaises(ValueError):
                deploy.token()
            path.chmod(0o600)
            self.assertEqual(deploy.token(), path.read_text())
            del os.environ['TTR_BEARER_FILE']
            os.environ['TTR_BEARER'] = 'not-a-personal-token'
            with self.assertRaises(ValueError):
                deploy.token()

    def test_probe_payload_stays_out_of_argv_and_always_cleans_own_pod(self):
        calls = []
        def kc(*args, **kwargs):
            calls.append((args, kwargs))
            if 'exec' in args:
                return subprocess.CompletedProcess(args, 1, '{"probeError":"HTTPError","httpStatus":403}', '')
            return subprocess.CompletedProcess(args, 0, '{}', '')
        with patch.object(probe, 'kubectl', side_effect=kc):
            with self.assertRaisesRegex(RuntimeError, 'HTTPError HTTP 403'):
                probe.run('pass', {'token': 'private-token'})
        self.assertEqual(calls[-1][0][2], 'delete')
        for argv, _ in calls:
            self.assertNotIn('private-token', str(argv))
        create = json.loads(calls[0][1]['input'])
        self.assertEqual(create['spec']['terminationGracePeriodSeconds'], 1)
        self.assertFalse(create['spec']['automountServiceAccountToken'])
        with patch.object(probe.subprocess, 'run') as command:
            probe.kubectl('get', 'pod')
            self.assertEqual(command.call_args.args[0][:3], ['kubectl', '--context', 'bp-dsk'])


if __name__ == '__main__':
    unittest.main()
