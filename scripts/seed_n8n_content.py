"""Upsert/rehearse the Hartland demo content using n8n's pinned 2.44.6 REST API."""
from __future__ import annotations
import argparse
import copy
import json
import os
from pathlib import Path
import secrets
import sys
import urllib.error
import urllib.parse
import urllib.request
try:
    from .n8n_rest import Client, NoRedirect, SeedError, expect, login, password_file, private_file
except ImportError:
    from n8n_rest import Client, NoRedirect, SeedError, expect, login, password_file, private_file

CREDENTIAL_TYPES = {'hartland-cz-pg': 'postgres', 'mailpit-smtp': 'smtp', 'webhook-echo-key': 'httpHeaderAuth'}
OWNER = {'email': 'marketa@hartland.example'}


def documents(directory):
    try:
        docs = [json.loads(p.read_text()) for p in sorted(Path(directory).glob('*.json'))]
    except (ValueError, OSError, UnicodeError):
        raise SeedError('cannot read workflow JSON files (contents withheld)') from None
    expect(bool(docs), 'workflow files (empty directory)')
    names = set()
    for doc in docs:
        expect(isinstance(doc, dict) and isinstance(doc.get('name'), str) and bool(doc['name'])
               and type(doc.get('active')) is bool and isinstance(doc.get('nodes'), list) and bool(doc['nodes'])
               and isinstance(doc.get('connections'), dict) and isinstance(doc.get('settings'), dict), 'workflow file')
        expect(doc['name'] not in names, 'duplicate workflow file name'); names.add(doc['name'])
        for node in doc['nodes']:
            expect(isinstance(node, dict) and all(k in node for k in ['name','type','typeVersion','position','parameters']), 'workflow node')
            for kind, ref in node.get('credentials', {}).items():
                expect(isinstance(ref, dict) and CREDENTIAL_TYPES.get(ref.get('name')) == kind, 'workflow credential reference')
    return docs


def by_name(items, endpoint):
    expect(isinstance(items, list), endpoint)
    result = {}
    for item in items:
        expect(isinstance(item, dict) and isinstance(item.get('id'), str)
               and isinstance(item.get('name'), str), endpoint)
        # Refuse ambiguous matches, including repeated IDs from a drifting paginated response.
        expect(item['name'] not in result, endpoint + ' (duplicate name)')
        result[item['name']] = item
    return result


def workflow_roster(client):
    items, skip = [], 0
    while True:
        result = client.call('/rest/workflows?' + urllib.parse.urlencode({'take': 250, 'skip': skip}), envelope=False)
        expect(isinstance(result, dict) and type(result.get('count')) is int
               and isinstance(result.get('data'), list), '/rest/workflows')
        count, batch = result['count'], result['data']
        items.extend(batch)
        expect(len(items) <= count, '/rest/workflows (inconsistent count)')
        if len(items) == count: break
        expect(bool(batch), '/rest/workflows (incomplete roster)')
        skip = len(items)
    return by_name(items, '/rest/workflows')


def credential_data(pg_password, webhook_key):
    return {'hartland-cz-pg': {'host': 'hartland-pg-rw.data.svc.cluster.local', 'port': 5432,
            'database': 'hartland_cz', 'user': 'hartland_cz_readonly', 'password': pg_password, 'ssl': 'disable'},
            'mailpit-smtp': {'host': 'mailpit-smtp.middleware', 'port': 25, 'secure': False, 'disableStartTls': True},
            'webhook-echo-key': {'name': 'X-Demo-Key', 'value': webhook_key}}


def mapped(doc, creds):
    payload = {key: copy.deepcopy(doc[key]) for key in ['name', 'nodes', 'connections', 'settings']}
    for node in payload['nodes']:
        for kind, ref in node.get('credentials', {}).items():
            name = ref['name']; c = creds.get(name)
            expect(c is not None and c.get('type') == kind, 'missing or mismatched credential')
            node['credentials'][kind] = {'name': name, 'id': c['id']}
    return payload


def check_flow(flow, doc, creds):
    expect(isinstance(flow, dict) and isinstance(flow.get('id'), str)
           and isinstance(flow.get('versionId'), str), 'workflow detail')
    expect(flow.get('active') is doc['active'] and
           (not doc['active'] or flow.get('activeVersionId') == flow['versionId']), 'workflow publication (draft not served)')
    # Compare portable content, ignoring editor-inserted optional fields on nodes.
    expected = mapped(doc, creds)
    expect(flow.get('name') == expected['name'] and flow.get('connections') == expected['connections'], 'workflow content')
    expect(isinstance(flow.get('nodes'), list) and len(flow['nodes']) == len(expected['nodes']), 'workflow nodes')
    actual = {n['name']: n for n in flow['nodes']}
    for node in expected['nodes']:
        expect(node['name'] in actual and all(actual[node['name']].get(k) == v for k,v in node.items()), 'workflow node content')
    expect(all(flow.get('settings', {}).get(k) == v for k,v in expected['settings'].items()), 'workflow settings')


