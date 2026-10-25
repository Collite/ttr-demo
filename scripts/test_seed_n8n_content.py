"""Pinned n8n 2.44.6 content API: local fakes only, no cluster or real credentials."""
import copy
import http.server
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
OWNER = 'Owner-Private9!'
PG = 'Postgres-Private8!'


def templates():
    def node(name, kind, cred=None):
        return dict(id=name, name=name, type='n8n-nodes-base.' + kind, typeVersion=1,
                    position=[0, 0], parameters={}, **({'credentials': {cred: {'name': {
                    'postgres': 'hartland-cz-pg', 'smtp': 'mailpit-smtp', 'httpHeaderAuth': 'webhook-echo-key'}[cred],
                    'id': 'old-instance-id'}}} if cred else {}))
    return [dict(name='Denní přehled prodeje', active=True, settings={'timezone': 'Europe/Prague'},
                 nodes=[node('DB', 'postgres', 'postgres'), node('Mail', 'emailSend', 'smtp')], connections={}),
            dict(name='Webhook echo (test)', active=True, settings={},
                 nodes=[node('Echo', 'webhook', 'httpHeaderAuth')], connections={})]


class State:
    def __init__(self):
        self.creds, self.flows, self.calls = [], [], []
        self.broken, self.echo_bad = None, False


def handler(state):
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def answer(self, data, status=200, envelope=True):
            self.send_response(status)
            if self.path == '/rest/login' and status == 200:
                self.send_header('Set-Cookie', 'n8n-auth=owner; Path=/; HttpOnly')
            self.end_headers()
            self.wfile.write(json.dumps({'data': data} if envelope else data).encode())
        def handle_request(self):
            path = urlsplit(self.path).path
            payload = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0)))) if self.command in ['POST','PATCH'] else None
            state.calls.append((self.command, path, copy.deepcopy(payload)))
            if state.broken == path:
                return self.answer({'echoed': payload, 'secret': PG}, 422, False)
            if path == '/rest/login':
                if self.command == 'POST' and payload != {'emailOrLdapLoginId': 'marketa@hartland.example', 'password': OWNER}:
                    return self.answer(payload, 401)
                return self.answer(dict(id='owner', email='marketa@hartland.example', role='global:owner'))
            if path == '/webhook/echo':
                key = next(c['data']['value'] for c in state.creds if c['type'] == 'httpHeaderAuth')
                if self.headers.get('X-Demo-Key') != key: return self.answer({}, 401, False)
                return self.answer({'wrong': True} if state.echo_bad else payload, envelope=False)
            if self.headers.get('Cookie') != 'n8n-auth=owner': return self.answer({}, 401)
            if path == '/rest/credentials':
                if self.command == 'GET':
                    return self.answer([{k: v for k, v in c.items() if k != 'data'} for c in state.creds])
                item = {**payload, 'id': 'c' + str(len(state.creds)+1)}
                state.creds.append(item)
                return self.answer(item)
            if path.startswith('/rest/credentials/'):
                cid = path.split('/')[3]
                c = next(c for c in state.creds if c['id'] == cid)
                if self.command == 'PATCH': c.update(payload)
                return self.answer(c)
            if path == '/rest/workflows':
                if self.command == 'GET': return self.answer({'count': len(state.flows), 'data': state.flows}, envelope=False)
                assert 'active' not in payload, payload
                item = {**payload, 'id': 'w' + str(len(state.flows)+1), 'versionId': 'v1', 'checksum': 's1', 'active': False, 'activeVersionId': None}
                state.flows.append(item)
                return self.answer(item)
            if path.startswith('/rest/workflows/'):
                parts = path.split('/')
                flow = next(w for w in state.flows if w['id'] == parts[3])
                if len(parts) == 5:
                    if parts[4] == 'activate':
                        assert payload['versionId'] == flow['versionId'], payload
                        assert payload['expectedChecksum'] == flow['checksum'], payload
                        flow['active'], flow['activeVersionId'] = True, flow['versionId']
                    elif parts[4] == 'deactivate': flow['active'], flow['activeVersionId'] = False, None
                    else: return self.answer({}, 404)
                elif self.command == 'PATCH':
                    assert 'active' not in payload, payload
                    assert payload['expectedChecksum'] == flow['checksum'], payload
                    flow.update(payload)
                    flow['versionId'] = 'v' + str(int(flow['versionId'][1:])+1)
                    flow['checksum'] = 's' + flow['versionId'][1:]
                return self.answer(flow)
            return self.answer({}, 404)
        do_GET = do_POST = do_PATCH = handle_request
    return Handler


class ContentTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.workflows = self.dir / 'flows'; self.workflows.mkdir()
        for i, doc in enumerate(templates()): (self.workflows / f'{i}.json').write_text(json.dumps(doc))
        for name, value in [('owner', OWNER), ('pg', PG)]:
            f = self.dir / name; f.write_text(value); f.chmod(0o600)
        self.state = State()
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler(self.state))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        self.url = f'http://127.0.0.1:{server.server_port}'
    def run_seed(self, *args):
        result = subprocess.run([str(ROOT/'scripts/seed-n8n-content.sh'), '--dir', str(self.workflows),
            '--owner-password-file', str(self.dir/'owner'), '--pg-ro-password-file', str(self.dir/'pg'), *args],
            env={**os.environ, 'N8N_URL': self.url}, text=True, capture_output=True, timeout=10)
        for secret in [OWNER, PG, *[c['data'].get('value', '') for c in self.state.creds if c['type']=='httpHeaderAuth']]:
            if secret: self.assertNotIn(secret, result.stdout + result.stderr)
        return result
    def seed(self):
        r = self.run_seed(); self.assertEqual(r.returncode, 0, r.stdout+r.stderr)
    def test_fresh_maps_all_credentials_and_publishes_versions(self):
        self.seed()
        self.assertEqual(len(self.state.creds), 3); self.assertEqual(len(self.state.flows), 2)
        for w in self.state.flows:
            self.assertTrue(w['active']); self.assertEqual(w['activeVersionId'], w['versionId'])
            for n in w['nodes']:
                for kind, ref in n.get('credentials',{}).items():
                    c = next(c for c in self.state.creds if c['name']==ref['name'])
                    self.assertEqual(ref['id'], c['id']); self.assertEqual(kind, c['type'])
        smtp = next(c for c in self.state.creds if c['type']=='smtp')['data']
        self.assertEqual(smtp['port'],25); self.assertFalse(smtp['secure']); self.assertTrue(smtp['disableStartTls'])
    def test_second_run_no_duplicates_preserves_webhook_key_and_publishes_new_draft(self):
        self.seed(); key = self.state.creds[2]['data']['value']; self.state.calls.clear(); self.seed()
        self.assertEqual(len(self.state.creds),3); self.assertEqual(len(self.state.flows),2)
        self.assertEqual(self.state.creds[2]['data']['value'],key)
        self.assertFalse(any(m=='PATCH' and p=='/rest/credentials/c3' for m,p,_ in self.state.calls))
        self.assertTrue(all(w['activeVersionId']==w['versionId'] for w in self.state.flows))
    def test_verify_reads_existing_content_and_echo_without_writes(self):
        self.seed(); self.state.calls.clear()
        r=self.run_seed('--verify'); self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        self.assertTrue(any(p=='/webhook/echo' for _,p,_ in self.state.calls))
        self.assertFalse(any(m!='GET' and p not in ['/rest/login','/webhook/echo'] for m,p,_ in self.state.calls))
    def test_verify_missing_content_fails_without_upserts(self):
        r=self.run_seed('--verify'); self.assertEqual(r.returncode,1)
        self.assertEqual([p for m,p,_ in self.state.calls if m!='GET'],['/rest/login'])
    def test_verify_rejects_wrong_echo_and_unpublished_draft(self):
        self.seed(); self.state.echo_bad=True
        self.assertEqual(self.run_seed('--verify').returncode,1)
        self.state.echo_bad=False; self.state.flows[0]['activeVersionId']='old-version'
        self.assertEqual(self.run_seed('--verify').returncode,1)
    def test_inactive_file_unpublishes_existing_workflow(self):
        self.seed(); p=self.workflows/'0.json'; d=json.loads(p.read_text()); d['active']=False;p.write_text(json.dumps(d));self.seed()
        self.assertFalse(self.state.flows[0]['active'])
    def test_http_failure_never_echoes_secrets(self):
        self.state.broken='/rest/credentials'
        self.assertEqual(self.run_seed().returncode,1)
    def test_duplicate_credential_name_fails_before_mutation(self):
        self.seed(); self.state.creds.append(copy.deepcopy(self.state.creds[0])); self.state.calls.clear()
        self.assertEqual(self.run_seed().returncode,1)
        self.assertFalse(any(m in ['PATCH','POST'] and p!='/rest/login' for m,p,_ in self.state.calls))
    def test_duplicate_workflow_name_fails_before_mutation(self):
        self.seed(); self.state.flows.append(copy.deepcopy(self.state.flows[0]));self.state.calls.clear()
        self.assertEqual(self.run_seed().returncode,1)
        self.assertFalse(any(m in ['PATCH','POST'] and p!='/rest/login' for m,p,_ in self.state.calls))
    def test_invalid_files_fail_before_login(self):
        (self.workflows/'0.json').write_text('{"name":"wrong"}')
        self.assertEqual(self.run_seed().returncode,1); self.assertEqual(self.state.calls,[])
    def test_private_files_required(self):
        (self.dir/'pg').chmod(0o644)
        self.assertEqual(self.run_seed().returncode,1);self.assertEqual(self.state.calls,[])
    def test_unknown_credential_reference_fails_before_login(self):
        p=self.workflows/'0.json';d=json.loads(p.read_text());d['nodes'][0]['credentials']['postgres']['name']='other';p.write_text(json.dumps(d))
        self.assertEqual(self.run_seed().returncode,1);self.assertEqual(self.state.calls,[])

if __name__=='__main__': unittest.main()
