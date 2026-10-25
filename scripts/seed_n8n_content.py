"""Upsert/rehearse the Hartland demo content using n8n's pinned 2.44.6 REST API."""
from __future__ import annotations
import argparse
import http.client
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
    from .n8n_rest import NoRedirect, SeedError, expect, login, password_file, private_file, _private_regular_file, state_home, validate_base_url
except ImportError:
    from n8n_rest import NoRedirect, SeedError, expect, login, password_file, private_file, _private_regular_file, state_home, validate_base_url

CREDENTIAL_TYPES = {'hartland-cz-pg': 'postgres', 'mailpit-smtp': 'smtp', 'webhook-echo-key': 'httpHeaderAuth'}
OWNER = {'email': 'marketa@hartland.example'}
# n8n@2.44.6 workflow-helpers.removeDefaultValues; chart 1.24.43/olymp do not
# override EXECUTIONS_TIMEOUT, whose upstream default is -1.
DEFAULTABLE_SETTINGS = {'errorWorkflow', 'timezone', 'saveDataErrorExecution',
    'saveDataSuccessExecution', 'saveManualExecutions', 'saveExecutionProgress'}
# WorkflowSettings.vue initializes these on opening the modal (894-936).
# User-selected callerIds, resolver/redaction/telemetry/time-saved values are NOT ignored.
EDITOR_DEFAULT_SETTINGS = {'callerPolicy': 'workflowsFromSameOwner',
    'availableInMCP': False, 'timeSavedMode': 'fixed'}


def require(condition, message):
    if not condition:
        raise SeedError(message)


def referenced_credentials(docs):
    return {ref['name'] for doc in docs for node in doc['nodes']
            for ref in node.get('credentials', {}).values()}


def echo_paths(docs):
    paths = []
    for doc in docs:
        uses_key = any(ref.get('name') == 'webhook-echo-key'
                       for node in doc['nodes'] for ref in node.get('credentials', {}).values())
        nodes = [n for n in doc['nodes'] if n['type'] == 'n8n-nodes-base.webhook'
                 and n['parameters'].get('authentication') == 'headerAuth'
                 and n.get('credentials', {}).get('httpHeaderAuth', {}).get('name') == 'webhook-echo-key']
        meta = doc.get('meta')
        demo = meta.get('ttrDemo') if isinstance(meta, dict) else None
        marked_echo = isinstance(demo, dict) and demo.get('probe') == 'webhook-echo'
        if uses_key or marked_echo:
            require(bool(nodes), 'workflow file echo example lacks a keyed webhook')
        for node in nodes:
            path = node['parameters'].get('path')
            require(isinstance(path, str) and bool(path) and not path.startswith('/')
                   and all(part not in ('', '.', '..') for part in path.split('/'))
                   and node['parameters'].get('httpMethod') == 'POST', 'workflow file echo webhook path/method')
            paths.append(path)
    return paths



def documents(directory):
    try:
        docs = [json.loads(p.read_text()) for p in sorted(Path(directory).glob('*.json'))]
    except (ValueError, OSError, UnicodeError):
        raise SeedError('cannot read workflow JSON files (contents withheld)') from None
    require(bool(docs), 'workflow files (empty directory)')
    names = set()
    for doc in docs:
        require(isinstance(doc, dict) and isinstance(doc.get('name'), str) and bool(doc['name'])
               and type(doc.get('active')) is bool and isinstance(doc.get('nodes'), list) and bool(doc['nodes'])
               and isinstance(doc.get('connections'), dict) and isinstance(doc.get('settings'), dict), 'workflow file')
        require(doc['name'] not in names, 'duplicate workflow file name'); names.add(doc['name'])
        for node in doc['nodes']:
            require(isinstance(node, dict) and all(k in node for k in ['name','type','typeVersion','position','parameters']), 'workflow node')
            for kind, ref in node.get('credentials', {}).items():
                require(isinstance(ref, dict) and CREDENTIAL_TYPES.get(ref.get('name')) == kind, 'workflow credential reference')
    echo_paths(docs)
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


def workflow_roster(client, filters):
    items, skip = [], 0
    while True:
        result = client.call('/rest/workflows?' + urllib.parse.urlencode({'take': 100, 'skip': skip, 'filter': json.dumps(filters)}), envelope=False)
        expect(isinstance(result, dict) and type(result.get('count')) is int
               and isinstance(result.get('data'), list), '/rest/workflows')
        count, batch = result['count'], result['data']
        items.extend(batch)
        expect(len(items) <= count, '/rest/workflows (inconsistent count)')
        if len(items) == count: break
        expect(bool(batch), '/rest/workflows (incomplete roster)')
        skip = len(items)
    return items


