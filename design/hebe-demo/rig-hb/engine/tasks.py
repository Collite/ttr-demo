"""Read open-task counts with Markéta's existing OBO seed, without logging credentials."""
import base64
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import probe

REMOTE = r'''
import base64, json, ssl, sys, urllib.parse, urllib.request
p = json.load(sys.stdin)
context = ssl.create_default_context()
context.load_verify_locations(cadata=p['ca'])
body = urllib.parse.urlencode({'grant_type':'refresh_token', 'client_id':p['client'],
    'client_secret':p['secret'], 'refresh_token':p['seed']}).encode()
req = urllib.request.Request('https://keycloak.192-168-1-38.nip.io/realms/kantheon/protocol/openid-connect/token',data=body)
with urllib.request.urlopen(req,context=context,timeout=30) as r:
    access = json.load(r)['access_token']
part=access.split('.')[1]
claims=json.loads(base64.urlsafe_b64decode(part+'='*(-len(part)%4)))
assert claims['preferred_username']=='marketa' and claims['azp']=='hebe'
assert 'hartland-sales-managers' in claims['groups']
assert 'process-engine-rest' in claims['aud']
ids=set()
for query in ['assignee=marketa','candidateUser=marketa']:
    first=0
    while True:
        req=urllib.request.Request('http://process-engine.process-engine.svc/engine-rest/task?'+query+'&active=true&firstResult='+str(first)+'&maxResults=50',headers={'Authorization':'Bearer '+access})
        with urllib.request.urlopen(req,timeout=30) as r: rows=json.load(r)
        ids.update(t['id'] for t in rows)
        if len(rows)<50: break
        first+=50
print(json.dumps({'user':'marketa','azp':'hebe','groups':'hartland-sales-managers',
                  'audience':'process-engine-rest','openTasks':len(ids)}))
'''


def main():
    result = probe.kubectl('-n', 'kantheon', 'get', 'secret', 'hebe-marketa', '-o', 'json')
    if result.returncode:
        raise RuntimeError('Markéta secret unavailable')
    data = json.loads(result.stdout)['data']
    def key(name):
        return base64.b64decode(data[name]).decode()
    result = probe.kubectl('-n', 'auth', 'get', 'secret', 'root-ca-secret', '-o', 'json')
    if result.returncode:
        raise RuntimeError('public cluster CA unavailable')
    ca = base64.b64decode(json.loads(result.stdout)['data']['tls.crt']).decode()
    print(json.dumps(probe.run(REMOTE, {'client': key('keycloak-client-id'),
        'secret': key('keycloak-client-secret'), 'seed': key('keycloak-offline-token'), 'ca': ca})))


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, KeyError, ValueError) as e:
        raise SystemExit(str(e)) from None