def webhook_key_file(path, *, create):
    file = Path(path)
    if not file.exists():
        if not create:
            raise SeedError('original webhook key file required; existing credentials are never rotated')
        file.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        try:
            descriptor = os.open(file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass  # Another invocation won; read and validate its private file.
        else:
            with os.fdopen(descriptor, 'w') as output:
                output.write(secrets.token_hex(16) + '\n')
                output.flush(); os.fsync(output.fileno())
    # Reuse the private-file permission check; random hex needn't satisfy n8n login-password rules.
    import stat
    mode = file.stat().st_mode
    if not stat.S_ISREG(mode) or mode & 0o077:
        raise SeedError('webhook key must be a private regular file (chmod 600)')
    value = file.read_text().strip()
    if len(value) != 32 or any(c not in '0123456789abcdef' for c in value):
        raise SeedError('webhook key file must contain the original 32 lowercase hex characters')
    return value


def verify_echo(creds, url, key):
    c = creds.get('webhook-echo-key')
    expect(c is not None and c.get('type') == 'httpHeaderAuth', 'webhook credential')
    probe = {'ahoj': 'světe', 'probe': secrets.token_hex(8)}
    target = url.rstrip('/') + '/webhook/echo'
    unauthorized = urllib.request.Request(target, json.dumps(probe).encode(), headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.build_opener(NoRedirect()).open(unauthorized, timeout=30):
            raise SeedError('webhook accepted a request without the demo key')
    except urllib.error.HTTPError as error:
        expect(error.code in (401, 403), 'webhook missing-key denial')
    except (OSError, urllib.error.URLError):
        raise SeedError('webhook denial probe failed (response withheld)') from None
    request = urllib.request.Request(target, json.dumps(probe).encode(),
              headers={'Content-Type': 'application/json', 'X-Demo-Key': key})
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=30) as response:
            expect(response.status == 200 and json.loads(response.read()) == probe, 'webhook echo')
    except (OSError, urllib.error.URLError, ValueError):
        raise SeedError('webhook echo failed (response withheld)') from None


def run(args):
    docs = documents(args.dir)
    owner_password = password_file(args.owner_password_file)
    pg_password = private_file(args.pg_ro_password_file)
    client = login(args.url, OWNER, owner_password, 'global:owner')
    creds = by_name(client.call('/rest/credentials'), '/rest/credentials')
    flows = workflow_roster(client)
    # Detect ambiguity and schema mismatches before performing any content mutation.
    for name, kind in CREDENTIAL_TYPES.items():
        if name in creds: expect(creds[name].get('type') == kind, 'existing credential type')
    key = webhook_key_file(args.webhook_key_file, create=not args.verify and 'webhook-echo-key' not in creds)
    if args.verify:
        for doc in docs:
            expect(doc['name'] in flows, 'missing workflow')
            flow = client.call('/rest/workflows/' + urllib.parse.quote(flows[doc['name']]['id'], safe=''))
            check_flow(flow, doc, creds)
        if any(d['name'] == 'Webhook echo (test)' for d in docs): verify_echo(creds, args.url, key)
        print(f'{len(docs)} workflows verified; publication/content/credentials match' + ('; webhook echo ✓' if any(d['name']=='Webhook echo (test)' for d in docs) else ''))
        return
    for name, data in credential_data(pg_password, key).items():
        if name == 'webhook-echo-key' and name in creds:
            # Preserve the encrypted existing key; never rotate it on reset/rehearsal.
            continue
        payload = {'name': name, 'type': CREDENTIAL_TYPES[name], 'data': data}
        if name in creds:
            c = client.call('/rest/credentials/' + urllib.parse.quote(creds[name]['id'], safe=''), payload, method='PATCH')
        else: c = client.call('/rest/credentials', payload)
        expect(isinstance(c, dict) and isinstance(c.get('id'), str) and c.get('name') == name
               and c.get('type') == CREDENTIAL_TYPES[name], 'credential upsert')
        creds[name] = c
        print('credential ready: ' + name)
    for doc in docs:
        payload = mapped(doc, creds)
        if doc['name'] in flows:
            wid = urllib.parse.quote(flows[doc['name']]['id'], safe='')
            before = client.call('/rest/workflows/' + wid)
            expect(isinstance(before.get('checksum'), str), 'workflow checksum')
            flow = client.call('/rest/workflows/' + wid, {**payload, 'expectedChecksum': before['checksum']}, method='PATCH')
        else: flow = client.call('/rest/workflows', payload)
        expect(isinstance(flow, dict) and isinstance(flow.get('id'), str) and isinstance(flow.get('versionId'), str)
               and isinstance(flow.get('checksum'), str), 'workflow upsert')
        wid = urllib.parse.quote(flow['id'], safe='')
        if doc['active']:
            flow = client.call('/rest/workflows/' + wid + '/activate', {'versionId': flow['versionId'],
                'name': 'Hartland demo seed', 'description': 'Restore reviewed demo content', 'expectedChecksum': flow['checksum']})
        elif flow.get('active'):
            flow = client.call('/rest/workflows/' + wid + '/deactivate', {'expectedChecksum': flow['checksum']})
        check_flow(flow, doc, creds)
        print('workflow ready: ' + doc['name'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dir', default=str(Path(__file__).resolve().parents[1]/'n8n/demo'))
    state_home = Path(os.environ.get('XDG_STATE_HOME', Path.home()/'.local/state'))
    parser.add_argument('--webhook-key-file', default=str(state_home/'hartland-n8n/webhook-echo-key'),
                        help='private persistent key file; generated once, never rotated automatically')
    parser.add_argument('--owner-password-file'); parser.add_argument('--pg-ro-password-file')
    parser.add_argument('--verify', action='store_true'); args = parser.parse_args()
    args.url = os.environ.get('N8N_URL', 'https://n8n.hartland.collite.cz')
    try:
        base = urllib.parse.urlsplit(args.url)
        if not (base.scheme in ['http','https'] and base.hostname and not (base.username or base.password or base.query or base.fragment)):
            parser.error('N8N_URL must be an HTTP(S) base without credentials, query or fragment')
        base.port
    except ValueError: parser.error('invalid N8N_URL')
    try:
        run(args); return 0
    except (SeedError, OSError, UnicodeError, KeyError, TypeError, ValueError, AttributeError) as error:
        print('ERROR: '+(str(error) if isinstance(error, SeedError) else 'unexpected response or local file error (details withheld)'),file=sys.stderr)
        return 1
if __name__=='__main__': sys.exit(main())
