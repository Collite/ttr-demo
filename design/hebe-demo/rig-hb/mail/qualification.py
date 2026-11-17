"""HE-D-33 inherited qualification: compare accepted source inputs to live policy.

No mail login, token mutation, realm edit or credential file. Keycloak's existing
admin credential is used only in local process memory for GETs; its session logs out.
Only non-secret settings/hashes leave this reader.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import ssl
import subprocess
import urllib.parse
import urllib.request

HERE = Path(__file__).resolve().parent
CASES = {'missing-audience-initial-imap', 'missing-audience-continuation-imap',
         'missing-audience-smtp', 'wrong-audience-imap', 'wrong-audience-smtp',
         'engine-only-imap', 'engine-only-smtp', 'malformed-imap', 'malformed-smtp',
         'expired-imap', 'expired-smtp', 'foreign-signature'}
BASELINE = HERE / 'qualification-baseline.json'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def mapper(value):
    return {k: value.get(k, {} if k == 'config' else None)
            for k in ('name', 'protocol', 'protocolMapper', 'config')}


def policy(expected):
    scope = expected['mailScope']
    result = {'clients': {name: {**c, 'mappers': sorted([mapper(m) for m in c['mappers']], key=lambda m: m['name'])}
                        for name, c in expected['clients'].items()},
            'mailScope': {'name': scope['name'], 'protocol': scope['protocol'],
                          'attributes': scope['attributes'], 'mappers': sorted([mapper(m) for m in scope['protocolMappers']], key=lambda m: m['name'])},
            'mailAssociations': {'default': [], 'optional': ['hebe', 'webmail']},
            'realmMailDefault': False, 'issuer': expected['issuer'],
            'publicJwks': expected['issuer'] + '/protocol/openid-connect/certs'}
    # Keycloak26.5.1 ClientManager.enableServiceAccount adds the built-in scope;
    # GroupMembershipMapper.setClaim forces multivalued on token issuance. These
    # deterministic server rules expand the accepted authored realm, not live data.
    # Exact primary-source links and the pre-qualification running-image witness
    # are kept in the baseline. No other extra scope/mapper/config is normalized.
    for c in result['clients'].values():
        if c['flags']['serviceAccountsEnabled']:
            c['default'] = sorted(set(c['default']) | {'service_account'})
        for m in c['mappers']:
            if m['protocolMapper'] == 'oidc-group-membership-mapper':
                m['config'] = {**m['config'], 'multivalued': 'true'}
    return result


def expected_observation(expected):
    return {k: expected[k] for k in ('jamesImage', 'webmailImage', 'jamesFiles',
                                    'webmailConfigSha256', 'caSha256', 'webmailRuntime',
                                    'keycloakImageID')} | {'policy': policy(expected)}


def evaluate(current, expected):
    missing = CASES - set(expected.get('cases', {}))
    if missing or any(not all(expected['cases'][c].get(k) for k in ('source', 'kind', 'case')) for c in CASES - missing):
        return 'OPEN', 'inherited qualification: required negative-case provenance missing', None
    desired = expected_observation(expected)
    if set(current) != set(desired):
        return 'OPEN', 'inherited qualification: incomplete live comparison', None
    changed = [k for k in desired if current[k] != desired[k]]
    if changed:
        return 'FAIL', 'inherited qualification: material baseline drift: ' + ', '.join(changed), None
    fingerprint = digest(current)
    return 'PASS', ('inherited qualification: #305 local21/live19 + #304 JWT-unit71 foreign-signature; '
                    '#307 client configuration; current policy/config match ' + fingerprint), fingerprint


def kc(*args):
    result = subprocess.run(['kubectl', '--context', 'bp-dsk', *args], capture_output=True, text=True, timeout=60)
    if result.returncode:
        raise RuntimeError('read-only cluster observation failed')
    return result.stdout


def pod(label):
    items = json.loads(kc('-n', 'middleware', 'get', 'pods', '-l', 'app.kubernetes.io/name=' + label, '-o', 'json'))['items']
    items = [p for p in items if not p['metadata'].get('deletionTimestamp')]
    if len(items) != 1 or not items[0]['status']['containerStatuses'][0]['ready']:
        raise RuntimeError('one Ready substrate pod required')
    return items[0]


def hash_file(name, path):
    return kc('-n', 'middleware', 'exec', name, '--', 'sha256sum', path).split()[0]


def read_policy(expected):
    issuer = expected['issuer']
    server = issuer.split('/realms/')[0]
    context = ssl.create_default_context(cafile=os.environ['HEBE_VERIFY_CA_FILE'])
    data = json.loads(kc('-n', 'auth', 'get', 'secret', 'keycloak-admin-creds', '-o', 'json'))['data']
    password = base64.b64decode(data['admin-password']).decode()
    form = urllib.parse.urlencode({'grant_type': 'password', 'client_id': 'admin-cli',
                                  'username': 'admin', 'password': password}).encode()
    with urllib.request.urlopen(urllib.request.Request(server + '/realms/master/protocol/openid-connect/token', data=form), context=context, timeout=20) as response:
        tokens = json.load(response)
    del password, data, form

    def get(path):
        request = urllib.request.Request(server + '/admin/realms/kantheon' + path,
                                         headers={'Authorization': 'Bearer ' + tokens['access_token']})
        with urllib.request.urlopen(request, context=context, timeout=20) as response:
            return json.load(response)

    try:
        scopes = get('/client-scopes')
        mail, = [s for s in scopes if s['name'] == 'mail']
        mail = get('/client-scopes/' + mail['id'])
        associations = {'default': [], 'optional': []}
        clients = {}
        for c in get('/clients'):
            names = {}
            for kind in associations:
                names[kind] = sorted(s['name'] for s in get('/clients/' + c['id'] + '/' + kind + '-client-scopes'))
                if 'mail' in names[kind]:
                    associations[kind].append(c['clientId'])
            if c['clientId'] in expected['clients']:
                value = get('/clients/' + c['id'])
                clients[c['clientId']] = {'flags': {k: value.get(k, k == 'fullScopeAllowed') for k in expected['clients'][c['clientId']]['flags']},
                    'default': names['default'], 'optional': names['optional'],
                    'redirectUris': sorted(value.get('redirectUris', [])),
                    'mappers': sorted([mapper(m) for m in value.get('protocolMappers', [])], key=lambda m: m['name'])}
        realm_default = get('/default-default-client-scopes') + get('/default-optional-client-scopes')
        with urllib.request.urlopen(issuer + '/.well-known/openid-configuration', context=context, timeout=20) as response:
            discovery = json.load(response)
        return {'clients': clients, 'mailScope': {'name': mail['name'], 'protocol': mail['protocol'],
                  'attributes': mail['attributes'], 'mappers': sorted([mapper(m) for m in mail['protocolMappers']], key=lambda m: m['name'])},
                'mailAssociations': {k: sorted(v) for k, v in associations.items()},
                'realmMailDefault': any(s['name'] == 'mail' for s in realm_default),
                'issuer': discovery['issuer'], 'publicJwks': discovery['jwks_uri']}
    finally:
        form = urllib.parse.urlencode({'client_id': 'admin-cli', 'refresh_token': tokens['refresh_token']}).encode()
        with urllib.request.urlopen(urllib.request.Request(server + '/realms/master/protocol/openid-connect/logout', data=form), context=context, timeout=20):
            pass


def read_current(expected):
    james, webmail = pod('mail'), pod('webmail')
    for p, key in [(james, 'jamesImage'), (webmail, 'webmailImage')]:
        spec = p['spec']['containers'][0]['image']
        actual = p['status']['containerStatuses'][0]['imageID']
        if not actual.endswith('@' + spec.split('@')[-1]):
            raise RuntimeError('substrate runtime image differs from its immutable spec')
    web = webmail['metadata']['name']
    keys = list(expected['webmailRuntime'])
    php = ('define("RCUBE_INSTALL_PATH", "/var/www/html/"); $config=[]; '
           'include "/var/www/html/config/config.inc.php"; $safe=[]; foreach(' +
           json.dumps(keys) + ' as $k){$safe[$k]=$config[$k]??null;} echo json_encode($safe);')
    issuer_pods = json.loads(kc('-n', 'auth', 'get', 'pods', '-l', 'app.kubernetes.io/name=keycloakx', '-o', 'json'))['items']
    issuer_pods = [p for p in issuer_pods if not p['metadata'].get('deletionTimestamp')]
    if len(issuer_pods) != 1 or not issuer_pods[0]['status']['containerStatuses'][0]['ready']:
        raise RuntimeError('one Ready issuer pod required')
    return {'jamesImage': james['spec']['containers'][0]['image'],
            'webmailImage': webmail['spec']['containers'][0]['image'],
            'jamesFiles': {f: hash_file(james['metadata']['name'], '/root/conf/' + f) for f in expected['jamesFiles']},
            'webmailConfigSha256': hash_file(web, '/var/roundcube/config/webmail.inc.php'),
            'caSha256': hash_file(web, '/etc/webmail-ca/ca.crt'),
            'webmailRuntime': json.loads(kc('-n', 'middleware', 'exec', web, '--', 'php', '-r', php)),
            'keycloakImageID': issuer_pods[0]['status']['containerStatuses'][0]['imageID'],
            'policy': read_policy(expected)}


def verify():
    expected = json.loads(BASELINE.read_text())
    try:
        return evaluate(read_current(expected), expected)
    except Exception as error:
        return 'OPEN', 'inherited qualification: comparison unavailable (' + type(error).__name__ + ')', None
