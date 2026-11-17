"""Re-read the contracted thread/task stores and console receipts after the human walk."""
import json
import base64
import sys
from pathlib import Path
from datetime import timedelta
import urllib.parse

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.append(str(HERE.parent / 'engine'))
import fixture
import probe
import walk_record


def assess(record, state, receipts):
    steps = record['steps']
    cards = [steps[name] for name in ('card_read', 'console_outcome', 'claimed_elsewhere')]
    forward, bare = steps['forward_start'], steps['bare_forward']
    try:
        instances = {c['instanceId'] for c in cards} | {forward['instanceId']}
        if len(instances) != 4 or not forward.get('cleanupTaskId'):
            return 'OPEN', 'live: four distinct instances and forward cleanup task reference required'
        current = state['instances']
        if ({i['id'] for i in current} != instances or len(current) != 4 or
            any(i['state'] != 'COMPLETED' or i['activeTasks'] != 0 for i in current)):
            return 'FAIL', 'live: controlled instance not completed or still has active tasks'
        threads = state['threads']
        tasks = state['tasks']
        expected = [(c['rootMessageId'], 'card', c['taskId']) for c in cards]
        expected += [(forward['rootMessageId'], 'proposal', forward['proposalId']),
                     (bare['rootMessageId'], 'chat', None)]
        for root, kind, ref in expected:
            found = [t for t in threads if t['root_message_id'] == root]
            if len(found) != 1 or (found[0]['kind'], found[0]['subject_ref'], found[0]['state']) != (kind, ref, 'closed'):
                return 'FAIL', 'live: persisted walk thread missing, crossed or not closed'
        for card in cards:
            found = [t for t in tasks if t['task_id'] == card['taskId']]
            if len(found) != 1 or found[0]['instance_id'] != card['instanceId'] or found[0]['state'] not in ('answered', 'gone'):
                return 'FAIL', 'live: controlled task/instance map or completion differs'
        cleanup = [t for t in tasks if t['task_id'] == forward['cleanupTaskId']]
        if len(cleanup) != 1 or cleanup[0]['instance_id'] != forward['instanceId'] or cleanup[0]['state'] not in ('answered', 'gone'):
            return 'FAIL', 'live: forwarded-start cleanup not reflected in task store'
        if any(t['instance_id'] in instances and t['state'] == 'shown' for t in tasks):
            return 'FAIL', 'live: controlled task still active'
        starts, answers = [], []
        for receipt in receipts:
            tool = receipt.get('tool')
            args = json.loads(receipt.get('argsRedacted', '{}'))
            if tool == 'engine.start' and args.get('key') == 'hebe_p2_cert':
                if receipt.get('ok') is not True or args.get('outcome') != 'started':
                    return 'FAIL', 'live: certification start failed'
                starts.append((receipt, args))
            if tool == 'engine.answer':
                answers.append((receipt, args))
        if len(starts) != 4 or {a['instance'] for _, a in starts} != instances:
            return 'FAIL', 'live: certification start count/instance set differs (expected four)'
        expected_answers = {steps[n]['receiptId']: steps[n] for n in ('card_reply', 'console_outcome')}
        # Cleanup through Tasklist produces no Hebe answer; console/mail cleanup must name its receipt.
        if forward.get('cleanupReceiptId'):
            expected_answers[forward['cleanupReceiptId']] = {'taskId': forward['cleanupTaskId']}
        if len(answers) != len(expected_answers):
            return 'FAIL', 'live: engine answer count differs from performed walk/cleanup'
        for receipt, args in answers:
            key = 'seq' + str(receipt['seq'])
            if (key not in expected_answers or receipt.get('turnId') != expected_answers[key]['taskId'] or
                receipt.get('ok') is not True or args.get('outcome') != 'completed'):
                return 'FAIL', 'live: answer receipt/task/result differs'
            if key == steps['card_reply']['receiptId'] and args.get('channel') != 'email':
                return 'FAIL', 'live: first card answer was not email'
        mail_starts = [a for _, a in starts if a['instance'] == forward['instanceId']]
        if mail_starts[0].get('channel') != 'email':
            return 'FAIL', 'live: forwarded start was not confirmed by email'
        return 'PASS', 'live: persisted walk threads closed and task/instance maps consistent; four starts/' + str(len(answers)) + ' answers match console receipts'
    except (KeyError, TypeError, ValueError):
        return 'OPEN', 'live: incomplete post-walk store/receipt observation'


