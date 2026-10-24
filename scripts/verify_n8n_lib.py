"""Read-only n8n P1 verification. Standard library only; errors never print response/command bodies."""
import argparse
import base64
from dataclasses import dataclass
import hashlib
import http.client
import json
import os
import subprocess
from urllib.parse import urlsplit
import uuid

IMAGE = 'docker.n8n.io/n8nio/n8n:2.44.6'
PVC = 'n8n-main-persistence'
GUID = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'
TIMEOUT = 10


class CheckError(Exception):
    """Safe, operator-facing failure without raw HTTP, subprocess output or credentials."""


def require(condition, message):
    if not condition:
        raise CheckError(message)


@dataclass
class HTTPResult:
    status: int
    headers: dict
    body: bytes


def parsed_url(url):
    try:
        parsed = urlsplit(url)
        require(parsed.scheme in ('http', 'https') and parsed.hostname and parsed.port != 0,
                'N8N_URL must be an http(s) URL')
        require(not (parsed.username or parsed.password or parsed.fragment),
                'N8N_URL cannot contain credentials or a fragment')
        return parsed
    except ValueError as error:
        raise CheckError('invalid N8N_URL') from error


def http_get(url, *, headers=None, timeout=TIMEOUT):
    """No redirects or cookies; TLS validation on. A WebSocket 101 is read without blocking on a body."""
    parsed = parsed_url(url)
    connection_type = http.client.HTTPSConnection if parsed.scheme == 'https' else http.client.HTTPConnection
    connection = connection_type(parsed.hostname, parsed.port, timeout=timeout)
    try:
        path = parsed.path or '/'
        if parsed.query:
            path += '?' + parsed.query
        connection.request('GET', path, headers=headers or {})
        response = connection.getresponse()
        body = b'' if response.status == 101 else response.read(262145)
        require(len(body) <= 262144, 'HTTP response exceeds 256 KiB')
        return HTTPResult(response.status, {k.lower(): v for k, v in response.getheaders()}, body)
    except (OSError, http.client.HTTPException) as error:
        raise CheckError('HTTP request failed (connection, timeout or TLS)') from error
    finally:
        connection.close()


def http_code(url, *, timeout=TIMEOUT):
    return http_get(url, timeout=timeout).status


def managed_role_version(cluster, role='n8n'):
    """CNPG's resourceVersion is a string; a stale password status cannot hide reconciliation errors."""
    try:
        managed = cluster['status']['managedRolesStatus']
        require(role not in managed.get('cannotReconcile', {}), 'CNPG cannot reconcile the n8n role')
        for state, roles in managed.get('byStatus', {}).items():
            require(role not in roles or state == 'reconciled', 'CNPG n8n role is not reconciled')
        version = managed['passwordStatus'][role]['resourceVersion']
        require(isinstance(version, str) and bool(version.strip()), 'CNPG n8n password resourceVersion is absent')
        return version
    except (KeyError, TypeError, AttributeError) as error:
        raise CheckError('CNPG managedRolesStatus/passwordStatus.n8n shape is missing or invalid') from error


def websocket_status(status):
    # 401 means the authentication gate is reached; only a validated 101 proves an HTTP upgrade.
    return status in (101, 401)


def probe_push(base_url):
    """A proper RFC6455 request. n8n 2.44.6's ws.handleUpgrade precedes Express authentication."""
    parsed = parsed_url(base_url)
    key = base64.b64encode(os.urandom(16)).decode()
    origin = f'{parsed.scheme}://{parsed.netloc}'
    response = http_get(base_url.rstrip('/') + '/rest/push?pushRef=' + uuid.uuid4().hex, headers={
        'Connection': 'Upgrade', 'Upgrade': 'websocket', 'Sec-WebSocket-Version': '13',
        'Sec-WebSocket-Key': key, 'Origin': origin,
    })
    if response.status == 101:
        expected = base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()
        require(response.headers.get('upgrade', '').lower() == 'websocket'
                and 'upgrade' in [part.strip().lower() for part in response.headers.get('connection', '').split(',')]
                and response.headers.get('sec-websocket-accept') == expected,
                'HTTP 101 has an invalid WebSocket handshake')
    return response.status


def decode_json(raw, description):
    try:
        value = json.loads(raw)
        require(isinstance(value, dict), f'{description}: expected a JSON object')
        return value
    except (ValueError, TypeError) as error:
        raise CheckError(f'{description}: invalid JSON (body withheld)') from error


