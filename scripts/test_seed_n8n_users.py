"""N8 S2.2: offline HTTP fakes for n8n 2.44.6 and Mailpit v1.

Shapes checked against n8n@2.44.6 controllers/{owner,auth,users,invitation}.controller.ts,
services/user.service.ts (toPublic/sendEmails), and Mailpit's published Swagger API.
No real Azure, Kubernetes, mail, or external HTTP requests.
"""
from __future__ import annotations

import contextlib
import http.server
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
import unittest.mock
import urllib.parse

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / 'scripts/seed_n8n_users.py'
SHELL = ROOT / 'scripts/seed-n8n-users.sh'
OWNER_PASSWORD = 'Owner-Private9!'
MEMBER_PASSWORD = 'Member-Private8!'
PEOPLE = [
    ('marketa', 'marketa@hartland.example', 'Markéta', 'Nováková', 'cz'),
    ('tomas', 'cfo-cz@hartland.example', 'Tomáš', 'Horák', 'cz'),
    ('petr', 'petr@hartland.example', 'Petr', 'Svoboda', 'cz'),
    ('maya', 'maya@hartland.example', 'Maya', 'Smith', 'us'),
    ('john', 'john@hartland.example', 'John', 'Smith', 'us'),
]


class State:
    def __init__(self):
        self.users = {}
        self.tokens = {}
        self.sessions = {}
        self.messages = []
        self.writes = []
        self.mail_enabled = True
        self.broken = None
        self.bad_role = False
        self.no_cookie = False
        self.html_only = False
        self.requests = []

    def user(self, email, role='global:member', pending=False):
        user = dict(id=str(len(self.users) + 1), email=email, role=role, isPending=pending)
        self.users[email] = user
        return user


def handler_for(state, mail=False):
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def answer(self, data, status=200, cookie=None, envelope=True):
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            if cookie and not state.no_cookie:
                self.send_header('Set-Cookie', f'n8n-auth={cookie}; Path=/; HttpOnly')
            self.end_headers()
            self.wfile.write(json.dumps({'data': data} if envelope else data).encode())

        def do_GET(self):
            state.requests.append(self.path)
            parsed = urllib.parse.urlsplit(self.path)
            if mail:
                if parsed.path == '/api/v1/search':
                    query = urllib.parse.parse_qs(parsed.query)['query'][0]
                    messages = [{'ID': m['ID']} for m in state.messages if query == 'to:' + m['To']]
                    return self.answer({'messages': messages}, envelope=False)
                if parsed.path.startswith('/api/v1/message/'):
                    mid = parsed.path.rsplit('/', 1)[1]
                    msg = next(m for m in state.messages if m['ID'] == mid)
                    return self.answer(msg, envelope=False)
                return self.answer({}, 404)
            if state.broken == self.path:
                return self.answer({'changed': True}, envelope=False)
            if self.path == '/rest/settings':
                return self.answer({'userManagement': {'showSetupOnFirstLoad': not state.users}})
            cookie = self.headers.get('Cookie', '').removeprefix('n8n-auth=')
            email = state.sessions.get(cookie)
            if not email:
                return self.answer({'error': 'not authenticated'}, 401)
            if self.path == '/rest/login':
                user = dict(state.users[email])
                if state.bad_role:
                    user['role'] = 'global:admin'
                return self.answer(user)
            if parsed.path == '/rest/users':
                return self.answer({'count': len(state.users), 'items': list(state.users.values())})
            return self.answer({}, 404)

        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            if self.path == '/api/v1/send' and mail:
                state.messages.append(payload)
                return self.answer({}, envelope=False)
            state.writes.append(self.path)
            if state.broken == self.path:
                # A hostile error echoes the submitted credentials; none may be logged.
                return self.answer(payload, 422, envelope=False)
            if self.path == '/rest/owner/setup':
                if state.users:
                    return self.answer({}, 400)
                user = state.user(payload['email'], 'global:owner')
                state.sessions['session-1'] = user['email']
                return self.answer(user, cookie='session-1')
            if self.path == '/rest/login':
                email = payload['emailOrLdapLoginId']
                user = state.users.get(email)
                password = OWNER_PASSWORD if user and user['role'] == 'global:owner' else MEMBER_PASSWORD
                if not user or user['isPending'] or payload['password'] != password:
                    return self.answer(payload, 401, envelope=False)
                session = 'session-' + user['id']
                state.sessions[session] = email
                return self.answer(user, cookie=session)
            cookie = self.headers.get('Cookie', '').removeprefix('n8n-auth=')
            if self.path == '/rest/invitations':
                if state.sessions.get(cookie) != PEOPLE[0][1]:
                    return self.answer({}, 403)
                invitation = payload[0]
                email = invitation['email']
                user = state.users.get(email) or state.user(email, invitation['role'], True)
                token = 'eyJ.fake.' + user['id']
                state.tokens[token] = email
                link = 'https://n8n.test/signup?token=' + token
                invited = {**user, 'emailSent': state.mail_enabled}
                if state.mail_enabled:
                    # Feed the independent Mailpit fake through HTTP, like delivery.
                    import urllib.request
                    message = dict(ID=str(len(state.messages) + 1), To=email,
                                   Text='' if state.html_only else link,
                                   HTML=f'<a href="{link}">Accept invite</a>')
                    request = urllib.request.Request(state.mail_url + '/api/v1/send',
                                                     json.dumps(message).encode(),
                                                     {'Content-Type': 'application/json'})
                    with urllib.request.urlopen(request) as response:
                        response.read()
                else:
                    invited['inviteAcceptUrl'] = link
                return self.answer([{'user': invited, 'error': ''}])
            if self.path == '/rest/invitations/accept':
                email = state.tokens.pop(payload['token'])
                state.users[email]['isPending'] = False
                state.users[email]['firstName'] = payload['firstName']
                state.users[email]['lastName'] = payload['lastName']
                return self.answer(state.users[email])
            return self.answer({}, 404)
    return Handler


