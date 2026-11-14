"""Short-lived bp-dsk Python probe; sensitive payload travels only through stdin."""
import json
import subprocess
import uuid

CONTEXT = 'bp-dsk'
NAMESPACE = 'process-engine'


def kubectl(*args, **kwargs):
    return subprocess.run(['kubectl', '--context', CONTEXT, *args],
                          capture_output=True, text=True, timeout=90, **kwargs)


def run(code, payload):
    name = 'he-p2-cert-probe-' + uuid.uuid4().hex[:10]
    pod = {'apiVersion': 'v1', 'kind': 'Pod', 'metadata': {'name': name,
           'namespace': NAMESPACE, 'labels': {'hebe-certification': 's23d'}},
           'spec': {'restartPolicy': 'Never', 'activeDeadlineSeconds': 180,
                    'terminationGracePeriodSeconds': 1,
                    'automountServiceAccountToken': False,
                    'securityContext': {'runAsNonRoot': True, 'runAsUser': 65534},
                    'containers': [{'name': 'probe', 'image': 'python:3.12-alpine',
                        'command': ['python', '-c', 'import time; time.sleep(170)'],
                        'securityContext': {'allowPrivilegeEscalation': False,
                            'readOnlyRootFilesystem': True, 'capabilities': {'drop': ['ALL']}},
                        'resources': {'requests': {'cpu': '10m', 'memory': '32Mi'},
                                      'limits': {'cpu': '250m', 'memory': '128Mi'}}}]}}
    created = False
    try:
        result = kubectl('create', '-f', '-', input=json.dumps(pod))
        if result.returncode:
            raise RuntimeError('probe creation failed')
        created = True
        result = kubectl('-n', NAMESPACE, 'wait', '--for=condition=Ready',
                         'pod/' + name, '--timeout=60s')
        if result.returncode:
            raise RuntimeError('probe did not become Ready')
        wrapper = ('import json,sys\ntry:\n exec(' + repr(code) + ')\n'
                   'except Exception as e:\n print(json.dumps({"probeError":type(e).__name__, '
                   '"httpStatus":getattr(e,"code",None)}));sys.exit(1)\n')
        result = kubectl('-n', NAMESPACE, 'exec', '-i', name, '--', 'python', '-c', wrapper,
                         input=json.dumps(payload))
        if result.returncode:
            # Do not relay exception dumps or response bodies from a credential-bearing probe.
            try:
                safe = json.loads(result.stdout)
                reason = str(safe.get('probeError')) + ' HTTP ' + str(safe.get('httpStatus'))
            except ValueError:
                reason = 'no structured result'
            raise RuntimeError('authenticated probe failed: ' + reason)
        return json.loads(result.stdout)
    finally:
        if created:
            result = kubectl('-n', NAMESPACE, 'delete', 'pod', name, '--wait=true', '--timeout=30s')
            if result.returncode:
                raise RuntimeError('probe cleanup failed: ' + name)
