"""Deploy only the saved HE fixture, then reuse Olymp's PE authorization reconciler.

TTR_BEARER_FILE (0600) or TTR_BEARER supplies an existing personal bora bearer.
Cleanup removes only this fixture deployment, and refuses while an instance is active.
"""
import argparse
import base64
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import probe

REMOTE = r'''
import contextlib, io, json, os, sys, urllib.request, uuid
p = json.load(sys.stdin)
base = 'http://process-engine.process-engine.svc/engine-rest'
def api(path, body=None, method=None, content_type='application/json'):
    req = urllib.request.Request(base+path, data=body, method=method,
        headers={'Authorization': 'Bearer '+p['token'], 'Content-Type': content_type})
    with urllib.request.urlopen(req, timeout=30) as r:
        b = r.read()
        return json.loads(b) if b else None
name = 'hebe-p2-cert'
if p['cleanup']:
    rows = api('/deployment?name='+name)
    for row in rows:
        if api('/process-instance/count?deploymentId='+row['id'])['count']:
            raise RuntimeError('active fixture instance; cleanup refused')
    for row in rows:
        api('/deployment/'+row['id']+'?cascade=false', method='DELETE')
    print(json.dumps({'removed': len(rows)}))
else:
    boundary = 'hebe-cert-'+uuid.uuid4().hex
    fields = [('deployment-name', name), ('enable-duplicate-filtering', 'true'),
              ('deploy-changed-only', 'true')]
    body = b''
    for key, value in fields:
        body += ('--'+boundary+'\r\nContent-Disposition: form-data; name="'+key+'"\r\n\r\n'+value+'\r\n').encode()
    body += ('--'+boundary+'\r\nContent-Disposition: form-data; name="data"; filename="hebe-p2-cert.bpmn"\r\nContent-Type: application/xml\r\n\r\n').encode()
    body += p['bpmn'].encode()+('\r\n--'+boundary+'--\r\n').encode()
    deployed = api('/deployment/create', body, content_type='multipart/form-data; boundary='+boundary)
    os.environ['ENGINE_URL'] = base.removesuffix('/engine-rest')
    os.environ['TTR_BEARER'] = p['token']
    scope = {'__name__': 'hebe_existing_reconciler'}
    with contextlib.redirect_stdout(io.StringIO()) as out:
        exec(compile(p['reconciler'], 'provision-authorizations.py', 'exec'), scope)
        scope['main']()
    print(json.dumps({'deploymentId': deployed.get('id'), 'name': deployed.get('name'),
                      'authorization': out.getvalue().strip()}))
'''


def token():
    path = os.environ.get('TTR_BEARER_FILE')
    if path:
        p = Path(path)
        if not p.is_file() or p.stat().st_mode & 0o077:
            raise ValueError('TTR_BEARER_FILE must be a private regular file (0600)')
        value = p.read_text().strip()
    else:
        value = os.environ.get('TTR_BEARER', '').strip()
    if not value:
        raise ValueError('Supply the existing bora operator bearer through TTR_BEARER_FILE or TTR_BEARER')
    try:
        part = value.split('.')[1]
        claims = json.loads(base64.urlsafe_b64decode(part + '=' * (-len(part) % 4)))
        if claims.get('preferred_username') != 'bora':
            raise ValueError()
    except (ValueError, IndexError):
        raise ValueError('A personal bora operator bearer is required') from None
    # The engine, not this unverified diagnostic claim, validates the signature and authorization.
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cleanup', action='store_true')
    parser.add_argument('--olymp', type=Path,
                        default=Path(__file__).resolve().parents[5] / 'olymp')
    args = parser.parse_args()
    reconciler = args.olymp / 'clusters/bp-dsk/apps/process-engine/provision-authorizations.py'
    payload = {'token': token(), 'cleanup': args.cleanup,
               'bpmn': Path(__file__).with_name('hebe-p2-cert.bpmn').read_text(),
               'reconciler': reconciler.read_text()}
    print(json.dumps(probe.run(REMOTE, payload)))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError, OSError) as e:
        raise SystemExit(str(e)) from None
