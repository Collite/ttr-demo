"""T3's two explicit customer fixture sends, checkpointed to prevent blind retries."""
import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
import time
import urllib.parse

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import customer
import edge_login
import live
import qualification
import walk_record

STATE = ROOT / 'build/he-s36/mail-state.json'


def now():
    return datetime.now(timezone.utc).isoformat()


def save(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), 'w') as output:
        json.dump(state, output, ensure_ascii=False, indent=2)
    temporary.replace(path)


def load():
    path = Path(os.environ.get('HEBE_VERIFY_MAIL_STATE', STATE))
    return json.loads(path.read_text()) if path.is_file() else None


def console(path):
    password = os.environ.get('HEBE_VERIFY_PASSWORD', '')
    if not password:
        raise RuntimeError('HEBE_VERIFY_PASSWORD required before fixture sends')
    response = edge_login.sign_in('hebe.192-168-1-38.nip.io', 'marketa', password, path, None, 1_000_000)
    if response.get('status') != 200:
        raise RuntimeError('authenticated console read unavailable')
    return json.loads(response['body'])


def receipts(state):
    start = walk_record.time_value(state['stranger']['sentAt']) - timedelta(minutes=1)
    data = console('/api/receipts?' + urllib.parse.urlencode({'since': start.isoformat(), 'limit': 500}))
    return json.loads(data['receipts']) if isinstance(data['receipts'], str) else data['receipts']


def drop(rows, message_id):
    matches = []
    for r in rows:
        if r.get('tool') == 'mail.dropped' and r.get('turnId') == message_id:
            args = json.loads(r['argsRedacted'])
            if (set(args) == {'messageId', 'sender', 'reason'} and
                r.get('sessionId') == 'email' and r.get('ok') is True and
                args.get('messageId') == message_id and args.get('sender') == customer.CUSTOMER and
                args.get('reason') == 'sender is not the bound user'):
                matches.append(r)
    return matches[0] if len(matches) == 1 else None


def assess(state, run, deployment, recent, replies):
    if state is None:
        return 'OPEN', 'live: T3 fixture/drop/two polls not performed'
    if state.get('runId') != run or state.get('deployment') != deployment:
        return 'FAIL', 'live: stranger evidence run/deployment mismatch'
    try:
        if state['phase'] != 'complete':
            raise ValueError('incomplete fixture')
        sent, stranger = state['fixture'], state['stranger']
        if sent['to'] != customer.MARKETA or stranger['to'] != customer.HEBE or sent['messageId'] == stranger['messageId']:
            raise ValueError('fixture identities missing')
        polls = state['polls']
        if len(polls) < 2 or any(p['replies'] != 0 for p in polls):
            raise ValueError('two empty mailbox polls required')
        start = walk_record.time_value(stranger['sentAt'])
        for p in polls:
            if walk_record.time_value(p['at']) < start + timedelta(seconds=20):
                raise ValueError('poll interval not observed')
            start = walk_record.time_value(p['at'])
        receipt = drop(recent, stranger['messageId'])
        if receipt is None or receipt['seq'] != state['receiptSeq']:
            raise ValueError('matching dropped receipt required')
        if replies:
            return 'FAIL', 'live: a customer reply exists for the stranger fixture'
    except (KeyError, ValueError, TypeError):
        return 'OPEN', 'live: incomplete stranger/drop/two-poll evidence'
    return 'PASS', 'live: mail.dropped receipt seq' + str(receipt['seq']) + '; two spaced empty polls + fresh customer read'


def verify(state, run, deployment):
    if state is None:
        return 'OPEN', 'live: T3 fixture/drop/two polls not performed'
    if not run or deployment is None:
        return 'OPEN', 'live: current certification run/admission baseline required'
    try:
        replies = live.run('read', run=run, messageId=state['stranger']['messageId'])
        return assess(state, run, deployment, receipts(state), replies)
    except Exception as error:
        return 'OPEN', 'live: stranger observation unavailable (' + type(error).__name__ + ')'


def prepare(run, path):
    # Validate the run and console access before any DATA is sent.
    customer.complaint('validation only', run)
    console('/api/status')
    qualified = qualification.verify()
    if qualified[0] != 'PASS':
        raise RuntimeError('current admission comparison must pass before sends')
    deployment = walk_record.deployment(json.loads(qualification.BASELINE.read_text()), qualified[2])
    state = json.loads(path.read_text()) if path.is_file() else {'runId': run, 'deployment': deployment, 'createdAt': now(), 'polls': [], 'phase': 'preparing'}
    if state['runId'] != run or state['deployment'] != deployment:
        raise RuntimeError('existing fixture belongs to another run/deployment; no resend')
    for name, recipient in [('fixture', customer.MARKETA), ('stranger', customer.HEBE)]:
        if name in state:
            if state[name].get('pending'):
                raise RuntimeError('uncertain prior send; inspect before any retry')
            continue
        state[name] = {'pending': True, 'to': recipient, 'sentAt': now()}
        save(path, state)
        sent_at = state[name]['sentAt']
        result = live.run('send', text=(HERE / 'complaint-4711.txt').read_text(), run=run, recipient=recipient)
        state[name] = {**result, 'sentAt': sent_at}
        save(path, state)
    while len(state['polls']) < 2:
        time.sleep(25)
        reply = live.run('read', run=run, messageId=state['stranger']['messageId'])
        state['polls'].append({'at': now(), 'replies': len(reply)})
        save(path, state)
        if reply:
            raise RuntimeError('stranger received a reply')
    receipt = drop(receipts(state), state['stranger']['messageId'])
    if receipt is None:
        raise RuntimeError('matching mail.dropped receipt not observed')
    state.update(phase='complete', receiptSeq=receipt['seq'], completedAt=now())
    save(path, state)
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True)
    parser.add_argument('--state', type=Path, default=STATE)
    args = parser.parse_args()
    state = prepare(args.run, args.state)
    print(json.dumps(state, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        raise SystemExit('fixture stopped: ' + type(error).__name__ + '; inspect checkpoint, do not blindly resend') from None
