"""Validate explicit human observations; never infer a walk from healthy channels."""
from datetime import datetime, timezone, timedelta
import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('he_walk_engine', HERE.parent / 'engine/profile.py')
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)
SOURCE = 'cc3b5d8d0e35cd56a06feaff7a9db85535bae7e6'
FIELDS = {
    'sso': ('at', 'mailbox'),
    'card_read': ('at', 'rootMessageId', 'threadSubject', 'taskId', 'instanceId', 'taskLink', 'detailRows', 'moreRows', 'replyInstructions'),
    'card_reply': ('at', 'rootMessageId', 'threadSubject', 'taskId', 'instanceId', 'receiptId', 'command', 'answeredBy', 'instanceState'),
    'console_outcome': ('at', 'rootMessageId', 'threadSubject', 'taskId', 'instanceId', 'receiptId'),
    'claimed_elsewhere': ('at', 'rootMessageId', 'threadSubject', 'taskId', 'instanceId', 'claimant', 'handledElsewhere', 'fixtureCompleted'),
    'free_text': ('at', 'rootMessageId', 'threadSubject', 'notUnderstood', 'noModelCall', 'modelEvidenceRef'),
    'forward_start': ('at', 'rootMessageId', 'threadSubject', 'proposalId', 'instanceId', 'receiptId', 'confirmation', 'instruction', 'ttr_note', 'ttr_source', 'fixtureCompleted'),
    'bare_forward': ('at', 'rootMessageId', 'threadSubject', 'threeWayQuestion', 'replyCommand', 'closed', 'noInstance'),
}


def deployment(baseline, fingerprint):
    if not fingerprint:
        return None
    return {'hebeImage': engine.IMAGE, 'hebeDigest': engine.DIGEST, 'hebeSource': SOURCE,
            'jamesImage': baseline['jamesImage'], 'webmailImage': baseline['webmailImage'],
            'admissionFingerprint': fingerprint}


def time_value(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('timestamps must include timezone')
    return parsed


def template(run, current):
    return {'actor': 'marketa', 'runId': run, 'deployment': current,
            'startedAt': None, 'completedAt': None,
            'steps': {name: {**dict.fromkeys(fields), 'result': 'NOT_PERFORMED'}
                      for name, fields in FIELDS.items()}}


def validate(record, run, current, now=None):
    if record is None:
        return 'OPEN', 'human evidence: fresh Markéta webmail walk not recorded'
    if not run or current is None:
        return 'OPEN', 'human evidence: certification run/current admission baseline required'
    if record.get('runId') != run or record.get('deployment') != current:
        return 'FAIL', 'human evidence: deployment or certification run mismatch'
    if record.get('actor') != 'marketa':
        return 'FAIL', 'human evidence: required actor is Markéta'
    try:
        begin, end = time_value(record['startedAt']), time_value(record['completedAt'])
        now = now or datetime.now(timezone.utc)
        if begin > end or end > now + timedelta(minutes=5):
            raise ValueError('invalid time interval')
        steps = record['steps']
        for name, required in FIELDS.items():
            step = steps[name]
            if step.get('result') != 'PASS' or any(k not in step or step[k] is None or step[k] == '' for k in required):
                raise ValueError('incomplete action')
            if not begin <= time_value(step['at']) <= end:
                raise ValueError('action outside walk interval')
        card, reply = steps['card_read'], steps['card_reply']
        if steps['sso']['mailbox'] != 'marketa@hartland.example':
            raise ValueError('wrong mailbox')
        if (card['detailRows'], card['moreRows'], card['replyInstructions']) != (10, 2, True):
            raise ValueError('card details/instructions missing')
        if not card['taskLink'].endswith('/' + card['taskId']):
            raise ValueError('task link mismatch')
        if any(card[k] != reply[k] for k in ['rootMessageId', 'threadSubject', 'taskId', 'instanceId']):
            raise ValueError('reply crossed card threads')
        if (reply['command'], reply['answeredBy'], reply['instanceState']) != ('schválit', 'marketa', 'COMPLETED'):
            raise ValueError('mail answer not completed by Markéta')
        cards = [card, steps['console_outcome'], steps['claimed_elsewhere']]
        for field in ('taskId', 'instanceId', 'rootMessageId'):
            if len({c[field] for c in cards}) != 3:
                raise ValueError('controlled instances/threads not distinct')
        claimed, free = steps['claimed_elsewhere'], steps['free_text']
        if claimed['claimant'] != 'bora' or claimed['handledElsewhere'] is not True or claimed['fixtureCompleted'] is not True:
            raise ValueError('handled elsewhere observation incomplete')
        if free['notUnderstood'] is not True or free['noModelCall'] is not True:
            raise ValueError('deterministic reply evidence incomplete')
        forward, bare = steps['forward_start'], steps['bare_forward']
        if forward['confirmation'] != 'ano' or forward['fixtureCompleted'] is not True:
            raise ValueError('forward confirmation/cleanup incomplete')
        if forward['instruction'] not in forward['ttr_note'] or '4711' not in forward['ttr_note'] or 'Jana' not in forward['ttr_note'] or not forward['ttr_source'].startswith('mail:<'):
            raise ValueError('forward note/source not observed')
        if (bare['threeWayQuestion'], bare['replyCommand'], bare['closed'], bare['noInstance']) != (True, '3', True, True):
            raise ValueError('bare forward not closed without start')
    except (KeyError, TypeError, ValueError, AttributeError):
        return 'OPEN', 'human evidence: incomplete or inconsistent action/result/reference record'
    return 'PASS', 'human evidence: complete Markéta walk bound to run ' + run + ' and current deployment'