def stores():
    result = probe.kubectl('-n', 'data', 'get', 'pods', '-l', 'cnpg.io/cluster=postgres,role=primary', '-o', 'json')
    pods = json.loads(result.stdout)['items'] if result.returncode == 0 else []
    if len(pods) != 1:
        raise RuntimeError('one Postgres primary required')
    sql = """BEGIN READ ONLY;
    SET LOCAL search_path=hebe_marketa,public;
    SELECT jsonb_build_object('threads',(SELECT coalesce(jsonb_agg(t),'[]'::jsonb) FROM
      (SELECT root_message_id,kind,subject_ref,state,last_message_id FROM mail_threads) t),
      'tasks',(SELECT coalesce(jsonb_agg(t),'[]'::jsonb) FROM
      (SELECT task_id,instance_id,state FROM engine_tasks) t));
    COMMIT;"""
    result = probe.kubectl('-n', 'data', 'exec', '-i', pods[0]['metadata']['name'], '-c', 'postgres', '--',
                           'psql', '-X', '-qAt', '-v', 'ON_ERROR_STOP=1', '-U', 'postgres', '-d', 'hebe', input=sql)
    if result.returncode:
        raise RuntimeError('read-only thread/task observation unavailable')
    return json.loads(result.stdout)


ENGINE = r'''
import base64,json,ssl,sys,urllib.parse,urllib.request
p=json.load(sys.stdin)
context=ssl.create_default_context(cadata=p['ca'])
body=urllib.parse.urlencode({'grant_type':'refresh_token','client_id':p['client'],
    'client_secret':p['secret'],'refresh_token':p['seed']}).encode()
request=urllib.request.Request('https://keycloak.192-168-1-38.nip.io/realms/kantheon/protocol/openid-connect/token',data=body)
with urllib.request.urlopen(request,context=context,timeout=30) as response:
    access=json.load(response)['access_token']
part=access.split('.')[1]
claims=json.loads(base64.urlsafe_b64decode(part+'='*(-len(part)%4)))
assert claims['preferred_username']=='marketa' and claims['azp']=='hebe'
assert 'hartland-sales-managers' in claims['groups'] and 'process-engine-rest' in claims['aud']
def get(path):
    request=urllib.request.Request('http://process-engine.process-engine.svc/engine-rest'+path,headers={'Authorization':'Bearer '+access})
    with urllib.request.urlopen(request,timeout=30) as response: return json.load(response)
rows=[]
for identity in p['instances']:
    history=get('/history/process-instance/'+urllib.parse.quote(identity,safe=''))
    tasks=get('/task?'+urllib.parse.urlencode({'processInstanceId':identity,'active':'true'}))
    assert history['id']==identity
    rows.append({'id':identity,'state':history['state'],'activeTasks':len(tasks)})
print(json.dumps(rows))
'''


def engine_states(record):
    steps=record['steps']
    ids=[steps[n]['instanceId'] for n in ('card_read','console_outcome','claimed_elsewhere','forward_start')]
    result=probe.kubectl('-n','kantheon','get','secret','hebe-marketa','-o','json')
    if result.returncode:
        raise RuntimeError('existing OBO seed unavailable')
    data=json.loads(result.stdout)['data']
    def key(name):
        return base64.b64decode(data[name]).decode()
    result=probe.kubectl('-n','auth','get','secret','root-ca-secret','-o','json')
    if result.returncode:
        raise RuntimeError('public CA unavailable')
    ca=base64.b64decode(json.loads(result.stdout)['data']['tls.crt']).decode()
    return probe.run(ENGINE,{'client':key('keycloak-client-id'),'secret':key('keycloak-client-secret'),
        'seed':key('keycloak-offline-token'),'ca':ca,'instances':ids},stage='s36-history')


def verify(record, human):
    if human[0] != 'PASS':
        return human
    try:
        since = walk_record.time_value(record['startedAt']) - timedelta(minutes=1)
        data = fixture.console('/api/receipts?' + urllib.parse.urlencode({'since': since.isoformat(), 'limit': 500}))
        receipts = json.loads(data['receipts']) if isinstance(data['receipts'], str) else data['receipts']
        state=stores()
        state['instances']=engine_states(record)
        verdict, detail = assess(record, state, receipts)
        return verdict, human[1] + '; ' + detail
    except Exception as error:
        return 'OPEN', 'live: post-walk observation unavailable (' + type(error).__name__ + ')'
