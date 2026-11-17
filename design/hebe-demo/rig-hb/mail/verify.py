"""Mail additions to the engine rig; missing evidence remains OPEN, never PASS."""
import json
import os
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import edge_login
import live
import rows
import qualification
import walk_record
import fixture
import post_walk


def assess(ready, status, doctor, substrate, qualified=None, human=None, stranger=None):
    checks = {c['name']: c for c in ready.get('checks', [])}
    observation = {}
    email = [c for c in status.get('channels', []) if c.get('name') == 'email']
    registered = (checks.get('channels', {}).get('ok') is True and
                  re.search(r'\bemail=Up\b', checks.get('channels', {}).get('detail', '')) is not None and
                  len(email) == 1 and email[0].get('health') == 'Up')
    observation['mail-channels'] = ('PASS' if registered else 'FAIL',
                                    'live: full readiness names email=Up and console email health must both pass')
    delivery = checks.get('delivery', {}).get('ok') is True
    observation['mail-delivery'] = ('PASS' if delivery else 'FAIL', 'live: full readiness delivery: ' + str(checks.get('delivery', {}).get('detail')))
    for name in ['R1', 'R2']:
        value = substrate.get(name, {})
        ok = value.get('code') in (503, 530, 550, 553, 554) and value.get('dataSent') is False
        observation[name] = ('PASS' if ok else 'FAIL', 'live: forbidden envelope refused without DATA: ' + str(value.get('code')))
    mail = next((c for c in doctor.get('checks', []) if c['name'] == 'mail'), {})
    ok = mail.get('status') == 'pass' and checks.get('mail', {}).get('ok') is True
    observation['R3-service'] = ('PASS' if ok else 'FAIL', 'live: Hebe doctor: ' + str(mail.get('message', 'missing mail check')))
    observation['R3-person'] = human or ('OPEN', 'human evidence: fresh Markéta SSO/read/Reply record required')
    observation['R3-negative'] = qualified[:2] if qualified else ('OPEN', 'inherited qualification: current comparison required')
    observation['mail-stranger'] = stranger or ('OPEN', 'live: T3 dropped receipt and two customer mailbox polls not performed yet')
    observation['mail-threads'] = human or ('OPEN', 'human evidence: complete T4–T6 thread observations required')
    return rows.table(observation)


def main():
    try:
        ready = json.loads(os.environ['HEBE_VERIFY_MAIL_READY'])
        text = os.environ['HEBE_VERIFY_MAIL_DOCTOR']
        match = re.search(r'\{\s*"checks"\s*:', text)
        if not match:
            raise ValueError('doctor report missing')
        doctor = json.loads(text[match.start():])
        password = os.environ.get('HEBE_VERIFY_PASSWORD', '')
        if not password:
            print('OPEN\tmail-channels\tHEBE_VERIFY_PASSWORD required for authenticated console status')
            return 3
        response = edge_login.sign_in('hebe.192-168-1-38.nip.io', 'marketa', password, '/api/status', None, 1_000_000)
        if response.get('status') != 200:
            raise RuntimeError('authenticated console status unavailable')
        qualified = qualification.verify()
        baseline = json.loads(qualification.BASELINE.read_text())
        current = walk_record.deployment(baseline, qualified[2])
        state = fixture.load()
        run = os.environ.get('HEBE_VERIFY_MAIL_RUN') or (state or {}).get('runId')
        path = os.environ.get('HEBE_VERIFY_MAIL_WALK_FILE')
        record = json.loads(Path(path).read_text()) if path else None
        human = walk_record.validate(record, run, current)
        stranger = fixture.verify(state, run, current)
        result = assess(ready, json.loads(response['body']), doctor, live.run('substrate'), qualified, human, stranger)
        threads = post_walk.verify(record, human)
        result = [(name, *threads) if name == 'mail-threads' else (name, verdict, detail)
                  for name, verdict, detail in result]
        for name, verdict, detail in result:
            print(verdict + '\t' + name + '\t' + detail.replace('\t', ' ').replace('\n', ' '))
        return rows.exit_code(result)
    except Exception as error:
        print('FAIL\tmail-profile\tobservation failed: ' + type(error).__name__)
        return 1


if __name__ == '__main__':
    sys.exit(main())
