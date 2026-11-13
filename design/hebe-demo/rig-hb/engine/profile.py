"""Fail-closed engine-profile checks; no credentials or cluster access in these validators."""
import json
import re
import sys
import tomllib

IMAGE = 'ghcr.io/collite/hebe:0.11.11'
DIGEST = 'sha256:d7b3e6c29caa32c140f6305ef5a8cd77f3e694a1e5697dcee83c9c2d40b35727'


def config(cm):
    c = tomllib.loads(cm['data']['config.toml'])
    if c['channels']['telegram'].get('enabled') is not False or c['engine'].get('deliver_channels') != ['web']:
        raise ValueError('phone N/A requires Telegram disabled and web-only engine delivery')
    if c['engine'].get('rest_url') != 'http://process-engine.process-engine.svc/engine-rest':
        raise ValueError('wrong bp-dsk engine URL')
    return 'Telegram disabled; web only'


def image(deploy, pods):
    if deploy['spec']['replicas'] != 1 or deploy['status'].get('readyReplicas') != 1:
        raise ValueError('expected one Ready Markéta replica')
    containers = deploy['spec']['template']['spec']['containers']
    if len(containers) != 1 or containers[0]['image'] != IMAGE:
        raise ValueError('deployment is not the reviewed 0.11.11 image')
    live = [p for p in pods['items'] if not p['metadata'].get('deletionTimestamp')]
    if len(live) != 1:
        raise ValueError('expected only the new Markéta pod')
    pod = live[0]
    app, = pod['status']['containerStatuses']
    init, = pod['status']['initContainerStatuses']
    for c in [app, init]:
        if c['imageID'] != 'ghcr.io/collite/hebe@' + DIGEST:
            raise ValueError('pod app/init imageID differs from the published digest')
    if not app['ready'] or init['state'].get('terminated', {}).get('exitCode') != 0:
        raise ValueError('new app not Ready or truststore init failed')
    return 'one Ready Markéta pod; app/init match ' + IMAGE + '@' + DIGEST


def doctor(text):
    match = re.search(r'\{\s*"checks"\s*:', text)
    if not match:
        raise ValueError('doctor returned no check report')
    report = json.loads(text[match.start():])
    checks = {c['name']: c for c in report['checks']}
    names = ['Process engine', 'OBO mint', 'State durability', 'Console admission',
             'Console token keys', 'Receipts signing key']
    for name in names:
        if checks.get(name, {}).get('status') != 'pass':
            raise ValueError('doctor missing or failed: ' + name)
    if 'workspace=postgres receipts=postgres' not in checks['State durability']['message']:
        raise ValueError('ephemeral state must use both PostgreSQL stores')
    return 'six platform/engine/durability checks pass (legacy filesystem rows are outside the PG profile)'


if __name__ == '__main__':
    try:
        if sys.argv[1] == 'image':
            decoder = json.JSONDecoder()
            text = sys.stdin.read()
            deploy, offset = decoder.raw_decode(text)
            print(image(deploy, json.loads(text[offset:])))
        elif sys.argv[1] == 'config':
            print(config(json.load(sys.stdin)))
        else:
            print(doctor(sys.stdin.read()))
    except (ValueError, KeyError, IndexError, TypeError) as e:
        print('engine profile validation failed: ' + str(e))
        sys.exit(1)