class Rig:
    def __init__(self, context, url, image):
        self.context, self.url, self.image = context, url.rstrip('/'), image

    def kubectl(self, namespace, *args):
        command = ['kubectl', '--context', self.context, '--request-timeout=10s', '-n', namespace, *args]
        try:
            result = subprocess.run(command, text=True, capture_output=True, timeout=20, check=False)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise CheckError('kubectl unavailable or timed out (output withheld)') from error
        require(result.returncode == 0, 'kubectl command failed (output withheld)')
        return result.stdout.strip()

    def get(self, namespace, kind, name=None, *extra):
        args = ['get', kind] + ([name] if name else []) + list(extra) + ['-o', 'json']
        return decode_json(self.kubectl(namespace, *args), f'{namespace}/{kind}')

    def application(self):
        app = self.get('argocd', 'application', 'middleware')
        sync, health = app['status']['sync']['status'], app['status']['health']['status']
        require(sync == 'Synced' and health == 'Healthy', 'middleware Application is not Synced/Healthy')
        return 'middleware Synced/Healthy'

    def workload(self):
        deployment = self.get('middleware', 'deployment', 'n8n')
        status, desired = deployment['status'], deployment['spec']['replicas']
        require(desired == 1 and status.get('readyReplicas') == desired
                and status.get('updatedReplicas') == desired and status.get('replicas') == desired
                and status.get('observedGeneration', 0) >= deployment['metadata']['generation'],
                'n8n Deployment rollout is not ready at its current generation')
        template = deployment['spec']['template']['spec']
        require(any(c.get('name') == 'n8n' and c.get('image') == self.image for c in template['containers']),
                'Deployment image does not match N8N_IMAGE')
        pods = self.get('middleware', 'pods', None, '-l', 'app.kubernetes.io/instance=n8n,app.kubernetes.io/component=main')
        active = [p for p in pods['items'] if not p['metadata'].get('deletionTimestamp')]
        require(bool(active), 'no active n8n main pod')
        for pod in active:
            require(any(c.get('name') == 'n8n' and c.get('image') == self.image for c in pod['spec']['containers']),
                    'active pod image does not match N8N_IMAGE')
            require(any(c.get('type') == 'Ready' and c.get('status') == 'True'
                        for c in pod['status'].get('conditions', [])), 'n8n main pod is not Ready')
        volumes = {v['name'] for v in template.get('volumes', [])
                   if v.get('persistentVolumeClaim', {}).get('claimName') == PVC}
        main = next(c for c in template['containers'] if c.get('name') == 'n8n')
        require(any(m.get('name') in volumes and m.get('mountPath') == '/home/node/.n8n'
                    for m in main.get('volumeMounts', [])),
                'Deployment does not mount n8n persistence PVC')
        pvc = self.get('middleware', 'pvc', PVC)
        require(pvc['status']['phase'] == 'Bound', 'n8n persistence PVC is not Bound')
        return f'{len(active)} Ready main pod; PVC {PVC} Bound; image {self.image}'

    def health(self):
        live = http_code(self.url + '/healthz')
        ready = http_code(self.url + '/healthz/readiness')
        require(live == ready == 200, f'gateway /healthz HTTP {live}, /healthz/readiness HTTP {ready}')
        return 'gateway /healthz and /healthz/readiness HTTP 200'

    def owner(self):
        response = http_get(self.url + '/rest/settings')
        require(response.status == 200, f'/rest/settings HTTP {response.status}')
        settings = decode_json(response.body, '/rest/settings')
        claimed = settings['data']['userManagement']['showSetupOnFirstLoad']
        require(claimed is False, 'owner setup is unclaimed or settings shape changed')
        return 'showSetupOnFirstLoad=false; owner claimed'

    def push(self):
        status = probe_push(self.url)
        require(websocket_status(status), f'push probe HTTP {status}; expected 101 upgrade or 401 authentication')
        return ('HTTP 101; valid WebSocket upgrade' if status == 101 else
                'HTTP 401; authentication reached (authenticated editor connection still requires browser check)')

    def database(self):
        db_type = self.kubectl('middleware', 'exec', 'deployment/n8n', '-c', 'n8n', '--', 'printenv', 'DB_TYPE')
        require(db_type == 'postgresdb', 'n8n runtime DB_TYPE is not postgresdb')
        version = managed_role_version(self.get('data', 'cluster', 'postgres'))
        return f'postgresdb; CNPG n8n password resourceVersion={version}'

    def run(self):
        checks = [('Application', self.application), ('pod, persistence and image', self.workload),
                  ('public health', self.health), ('owner claimed', self.owner),
                  ('push channel', self.push), ('database', self.database)]
        failures = 0
        for number, (name, check) in enumerate(checks, 1):
            try:
                evidence = check()
                print(f'✓ V{number} {name} — {evidence}')
            except (CheckError, KeyError, TypeError, AttributeError, ValueError) as error:
                failures += 1
                evidence = str(error) if isinstance(error, CheckError) else 'response shape missing or invalid (body withheld)'
                print(f'✗ V{number} {name} — {evidence}')
        for number, phase in [(7, 2), (8, 2), (9, 2), (10, 3), (11, 4)]:
            print(f'○ V{number} not yet (P{phase})')
        print(f'{6 - failures} pass · {failures} fail · 5 not yet')
        return 1 if failures else 0


def main():
    parser = argparse.ArgumentParser(description='Read-only n8n P1 V1–V6 checks; later-phase checks stay pending. '
        'Environment: KUBE_CONTEXT=hartland, N8N_URL=https://n8n.hartland.collite.cz, N8N_IMAGE=' + IMAGE)
    parser.parse_args()
    url = os.environ.get('N8N_URL', 'https://n8n.hartland.collite.cz')
    try:
        parsed = parsed_url(url)
        require(not parsed.query, 'N8N_URL base cannot contain a query')
        return Rig(os.environ.get('KUBE_CONTEXT', 'hartland'), url, os.environ.get('N8N_IMAGE', IMAGE)).run()
    except CheckError as error:
        parser.error(str(error))


if __name__ == '__main__':
    raise SystemExit(main())
