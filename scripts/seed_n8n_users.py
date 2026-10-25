"""Seed demo identities through n8n's internal REST API, pinned to n8n 2.44.6.

Standard library only. Passwords enter through private files; cookies and invitation tokens
stay in memory. See design/n8n-demo/runbook-identity.md for the operational procedure.
"""
from __future__ import annotations

import argparse
import html
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request


try:
    from .n8n_rest import SeedError, Client, expect, identity, password_file, login, validate_base_url
except ImportError:  # Direct script entry point.
    from n8n_rest import SeedError, Client, expect, identity, password_file, login, validate_base_url


def personas(realm_path, owner):
    try:
        realm = json.loads(Path(realm_path).read_text())
        people = [u for u in realm['users'] if u.get('attributes', {}).get('world') == ['cz']]
        for user in people:
            if not all(isinstance(user.get(k), str) and user[k] for k in ('username', 'email', 'firstName', 'lastName')):
                raise ValueError
        if len({p['email'].lower() for p in people}) != len(people):
            raise ValueError
        owners = [p for p in people if p['username'] == owner]
        if len(owners) != 1:
            raise ValueError
        return owners[0], [p for p in people if p is not owners[0]]
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        raise SeedError('realm must contain one selected Czech owner and valid, distinct Czech personas') from None


