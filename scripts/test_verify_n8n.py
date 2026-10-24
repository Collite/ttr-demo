"""N8-P1 S1.2: no real cluster, credentials or external HTTP; exercise the shipped CLI too."""
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import unittest

from scripts.verify_n8n_lib import CheckError, http_code, managed_role_version, websocket_status, probe_push

ROOT = Path(__file__).resolve().parents[1]
IMAGE = 'docker.n8n.io/n8nio/n8n:2.44.6'
GUID = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'


def fixture():
    # n8n-1.24.43 templates/_helpers.tpl `n8n.main.name` and the live rendered Deployment.
    container = {'name': 'n8n-main', 'image': IMAGE,
                 'volumeMounts': [{'name': 'data', 'mountPath': '/home/node/.n8n'}]}
    return {
        'application': {'status': {'sync': {'status': 'Synced'}, 'health': {'status': 'Healthy'}}},
        'deployment': {'metadata': {'generation': 2}, 'spec': {'replicas': 1, 'template': {'spec': {
            'containers': [container], 'volumes': [{'name': 'data', 'persistentVolumeClaim': {'claimName': 'n8n-main-persistence'}}]}}},
            'status': {'observedGeneration': 2, 'replicas': 1, 'readyReplicas': 1, 'updatedReplicas': 1}},
        'pods': {'items': [{'metadata': {'name': 'n8n-ready'}, 'spec': {'containers': [container]},
            'status': {'conditions': [{'type': 'Ready', 'status': 'True'}]}}]},
        'pvc': {'metadata': {'name': 'n8n-main-persistence'}, 'status': {'phase': 'Bound'}},
        'cluster': {'status': {'managedRolesStatus': {'byStatus': {'reconciled': ['n8n']},
            'passwordStatus': {'n8n': {'resourceVersion': '42'}}}}},
        'db_type': 'postgresdb',
    }


class FakeHTTP(BaseHTTPRequestHandler):
    def do_GET(self):
        self.server.requests.append((self.path, dict(self.headers)))
        if self.path.startswith('/rest/push?'):
            code = self.server.push_code
            self.send_response(code)
            if code == 101:
                self.send_header('Connection', 'Upgrade')
                self.send_header('Upgrade', 'websocket')
                key = self.headers.get('Sec-WebSocket-Key', '')
                accept = base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()
                self.send_header('Sec-WebSocket-Accept', 'bad' if self.server.bad_accept else accept)
            self.end_headers()
            return
        code = self.server.codes.get(self.path, 200)
        self.send_response(code)
        if code == 302:
            self.send_header('Location', '/redirect-target')
        self.end_headers()
        if self.path == '/rest/settings':
            self.wfile.write(json.dumps(self.server.settings).encode())
        else:
            self.wfile.write(b'{"status":"ok"}')

    def log_message(self, *args):
        pass


class VerifyTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), FakeHTTP)
        self.server.codes = {}
        self.server.requests = []
        self.server.push_code = 401
        self.server.bad_accept = False
        self.server.settings = {'data': {'userManagement': {'showSetupOnFirstLoad': False}}}
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.url = f'http://127.0.0.1:{self.server.server_port}'
        self.data = fixture()
        self.state = self.directory / 'state.json'
        self.calls = self.directory / 'calls.jsonl'
        fake = self.directory / 'kubectl'
        fake.write_text('''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
with open(os.environ['N8N_FAKE_CALLS'], 'a') as f: f.write(json.dumps(args) + '\\n')
d = json.loads(Path(os.environ['N8N_FAKE_STATE']).read_text())
if 'exec' in args:
    assert args[-3:] == ['--', 'printenv', 'DB_TYPE'], args
    assert args[args.index('-c') + 1] == 'n8n-main', args
    print(d['db_type']); sys.exit(0)
assert 'get' in args, args
kind = args[args.index('get') + 1]
assert kind in ['application', 'deployment', 'pods', 'pvc', 'cluster'], args
if d.get('fail') == kind:
    print('PRIVATE_RAW_ERROR_BODY', file=sys.stderr); sys.exit(1)
print('PRIVATE_BAD_JSON' if d.get('malformed') == kind else json.dumps(d[kind]))
''')
        fake.chmod(0o755)

    def run_rig(self, *args, env_extra=None):
        self.state.write_text(json.dumps(self.data))
        env = {**os.environ, 'PATH': str(self.directory) + os.pathsep + os.environ['PATH'],
            'KUBE_CONTEXT': 'test-context', 'N8N_URL': self.url,
            'N8N_IMAGE': IMAGE, 'N8N_FAKE_STATE': str(self.state), 'N8N_FAKE_CALLS': str(self.calls)}
        env.update(env_extra or {})
        return subprocess.run([str(ROOT / 'scripts/verify-n8n.sh'), *args], cwd=ROOT,
            env=env, text=True, capture_output=True, timeout=10)

    def test_http_code_preserves_errors_and_does_not_follow_redirects(self):
        self.assertEqual(http_code(self.url + '/healthz'), 200)
        self.server.codes['/healthz'] = 401
        self.assertEqual(http_code(self.url + '/healthz'), 401)
        self.server.codes['/healthz'] = 302
        self.assertEqual(http_code(self.url + '/healthz'), 302)
        self.assertFalse(any(p == '/redirect-target' for p, _ in self.server.requests))

    def test_managed_role_requires_nonempty_resource_version_and_no_reconciliation_failure(self):
        self.assertEqual(managed_role_version(self.data['cluster']), '42')
        for bad in [{}, {'status': {}}, {'status': {'managedRolesStatus': []}}]:
            with self.subTest(bad=bad), self.assertRaises(CheckError):
                managed_role_version(bad)
        for value in ['', None, 42, False]:
            doc = copy.deepcopy(self.data['cluster'])
            doc['status']['managedRolesStatus']['passwordStatus']['n8n']['resourceVersion'] = value
            with self.subTest(value=value), self.assertRaises(CheckError):
                managed_role_version(doc)
        self.data['cluster']['status']['managedRolesStatus']['cannotReconcile'] = {'n8n': ['private detail']}
        with self.assertRaises(CheckError):
            managed_role_version(self.data['cluster'])

    def test_websocket_status_classifies_auth_and_upgrade_separately_from_bad_gateway(self):
        for code in [101, 401]:
            self.assertTrue(websocket_status(code))
        for code in [200, 302, 400, 403, 426, 500, 504]:
            self.assertFalse(websocket_status(code))

    def test_real_push_handshake_headers_and_accept_validation(self):
        self.server.push_code = 101
        self.assertEqual(probe_push(self.url), 101)
        request, headers = self.server.requests[-1]
        self.assertTrue(request.startswith('/rest/push?pushRef='))
        self.assertEqual(headers['Sec-WebSocket-Version'], '13')
        self.assertEqual(headers['Origin'], self.url)
        self.server.bad_accept = True
        with self.assertRaises(CheckError):
            probe_push(self.url)

    def test_all_p1_pass_later_phases_explicitly_pending_and_context_always_set(self):
        result = self.run_rig()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for n in range(1, 7):
            self.assertIn(f'✓ V{n} ', result.stdout)
        for n in range(7, 12):
            self.assertIn(f'○ V{n} not yet (P', result.stdout)
        self.assertIn('6 pass · 0 fail · 5 not yet', result.stdout)
        for line in self.calls.read_text().splitlines():
            args = json.loads(line)
            self.assertEqual(args[:2], ['--context', 'test-context'])
            self.assertFalse(any(x in args for x in ['apply', 'patch', 'delete', 'create', 'secret']))

    def test_unsynced_application_fails_but_all_other_checks_still_run(self):
        self.data['application']['status']['sync']['status'] = 'OutOfSync'
        result = self.run_rig()
        self.assertEqual(result.returncode, 1)
        self.assertIn('✗ V1 ', result.stdout)
        self.assertIn('✓ V6 ', result.stdout)

    def test_pod_and_rollout_must_really_be_ready_on_the_pinned_image(self):
        for problem in ['ready', 'image', 'observed', 'updated', 'missing-pod']:
            self.data = fixture()
            if problem == 'ready':
                self.data['pods']['items'][0]['status']['conditions'][0]['status'] = 'False'
            elif problem == 'image':
                self.data['pods']['items'][0]['spec']['containers'][0]['image'] = 'n8n:old'
            elif problem == 'observed':
                self.data['deployment']['status']['observedGeneration'] = 1
            elif problem == 'updated':
                self.data['deployment']['status']['updatedReplicas'] = 0
            else:
                self.data['pods']['items'] = []
            with self.subTest(problem=problem):
                result = self.run_rig()
                self.assertEqual(result.returncode, 1)
                self.assertIn('✗ V2 ', result.stdout)

    def test_unbound_or_unmounted_pvc_fails_v2(self):
        for problem in ['phase', 'volume', 'mount']:
            self.data = fixture()
            if problem == 'phase':
                self.data['pvc']['status']['phase'] = 'Pending'
            elif problem == 'volume':
                self.data['deployment']['spec']['template']['spec']['volumes'] = []
            else:
                self.data['deployment']['spec']['template']['spec']['containers'][0]['volumeMounts'] = []
            with self.subTest(problem=problem):
                result = self.run_rig()
                self.assertEqual(result.returncode, 1)
                self.assertIn('✗ V2 ', result.stdout)

    def test_both_public_health_endpoints_need_200_without_redirects(self):
        for code in [302, 503]:
            self.server.codes['/healthz/readiness'] = code
            result = self.run_rig()
            self.assertEqual(result.returncode, 1)
            self.assertIn('✗ V3 ', result.stdout)

    def test_owner_setup_must_be_explicitly_false_in_known_envelope(self):
        for value in [True, 'false', None]:
            self.server.settings['data']['userManagement']['showSetupOnFirstLoad'] = value
            result = self.run_rig()
            self.assertEqual(result.returncode, 1)
            self.assertIn('✗ V4 ', result.stdout)
        self.server.settings = {'showSetupOnFirstLoad': False}
        result = self.run_rig()
        self.assertEqual(result.returncode, 1)
        self.assertIn('✗ V4 ', result.stdout)

    def test_websocket_upgrade_101_and_auth_401_pass_but_426_and_504_fail(self):
        for code in [101, 401, 426, 504]:
            self.server.push_code = code
            result = self.run_rig()
            self.assertEqual(result.returncode, 0 if code in [101, 401] else 1)
            self.assertIn(('✓' if code in [101, 401] else '✗') + ' V5 ', result.stdout)

    def test_database_engine_and_cnpg_password_status_both_required(self):
        for problem in ['engine', 'password']:
            self.data = fixture()
            if problem == 'engine':
                self.data['db_type'] = 'sqlite'
            else:
                self.data['cluster']['status']['managedRolesStatus']['passwordStatus'] = {}
            result = self.run_rig()
            self.assertEqual(result.returncode, 1)
            self.assertIn('✗ V6 ', result.stdout)

    def test_kubectl_failure_and_bad_json_are_safe_failures_not_tracebacks(self):
        for key in ['fail', 'malformed']:
            self.data = {**fixture(), key: 'application'}
            result = self.run_rig()
            self.assertEqual(result.returncode, 1)
            self.assertIn('✗ V1 ', result.stdout)
            self.assertIn('✓ V6 ', result.stdout)
            self.assertNotIn('PRIVATE_', result.stdout + result.stderr)
            self.assertNotIn('Traceback', result.stdout + result.stderr)

    def test_help_and_invalid_arguments_make_no_requests(self):
        result = self.run_rig('--help')
        self.assertEqual(result.returncode, 0)
        result = self.run_rig('--phase', '4')
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.server.requests, [])
        self.assertFalse(self.calls.exists())

    def test_credential_urls_rejected_before_requests_without_logging_password(self):
        result = self.run_rig(env_extra={'N8N_URL': 'https://user:PRIVATE_PASSWORD@example.com'})
        self.assertEqual(result.returncode, 2)
        self.assertNotIn('PRIVATE_PASSWORD', result.stdout + result.stderr)
        self.assertEqual(self.server.requests, [])
        self.assertFalse(self.calls.exists())


if __name__ == '__main__':
    unittest.main()
