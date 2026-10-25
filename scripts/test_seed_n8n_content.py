"""Pinned n8n 2.44.6 content API: local fakes only, no cluster or real credentials."""
import contextlib
import io
from unittest.mock import patch
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
from urllib.parse import urlsplit, parse_qs

ROOT = Path(__file__).resolve().parents[1]
OWNER = 'Owner-Private9!'
PG = 'private-db-password-without-n8n-complexity'


def templates():
    def node(name, kind, cred=None):
        return dict(id=name, name=name, type='n8n-nodes-base.' + kind, typeVersion=1,
                    position=[0, 0], parameters=({'authentication':'headerAuth','path':'echo','httpMethod':'POST'} if kind=='webhook' else {}), **({'credentials': {cred: {'name': {
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
        self.truncated, self.echo_status = None, None


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
            if state.truncated == path:
                self.send_response(200); self.send_header('Content-Length', '1000'); self.end_headers()
                self.wfile.write(b'{'); self.close_connection=True; return
            if state.broken == path:
                return self.answer({'echoed': payload, 'secret': PG}, 422, False)
            if path == '/rest/login':
                if self.command == 'POST' and payload != {'emailOrLdapLoginId': 'marketa@hartland.example', 'password': OWNER}:
                    return self.answer(payload, 401)
                return self.answer(dict(id='owner', email='marketa@hartland.example', role='global:owner'))
            if path == '/webhook/echo':
                if state.echo_status: return self.answer({'secret':PG}, state.echo_status, False)
                key = next(c['data']['value'] for c in state.creds if c['type'] == 'httpHeaderAuth')
                if self.headers.get('X-Demo-Key') != key: return self.answer({}, 401, False)
                return self.answer({'wrong': True} if state.echo_bad else payload, envelope=False)
            if self.headers.get('Cookie') != 'n8n-auth=owner': return self.answer({}, 401)
            if path == '/rest/projects/personal': return self.answer({'id':'personal-owner','type':'personal'})
            filters=json.loads(parse_qs(urlsplit(self.path).query).get('filter',['{}'])[0])
            def selected(items):
                return [i for i in items if ('projectId' not in filters or i.get('projectId')==filters['projectId'])
                    and ('isArchived' not in filters or i.get('isArchived',False)==filters['isArchived'])]
            if path == '/rest/credentials':
                if self.command == 'GET':
                    return self.answer([{k: v for k, v in c.items() if k != 'data'} for c in selected(state.creds)])
                item = {**payload, 'id': 'c' + str(len(state.creds)+1)}
                state.creds.append(item)
                return self.answer(item)
            if path.startswith('/rest/credentials/'):
                cid = path.split('/')[3]
                c = next(c for c in state.creds if c['id'] == cid)
                if self.command == 'PATCH': c.update(payload)
                return self.answer(c)
            if path == '/rest/workflows':
                if self.command == 'GET':
                    items=selected(state.flows); q=parse_qs(urlsplit(self.path).query)
                    skip=int(q.get('skip',[0])[0]); take=min(int(q.get('take',[100])[0]),100)
                    return self.answer({'count':len(items),'data':items[skip:skip+take]}, envelope=False)
                assert 'active' not in payload, payload
                item = {**payload, 'id': 'w' + str(len(state.flows)+1), 'versionId': 'v1', 'checksum': 's1', 'active': False, 'activeVersionId': None}
                item['settings']={k:v for k,v in item['settings'].items() if v!='DEFAULT' and not (k=='executionTimeout' and v==-1)}
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
                    if flow.get('isArchived'): return self.answer({},400)
                    settings={**flow.get('settings',{}),**payload.get('settings',{})}
                    defaults={'errorWorkflow','timezone','saveDataErrorExecution','saveDataSuccessExecution','saveManualExecutions','saveExecutionProgress'}
                    settings={k:v for k,v in settings.items() if not (k in defaults and v=='DEFAULT') and not (k=='executionTimeout' and v==-1)}
                    flow.update(payload); flow['settings']=settings
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
            '--webhook-key-file', str(self.dir/'webhook-key'), '--owner-password-file', str(self.dir/'owner'), '--pg-ro-password-file', str(self.dir/'pg'), *args],
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
    def test_missing_original_key_refuses_rotation(self):
        self.seed(); key=self.state.creds[2]['data']['value']; (self.dir/'webhook-key').unlink(); self.state.calls.clear()
        self.assertEqual(self.run_seed().returncode,1)
        self.assertEqual(self.state.creds[2]['data']['value'],key)
        self.assertFalse(any(m in ['PATCH','POST'] and p!='/rest/login' for m,p,_ in self.state.calls))
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
    def test_rig_phase3_delegates_read_only_content_verification(self):
        from scripts.verify_n8n_lib import Rig
        self.seed(); self.state.calls.clear()
        rig=Rig('test-context',self.url,'n8n:test',phase=3,content_args=[
            '--dir',str(self.workflows),'--owner-password-file',str(self.dir/'owner'),
            '--pg-ro-password-file',str(self.dir/'pg'),'--webhook-key-file',str(self.dir/'webhook-key')])
        with contextlib.ExitStack() as stack:
            for name in ['application','workload','health','owner','push','database','personas','mailpit','invitation']:
                stack.enter_context(patch.object(rig,name,return_value='fake prior row'))
            output=io.StringIO()
            with contextlib.redirect_stdout(output): result=rig.run()
        self.assertEqual(result,0,output.getvalue())
        self.assertIn('✓ V10 ',output.getvalue());self.assertIn('10 pass · 0 fail · 1 not yet',output.getvalue())
        self.assertFalse(any(m!='GET' and p not in ['/rest/login','/webhook/echo'] for m,p,_ in self.state.calls))

    def test_shipped_workflows_import_publish_and_verify_with_the_pinned_shapes(self):
        for p in self.workflows.glob('*.json'): p.unlink()
        for source in (ROOT/'n8n/demo').glob('*.json'):
            (self.workflows/source.name).write_text(source.read_text())
        self.seed(); r=self.run_seed('--verify'); self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        for flow in self.state.flows:
            self.assertEqual(flow['settings']['timezone'],'Europe/Prague')
        digest=next(w for w in self.state.flows if w['name']=='Denní přehled prodeje')
        self.assertEqual(next(n for n in digest['nodes'] if n['type'].endswith('.scheduleTrigger'))['parameters']['rule']['interval'][0]['triggerAtHour'],7)
        query=next(n for n in digest['nodes'] if n['type'].endswith('.postgres'))['parameters']['query']
        oracle=(ROOT/'run-set/routing/validation/channel-2025.yaml').read_text().split('core: |\n',1)[1].split('assert:',1)[0]
        self.assertEqual(' '.join(query.split()), ' '.join(oracle.split()))
        code=next(n for n in digest['nodes'] if n['type'].endswith('.code'))['parameters']['jsCode']
        fixture=[{'json':{'channel':'store','revenue':'1234.50'}},{'json':{'channel':'<unsafe>','revenue':'1'}}]
        result=subprocess.run(['node','-e', "const [code,items]=JSON.parse(process.argv[1]);console.log(JSON.stringify(new Function('$input',code)({all:()=>items})));",json.dumps([code,fixture])],capture_output=True,text=True,check=True)
        html=json.loads(result.stdout)[0]['json']['html']
        self.assertIn('Kanál prodejen',html);self.assertIn('&lt;unsafe&gt;',html);self.assertIn('2025',html);self.assertIn('Hartland n8n',html)
        import re, itertools
        labels=dict(re.findall(r'^      (\w+): \[([^,\]]+)',(ROOT/'run-set/routing/validation/channel-2025.yaml').read_text(),re.M))
        rows=[{'json':{'channel':c,'revenue':i*100}} for i,c in enumerate(['store','web','marketplace'],1)]
        for order in itertools.permutations(rows):
            r=subprocess.run(['node','-e', "const [code,items]=JSON.parse(process.argv[1]);console.log(JSON.stringify(new Function('$input',code)({all:()=>items})));",json.dumps([code,order])],capture_output=True,text=True,check=True)
            text=json.loads(r.stdout)[0]['json']['html']
            positions=[text.index(labels[c]) for c in ['marketplace','web','store']]
            self.assertEqual(positions,sorted(positions))

    def test_shell_vault_reads_use_private_files_and_cleanup_on_failure(self):
        bin_dir=self.dir/'bin';bin_dir.mkdir();fake=bin_dir/'az'
        fake.write_text("#!/usr/bin/env python3\nimport os,sys\nfrom pathlib import Path\n"
                        "key=sys.argv[sys.argv.index('--name')+1]\n"
                        "assert key == 'n8n-owner-password', 'verify must not read PG vault key'\n"
                        "print(os.environ['FAKE_OWNER'] if key=='n8n-owner-password' else os.environ['FAKE_PG'])\n")
        fake.chmod(0o755)
        # No workflows in the fake: --verify must fail after login and clean both vault temporary files.
        r=subprocess.run([str(ROOT/'scripts/seed-n8n-content.sh'),'--dir',str(self.workflows),'--verify',
            '--webhook-key-file',str(self.dir/'absent-key')],env={**os.environ,'N8N_URL':self.url,
            'PATH':str(bin_dir)+os.pathsep+os.environ['PATH'],'TMPDIR':str(self.dir),'FAKE_OWNER':OWNER,'FAKE_PG':PG},
            capture_output=True,text=True,timeout=10)
        self.assertEqual(r.returncode,1)
        self.assertEqual(list(self.dir.glob('n8n-content.*')),[])
        self.assertNotIn(OWNER,r.stdout+r.stderr);self.assertNotIn(PG,r.stdout+r.stderr)

    def test_private_files_required(self):
        (self.dir/'pg').chmod(0o644)
        self.assertEqual(self.run_seed().returncode,1);self.assertEqual(self.state.calls,[])
    def test_unknown_credential_reference_fails_before_login(self):
        p=self.workflows/'0.json';d=json.loads(p.read_text());d['nodes'][0]['credentials']['postgres']['name']='other';p.write_text(json.dumps(d))
        self.assertEqual(self.run_seed().returncode,1);self.assertEqual(self.state.calls,[])


    def test_reset_clears_pins_and_mergeable_settings_preserves_runtime_state(self):
        self.seed(); flow=self.state.flows[0]
        flow.update(pinData={'DB':[{'json':{'fake':True}}]},staticData={'lastRun':'kept'})
        flow['settings'].update(errorWorkflow='rehearsal',executionTimeout=90,saveManualExecutions=True)
        r=self.run_seed('--verify');self.assertEqual(r.returncode,1);self.assertIn('pinData',r.stderr)
        self.seed();self.assertEqual(flow['pinData'],{});self.assertEqual(flow['staticData'],{'lastRun':'kept'})
        for key in ['errorWorkflow','executionTimeout','saveManualExecutions']: self.assertNotIn(key,flow['settings'])
        self.assertEqual(self.run_seed('--verify').returncode,0)
    def test_unknown_settings_fail_with_key_without_value(self):
        self.seed();self.state.flows[0]['settings']['credentialResolverId']='PRIVATE-VALUE'
        r=self.run_seed('--verify');self.assertEqual(r.returncode,1)
        self.assertIn('credentialResolverId',r.stderr);self.assertNotIn('PRIVATE-VALUE',r.stderr)
    def test_editor_default_settings_are_allowed_but_changed_values_fail(self):
        self.seed();self.state.flows[0]['settings'].update(callerPolicy='workflowsFromSameOwner',availableInMCP=False,timeSavedMode='fixed')
        self.assertEqual(self.run_seed('--verify').returncode,0)
        self.state.flows[0]['settings']['availableInMCP']=True
        self.assertEqual(self.run_seed('--verify').returncode,1)
    def test_archived_echo_is_untouched_and_recreated(self):
        self.seed(); archived=self.state.flows[1];archived['isArchived']=True;before=copy.deepcopy(archived)
        self.seed(); self.assertEqual(archived,before);self.assertEqual(len(self.state.flows),3)
        self.assertEqual(self.run_seed('--verify').returncode,0)
    def test_other_projects_same_names_are_ignored_and_counted(self):
        self.seed()
        foreign_flow=copy.deepcopy(self.state.flows[0]);foreign_flow.update(id='foreign-w',projectId='member')
        foreign_cred=copy.deepcopy(self.state.creds[1]);foreign_cred.update(id='foreign-c',projectId='member')
        self.state.flows.append(foreign_flow);self.state.creds.append(foreign_cred)
        before=copy.deepcopy((foreign_flow,foreign_cred));r=self.run_seed()
        self.assertEqual(r.returncode,0,r.stderr);self.assertIn('2 same-named items in other projects ignored',r.stdout)
        self.assertEqual((foreign_flow,foreign_cred),before);self.assertEqual(self.run_seed('--verify').returncode,0)
        self.assertTrue(all(w['projectId']=='personal-owner' for w in self.state.flows[:2]))
    def test_digest_only_requires_no_webhook_key_or_unused_credential(self):
        (self.workflows/'1.json').unlink();self.seed()
        self.assertFalse((self.dir/'webhook-key').exists());self.assertEqual(len(self.state.creds),2)
    def test_verify_needs_no_pg_file_and_renamed_echo_still_probes(self):
        p=self.workflows/'1.json';d=json.loads(p.read_text());d['name']='Renamed echo';p.write_text(json.dumps(d))
        self.seed();(self.dir/'pg').unlink();self.state.calls.clear()
        r=self.run_seed('--verify');self.assertEqual(r.returncode,0,r.stderr)
        self.assertTrue(any(path=='/webhook/echo' for _,path,_ in self.state.calls))
    def test_invalid_echo_shape_fails_before_login(self):
        p=self.workflows/'1.json';d=json.loads(p.read_text());d['nodes'][0]['parameters'].pop('path');p.write_text(json.dumps(d))
        self.assertEqual(self.run_seed().returncode,1);self.assertEqual(self.state.calls,[])
    def test_status_diagnostics_and_local_file_errors(self):
        self.seed();self.state.echo_status=404
        r=self.run_seed('--verify');self.assertEqual(r.returncode,1);self.assertIn('HTTP 404',r.stderr)
        self.assertNotIn(PG,r.stderr)
        self.state.echo_status=403
        r=self.run_seed('--verify');self.assertIn('HTTP 403',r.stderr)
        for p in self.workflows.glob('*.json'):p.unlink()
        r=self.run_seed();self.assertNotIn('HTTP',r.stderr)
    def test_truncated_response_is_clean_error(self):
        self.state.truncated='/rest/credentials'
        r=self.run_seed();self.assertEqual(r.returncode,1);self.assertIn('ERROR:',r.stderr);self.assertNotIn('Traceback',r.stderr)
    def test_empty_or_relative_xdg_uses_absolute_home_state(self):
        from scripts.n8n_rest import state_home
        for value in ['', 'rel']:
            with patch.dict(os.environ,{'HOME':str(self.dir),'XDG_STATE_HOME':value}):
                self.assertEqual(state_home(),self.dir/'.local/state')
        with patch.dict(os.environ,{'XDG_STATE_HOME':str(self.dir)}):self.assertEqual(state_home(),self.dir)

if __name__=='__main__': unittest.main()
