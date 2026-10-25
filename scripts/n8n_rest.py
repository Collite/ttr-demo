"""Shared n8n 2.44.6 REST session and private-file helpers; no response-body leaks."""
from __future__ import annotations
import http.cookiejar
import json
from pathlib import Path
import re
import stat
import urllib.error
import urllib.request

class SeedError(Exception):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    # Never forward an authentication body to a redirected destination.
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Client:
    def __init__(self, base):
        self.base = base.rstrip('/')
        self.cookies = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(NoRedirect(), urllib.request.HTTPCookieProcessor(self.cookies))

    def call(self, path, payload=None, *, envelope=True, method=None):
        # All /rest bodies may carry credentials, cookies, or live invitation links.
        # Only settings is safe to excerpt when its shape changes.
        safe_excerpt = path == '/rest/settings'
        request = urllib.request.Request(self.base + path,
            data=None if payload is None else json.dumps(payload).encode(),
            headers={'Content-Type': 'application/json', 'Accept': 'application/json'}, method=method)
        try:
            with self.opener.open(request, timeout=30) as response:
                status, raw = response.status, response.read()
        except urllib.error.HTTPError as error:
            status, raw = error.code, error.read()
        except (OSError, urllib.error.URLError):
            raise SeedError(f'{path.split("?")[0]}: connection failed') from None
        excerpt = ': ' + raw[:200].decode('utf-8', 'replace') if safe_excerpt else ' (body withheld)'
        if status != 200:
            raise SeedError(f'{path.split("?")[0]}: HTTP {status}{excerpt}')
        try:
            data = json.loads(raw)
        except (ValueError, UnicodeError):
            raise SeedError(f'{path.split("?")[0]}: HTTP {status}, invalid JSON{excerpt}') from None
        if envelope:
            if not isinstance(data, dict) or 'data' not in data:
                raise SeedError(f'{path.split("?")[0]}: HTTP {status}, expected data envelope{excerpt}')
            data = data['data']
        return data

    def require_cookie(self):
        if not any(cookie.name == 'n8n-auth' for cookie in self.cookies):
            raise SeedError('HTTP 200: authentication response missing n8n-auth cookie')


def expect(condition, endpoint):
    if not condition:
        raise SeedError(f'{endpoint}: HTTP 200, unexpected n8n 2.44.6 response shape (body withheld)')


def identity(data, person, role, endpoint):
    expect(isinstance(data, dict) and data.get('email') == person['email']
           and data.get('role') == role and isinstance(data.get('id'), str), endpoint)


def private_file(path):
    if not path:
        raise SeedError('password file required (use the shell wrapper for vault reads)')
    file = Path(path)
    try:
        mode = file.stat().st_mode
        if not stat.S_ISREG(mode) or mode & 0o077:
            raise SeedError('password files must be regular files readable only by their owner (chmod 600)')
        value = file.read_text().rstrip('\r\n')
    except OSError:
        raise SeedError('cannot read password file') from None
    if not value:
        raise SeedError('password file is empty')
    return value


def password_file(path):
    value = private_file(path)
    if len(value) < 8 or not re.search('[A-Z]', value) or not re.search('[0-9]', value):
        raise SeedError('password must have at least 8 characters, an uppercase letter and a digit')
    if value == 'Hartland!2026':
        raise SeedError('the public realm demo password cannot be used for n8n')
    return value


def login(url, person, password, role):
    client = Client(url)
    data = client.call('/rest/login', {'emailOrLdapLoginId': person['email'], 'password': password})
    identity(data, person, role, '/rest/login')
    client.require_cookie()
    identity(client.call('/rest/login'), person, role, '/rest/login')
    return client