def credential_data(pg_password, webhook_key):
    return {'hartland-cz-pg': {'host': 'hartland-pg-rw.data.svc.cluster.local', 'port': 5432,
            'database': 'hartland_cz', 'user': 'hartland_cz_readonly', 'password': pg_password, 'ssl': 'disable'},
            'mailpit-smtp': {'host': 'mailpit-smtp.middleware', 'port': 25, 'secure': False, 'disableStartTls': True},
            'webhook-echo-key': {'name': 'X-Demo-Key', 'value': webhook_key}}


def mapped(doc, creds, *, reset=False):
    payload = {key: copy.deepcopy(doc[key]) for key in ['name', 'nodes', 'connections', 'settings']}
    payload['pinData'] = {}
    # Only update strips these reset markers; create stores its settings verbatim.
    if reset:
        payload['settings'] = {**{k: 'DEFAULT' for k in DEFAULTABLE_SETTINGS},
                               'executionTimeout': -1, **payload['settings']}
    for node in payload['nodes']:
        for kind, ref in node.get('credentials', {}).items():
            name = ref['name']; c = creds.get(name)
            require(c is not None and c.get('type') == kind, 'missing or mismatched credential')
            node['credentials'][kind] = {'name': name, 'id': c['id']}
    return payload


def check_flow(flow, doc, creds):
    expect(isinstance(flow, dict) and isinstance(flow.get('id'), str)
           and isinstance(flow.get('versionId'), str), 'workflow detail')
    require(flow.get('active') is doc['active'] and
           (not doc['active'] or flow.get('activeVersionId') == flow['versionId']), 'workflow publication (draft not served)')
    # Compare portable content, ignoring editor-inserted optional fields on nodes.
    expected = mapped(doc, creds)
    require(flow.get('name') == expected['name'] and flow.get('connections') == expected['connections'], 'workflow content')
    expect(isinstance(flow.get('nodes'), list), 'workflow nodes')
    require(len(flow['nodes']) == len(expected['nodes']), 'workflow nodes differ')
    actual = {n['name']: n for n in flow['nodes']}
    for node in expected['nodes']:
        require(node['name'] in actual and all(actual[node['name']].get(k) == v for k,v in node.items()), 'workflow node content')
    require(not flow.get('pinData'), 'workflow pinData must be empty')
    actual_settings = flow.get('settings')
    expect(isinstance(actual_settings, dict), 'workflow settings')
    desired = doc['settings']
    for key in sorted(set(actual_settings) | set(desired)):
        if key in desired:
            valid = key in actual_settings and actual_settings[key] == desired[key]
        else:
            valid = key in EDITOR_DEFAULT_SETTINGS and type(actual_settings[key]) is type(EDITOR_DEFAULT_SETTINGS[key]) and actual_settings[key] == EDITOR_DEFAULT_SETTINGS[key]
        # Name only the key; values may refer to private workflows/configuration.
        require(valid, 'workflow settings key ' + key + ' differs; manual correction required')


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
    value = _private_regular_file(file).strip()
    if len(value) != 32 or any(c not in '0123456789abcdef' for c in value):
        raise SeedError('webhook key file must contain the original 32 lowercase hex characters')
    return value


def verify_echo(creds, url, key, path):
    c = creds.get('webhook-echo-key')
    expect(c is not None and c.get('type') == 'httpHeaderAuth', 'webhook credential')
    probe = {'ahoj': 'světe', 'probe': secrets.token_hex(8)}
    target = url.rstrip('/') + '/webhook/' + urllib.parse.quote(path, safe='/')
    unauthorized = urllib.request.Request(target, json.dumps(probe).encode(), headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.build_opener(NoRedirect()).open(unauthorized, timeout=30):
            raise SeedError('webhook accepted a request without the demo key')
    except urllib.error.HTTPError as error:
        expect(error.code in (401, 403), 'webhook missing-key denial', status=error.code)
    except (OSError, urllib.error.URLError, http.client.HTTPException):
        raise SeedError('webhook denial probe failed (response withheld)') from None
    request = urllib.request.Request(target, json.dumps(probe).encode(),
              headers={'Content-Type': 'application/json', 'X-Demo-Key': key})
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=30) as response:
            expect(response.status == 200 and json.loads(response.read()) == probe, 'webhook echo', status=response.status)
    except urllib.error.HTTPError as error:
        raise SeedError(f'webhook echo: HTTP {error.code} (body withheld)') from None
    except (OSError, urllib.error.URLError, http.client.HTTPException, ValueError):
        raise SeedError('webhook echo failed (response withheld)') from None


