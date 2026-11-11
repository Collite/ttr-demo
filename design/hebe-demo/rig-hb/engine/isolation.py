"""Exercise console admission from the engine namespace, around the gateway."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import probe

REMOTE = r'''
import json, socket, urllib.error, urllib.request
req=urllib.request.Request('http://hebe.kantheon:8765/api/status',
    headers={'x-forwarded-user':'marketa'})
try:
    with urllib.request.urlopen(req,timeout=5) as r:
        raise RuntimeError('forged header admitted: '+str(r.status))
except urllib.error.HTTPError as e:
    assert e.code==401
    print(json.dumps({'status':401,'result':'forged header refused without edge token'}))
except (TimeoutError,socket.timeout):
    print(json.dumps({'result':'connection timed out under network isolation'}))
'''

if __name__ == '__main__':
    try:
        print(json.dumps(probe.run(REMOTE, {})))
    except RuntimeError as e:
        raise SystemExit(str(e)) from None