def mail_read(mode, path, context):
    if mode != 'proxy':
        return Client(mode).call(path, envelope=False)
    try:
        result = subprocess.run(['kubectl', '--context', context, 'get', '--raw',
            '/api/v1/namespaces/middleware/services/mailpit-http:80/proxy' + path],
            capture_output=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise SeedError('Mailpit service proxy failed (output withheld)') from None
    if result.returncode:
        raise SeedError('Mailpit service proxy failed (output withheld)')
    try:
        return json.loads(result.stdout)
    except ValueError:
        raise SeedError('Mailpit service proxy returned invalid JSON (output withheld)') from None


def signup_token(text):
    match = re.search(r'/signup\?token=([A-Za-z0-9._-]+)', html.unescape(text))
    return match.group(1) if match else None


def mail_messages(mode, person, context):
    query = urllib.parse.urlencode({'query': 'to:' + person['email']})
    result = mail_read(mode, '/api/v1/search?' + query, context)
    expect(isinstance(result, dict) and isinstance(result.get('messages'), list), 'Mailpit search')
    for message in result['messages']:
        expect(isinstance(message, dict) and isinstance(message.get('ID'), str), 'Mailpit search')
    return result['messages']


def invitation_token(mode, person, context, old_ids):
    deadline = time.monotonic() + 30
    while True:
        messages = [m for m in mail_messages(mode, person, context) if m['ID'] not in old_ids]
        # Ignore mail already present before this invitation, including expired tokens.
        if messages:
            newest = messages[0]
            message = mail_read(mode, '/api/v1/message/' + urllib.parse.quote(newest['ID'], safe=''), context)
            expect(isinstance(message, dict) and isinstance(message.get('Text'), str)
                   and isinstance(message.get('HTML'), str), 'Mailpit message')
            token = signup_token(message['Text'] + '\n' + message['HTML'])
            if token:
                return token
        if time.monotonic() >= deadline:
            raise SeedError('Mailpit: no invitation link arrived within 30 seconds')
        time.sleep(1)


def run(args):
    owner, members = personas(args.realm, args.owner)
    people = [owner] + ([] if args.mailpit == 'none' else members)
    if args.dry_run:
        print(f'owner {owner["username"]}: claim if unclaimed, otherwise authenticate')
        for person in people[1:]:
            print(f'member {person["username"]}: invite if missing; pending requires --reinvite')
        if args.mailpit == 'none':
            print('members deferred until Mailpit is ready')
        return
    owner_password = password_file(args.owner_password_file)
    member_password = password_file(args.member_password_file) if people[1:] else None
    client = Client(args.url)
    settings = client.call('/rest/settings')
    expect(isinstance(settings, dict) and isinstance(settings.get('userManagement'), dict)
           and type(settings['userManagement'].get('showSetupOnFirstLoad')) is bool, '/rest/settings')
    fresh = settings['userManagement']['showSetupOnFirstLoad']
    if args.verify:
        if fresh:
            raise SeedError('owner is unclaimed; --verify never creates accounts')
        for person in people:
            role = 'global:owner' if person is owner else 'global:member'
            login(args.url, person, owner_password if person is owner else member_password, role)
            print(f'{person["username"]} · {person["email"]} · {role} · ✓')
        return
    if fresh:
        data = client.call('/rest/owner/setup', {k: owner[k] for k in ('email', 'firstName', 'lastName')}
                           | {'password': owner_password})
        identity(data, owner, 'global:owner', '/rest/owner/setup')
        client.require_cookie()
        # Confirm the setup page is closed before considering owner creation successful.
        settings = client.call('/rest/settings')
        expect(isinstance(settings, dict) and isinstance(settings.get('userManagement'), dict)
               and settings['userManagement'].get('showSetupOnFirstLoad') is False, '/rest/settings')
        print(f'owner {owner["username"]}: created')
    else:
        client = login(args.url, owner, owner_password, 'global:owner')
        print(f'owner {owner["username"]}: present')
    if args.mailpit == 'none':
        print('members deferred until Mailpit is ready')
        return
    users = client.call('/rest/users')
    expect(isinstance(users, dict) and type(users.get('count')) is int
           and isinstance(users.get('items'), list), '/rest/users')
    # Fail instead of mistaking a truncated roster for absent users and issuing duplicates.
    expect(users['count'] == len(users['items']), '/rest/users (incomplete roster)')
    for user in users['items']:
        expect(isinstance(user, dict) and isinstance(user.get('id'), str)
               and isinstance(user.get('email'), str) and type(user.get('isPending')) is bool
               and isinstance(user.get('role'), str), '/rest/users')
    existing = {u['email'].lower(): u for u in users['items']}
    pending = False
    for person in members:
        user = existing.get(person['email'].lower())
        if user:
            identity(user, person, 'global:member', '/rest/users')
            if not user['isPending']:
                print(f'member {person["username"]}: present')
                continue
            if not args.reinvite:
                print(f'member {person["username"]}: pending (use --reinvite)')
                pending = True
                continue
        old_ids = {m['ID'] for m in mail_messages(args.mailpit, person, args.context)}
        invitations = client.call('/rest/invitations', [{'email': person['email'], 'role': 'global:member'}])
        expect(isinstance(invitations, list) and len(invitations) == 1
               and isinstance(invitations[0], dict), '/rest/invitations')
        invitation = invitations[0]
        invited = invitation.get('user')
        expect(isinstance(invited, dict) and invited.get('email') == person['email']
               and isinstance(invited.get('id'), str) and type(invited.get('emailSent')) is bool
               and invitation.get('error') == '', '/rest/invitations')
        if invited['emailSent']:
            token = invitation_token(args.mailpit, person, args.context, old_ids)
        else:
            link = invited.get('inviteAcceptUrl')
            expect(isinstance(link, str), '/rest/invitations (no emailed or copyable link)')
            token = signup_token(link)
            expect(token is not None, '/rest/invitations (invalid signup link)')
        accepted = Client(args.url).call('/rest/invitations/accept',
            {k: person[k] for k in ('firstName', 'lastName')} | {'token': token, 'password': member_password})
        identity(accepted, person, 'global:member', '/rest/invitations/accept')
        login(args.url, person, member_password, 'global:member')
        print(f'member {person["username"]}: invited → accepted')
    if pending:
        raise SeedError('pending personas remain; no invitation resent without --reinvite')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--owner', default='marketa')
    olymp = Path(os.environ.get('OLYMP_DIR', Path(__file__).resolve().parents[2] / 'olymp'))
    parser.add_argument('--realm', default=str(olymp / 'platform/auth/keycloak/overlays/hartland/realm/kantheon.json'))
    parser.add_argument('--owner-password-file')
    parser.add_argument('--member-password-file')
    parser.add_argument('--mailpit', default='proxy', help='proxy, API base URL, or none (owner only)')
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--verify', action='store_true')
    modes.add_argument('--dry-run', action='store_true')
    parser.add_argument('--reinvite', action='store_true')
    args = parser.parse_args(argv)
    args.url = os.environ.get('N8N_URL', 'https://n8n.hartland.collite.cz')
    args.context = os.environ.get('KUBE_CONTEXT', 'hartland')
    for url in [args.url] + ([] if args.mailpit in ('proxy', 'none') else [args.mailpit]):
        try:
            validate_base_url(url)
        except SeedError as error:
            parser.error(str(error))
    try:
        personas(args.realm, args.owner)
    except SeedError as error:
        parser.error(str(error))
    try:
        run(args)
        return 0
    except (SeedError, OSError, UnicodeError) as error:
        # Only SeedError has a deliberately safe message; raw OS errors can include URLs.
        print('ERROR: ' + (str(error) if isinstance(error, SeedError) else 'local file or encoding error'), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