def run(args):
    docs = documents(args.dir)
    owner_password = password_file(args.owner_password_file)
    required = referenced_credentials(docs)
    pg_password = private_file(args.pg_ro_password_file) if 'hartland-cz-pg' in required and not args.verify else None
    client = login(args.url, OWNER, owner_password, 'global:owner')
    project = client.call('/rest/projects/personal')
    expect(isinstance(project, dict) and isinstance(project.get('id'), str)
           and project.get('type') == 'personal', 'owner personal project')
    project_id = project['id']
    filters = {'projectId': project_id}
    credential_path = '/rest/credentials?' + urllib.parse.urlencode({'filter': json.dumps(filters)})
    own_creds = client.call(credential_path)
    own_flows = workflow_roster(client, {**filters, 'isArchived': False})
    creds = by_name(own_creds, '/rest/credentials')
    flows = by_name(own_flows, '/rest/workflows')
    # Global owner can see peer projects. Count collisions without logging their names/IDs.
    all_creds = client.call('/rest/credentials')
    expect(isinstance(all_creds, list), '/rest/credentials')
    all_flows = workflow_roster(client, {'isArchived': False})
    own_cids = {c['id'] for c in own_creds}
    own_wids = {w['id'] for w in own_flows}
    ignored = sum(c.get('name') in required and c.get('id') not in own_cids for c in all_creds)
    ignored += sum(w.get('name') in {d['name'] for d in docs} and w.get('id') not in own_wids for w in all_flows)
    if ignored: print(f'{ignored} same-named items in other projects ignored')
    # Detect ambiguity and schema mismatches before performing any content mutation.
    for name in required:
        if name in creds: expect(creds[name].get('type') == CREDENTIAL_TYPES[name], 'existing credential type')
    key = webhook_key_file(args.webhook_key_file, create=not args.verify and 'webhook-echo-key' not in creds) if 'webhook-echo-key' in required else None
    probes = echo_paths(docs)
    if args.verify:
        for doc in docs:
            require(doc['name'] in flows, 'missing workflow')
            flow = client.call('/rest/workflows/' + urllib.parse.quote(flows[doc['name']]['id'], safe=''))
            check_flow(flow, doc, creds)
        for path in probes: verify_echo(creds, args.url, key, path)
        print(f'{len(docs)} workflows verified; publication/content/credentials match' + ('; webhook echo ✓' if probes else ''))
        return
    for name, data in credential_data(pg_password, key).items():
        if name not in required: continue
        if name == 'webhook-echo-key' and name in creds:
            # Preserve the encrypted existing key; never rotate it on reset/rehearsal.
            continue
        payload = {'name': name, 'type': CREDENTIAL_TYPES[name], 'data': data}
        if name in creds:
            c = client.call('/rest/credentials/' + urllib.parse.quote(creds[name]['id'], safe=''), payload, method='PATCH')
        else: c = client.call('/rest/credentials', {**payload, 'projectId': project_id})
        expect(isinstance(c, dict) and isinstance(c.get('id'), str) and c.get('name') == name
               and c.get('type') == CREDENTIAL_TYPES[name], 'credential upsert')
        creds[name] = c
        print('credential ready: ' + name)
    for doc in docs:
        payload = mapped(doc, creds, reset=doc['name'] in flows)
        if doc['name'] in flows:
            wid = urllib.parse.quote(flows[doc['name']]['id'], safe='')
            before = client.call('/rest/workflows/' + wid)
            expect(isinstance(before.get('checksum'), str), 'workflow checksum')
            # CE PATCH forces saves and ignores expectedChecksum; activate/licensed PATCH still check it.
            flow = client.call('/rest/workflows/' + wid, {**payload, 'expectedChecksum': before['checksum']}, method='PATCH')
        else: flow = client.call('/rest/workflows', {**payload, 'projectId': project_id})
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
    parser.add_argument('--webhook-key-file', default=str(state_home()/'hartland-n8n/webhook-echo-key'),
                        help='private persistent key file; generated once, never rotated automatically')
    parser.add_argument('--owner-password-file'); parser.add_argument('--pg-ro-password-file')
    parser.add_argument('--list-required-credentials', action='store_true', help='list credential names required by workflow files; no login')
    parser.add_argument('--verify', action='store_true'); args = parser.parse_args()
    args.url = os.environ.get('N8N_URL', 'https://n8n.hartland.collite.cz')
    try:
        validate_base_url(args.url)
    except SeedError as error: parser.error(str(error))
    try:
        if args.list_required_credentials:
            print('\n'.join(sorted(referenced_credentials(documents(args.dir)))))
        else: run(args)
        return 0
    except (SeedError, OSError, http.client.HTTPException, UnicodeError, KeyError, TypeError, ValueError, AttributeError) as error:
        print('ERROR: '+(str(error) if isinstance(error, SeedError) else 'unexpected response or local file error (details withheld)'),file=sys.stderr)
        return 1
if __name__=='__main__': sys.exit(main())