@contextlib.contextmanager
def server(state, mail=False):
    httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler_for(state, mail))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{httpd.server_port}'
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join()


class SeedTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='n8n-test-')
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.realm = self.path / 'realm.json'
        self.realm.write_text(json.dumps({'users': [dict(username=u, email=e, firstName=f,
            lastName=l, attributes={'world': [w]}) for u, e, f, l, w in PEOPLE]}))
        for name, password in [('owner', OWNER_PASSWORD), ('member', MEMBER_PASSWORD)]:
            file = self.path / name
            file.write_text(password)
            file.chmod(0o600)
        self.state = State()
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.mail = self.stack.enter_context(server(self.state, True))
        self.state.mail_url = self.mail
        self.url = self.stack.enter_context(server(self.state))

    def run_seed(self, *flags, shell=False, vault=False):
        env = {**os.environ, 'N8N_URL': self.url, 'TMPDIR': str(self.path)}
        args = (['bash', str(SHELL)] if shell else [sys.executable, '-B', str(PYTHON)])
        args += ['--realm', str(self.realm), '--mailpit', self.mail]
        if not vault:
            args += ['--owner-password-file', str(self.path / 'owner'),
                     '--member-password-file', str(self.path / 'member')]
        result = subprocess.run(args + list(flags), capture_output=True, text=True, env=env, timeout=40)
        output = result.stdout + result.stderr
        for secret in (OWNER_PASSWORD, MEMBER_PASSWORD, *self.state.tokens, 'eyJ.fake.'):
            self.assertNotIn(secret, output)
        return result

    def seed(self):
        result = self.run_seed()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_fresh_then_idempotent(self):
        self.seed()
        self.assertEqual(set(self.state.users), {p[1] for p in PEOPLE[:3]})
        self.assertEqual(self.state.writes.count('/rest/owner/setup'), 1)
        self.assertEqual(self.state.writes.count('/rest/invitations'), 2)
        self.assertEqual(self.state.writes.count('/rest/invitations/accept'), 2)
        self.assertEqual(self.state.users[PEOPLE[1][1]]['firstName'], 'Tomáš')
        self.state.writes.clear()
        result = self.run_seed()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.count('present'), 3)
        self.assertEqual(set(self.state.writes), {'/rest/login'})

    def test_pending_requires_reinvite(self):
        self.seed()
        self.state.users[PEOPLE[1][1]]['isPending'] = True
        self.state.writes.clear()
        result = self.run_seed()
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn('pending', result.stdout + result.stderr)
        self.assertNotIn('/rest/invitations', self.state.writes)
        result = self.run_seed('--reinvite')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.state.users[PEOPLE[1][1]]['isPending'])

    def test_verify_success_and_wrong_password_or_role(self):
        self.seed()
        self.state.writes.clear()
        result = self.run_seed('--verify')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.count('✓'), 3)
        self.assertEqual(set(self.state.writes), {'/rest/login'})
        (self.path / 'member').write_text('Wrong-Password7')
        result = self.run_seed('--verify')
        self.assertEqual(result.returncode, 1)
        self.assertIn('HTTP 401', result.stderr)
        self.assertNotIn('Wrong-Password7', result.stderr)
        self.state.bad_role = True
        result = self.run_seed('--verify')
        self.assertEqual(result.returncode, 1)

    def test_verify_fresh_does_not_claim_owner(self):
        result = self.run_seed('--verify')
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.state.writes, [])

    def test_unknown_shape_names_status(self):
        self.state.broken = '/rest/settings'
        result = self.run_seed()
        self.assertEqual(result.returncode, 1)
        self.assertIn('HTTP 200', result.stderr)
        self.assertIn('changed', result.stderr)

    def test_sensitive_error_body_is_never_printed(self):
        self.state.broken = '/rest/owner/setup'
        result = self.run_seed()
        self.assertEqual(result.returncode, 1)
        self.assertIn('HTTP 422', result.stderr)
        self.assertNotIn('password', result.stderr.lower())

    def test_dry_run_no_http_or_vault(self):
        result = self.run_seed('--dry-run', shell=True, vault=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('owner marketa', result.stdout)
        self.assertNotIn('maya', result.stdout)
        self.assertEqual(self.state.writes, [])
        self.assertEqual(self.state.requests, [])

    def test_none_claims_only_owner(self):
        result = self.run_seed('--mailpit', 'none', shell=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(set(self.state.users), {PEOPLE[0][1]})
        self.assertIn('deferred', result.stdout)

    def test_mailpit_html_and_proxy(self):
        self.state.html_only = True
        self.seed()
        self.state.users[PEOPLE[1][1]]['isPending'] = True
        bin_dir = self.path / 'bin'
        bin_dir.mkdir()
        proxy = bin_dir / 'kubectl'
        proxy.write_text('#!/usr/bin/env python3\nimport sys, urllib.request\n'
                         f'url = {self.mail!r} + sys.argv[-1].split("/proxy", 1)[1]\n'
                         'with urllib.request.urlopen(url) as response: sys.stdout.buffer.write(response.read())\n')
        proxy.chmod(0o755)
        with unittest.mock.patch.dict(os.environ, {'PATH': str(bin_dir) + ':' + os.environ['PATH']}):
            result = self.run_seed('--reinvite', '--mailpit', 'proxy')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_owner_session_cookie_required(self):
        self.state.no_cookie = True
        result = self.run_seed()
        self.assertEqual(result.returncode, 1)
        self.assertNotIn('/rest/invitations', self.state.writes)

    def test_usage_and_invalid_owner_do_not_write(self):
        for flags in [('--bogus',), ('--owner', 'maya')]:
            result = self.run_seed(*flags)
            self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(self.state.writes, [])


if __name__ == '__main__':
    unittest.main()
