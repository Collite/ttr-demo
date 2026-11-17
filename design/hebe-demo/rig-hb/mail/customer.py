"""Customer-only SMTP/IMAP helpers; run inside bp-dsk, with verified STARTTLS.

There is deliberately no login-user or From override. The sole sender exception is
the R2 negative envelope probe, which never sends DATA. Passwords come from stdin
or the caller's memory, never argv or a result. Reading never changes Seen flags.
"""
import email
from email import policy
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
import imaplib
import json
import re
import smtplib
import ssl
import sys

CUSTOMER = 'jana.kralova@zakaznik.example'
MARKETA = 'marketa@hartland.example'
HEBE = 'hebe-marketa@hartland.example'
HOST = 'mail.middleware.svc'


def complaint(text, run, recipient=MARKETA):
    if not re.fullmatch(r'[a-z0-9-]{8,80}', run):
        raise ValueError('use a unique lowercase certification run id (8–80 characters)')
    if recipient not in (MARKETA, HEBE):
        raise ValueError('certification sends only to Markéta or Hebe')
    message = EmailMessage(policy=policy.SMTP)
    message['From'] = CUSTOMER
    message['To'] = recipient
    message['Subject'] = f'[HE-S36 {run}] Reklamace objednávky 4711'
    message['Date'] = formatdate(localtime=False)
    message['Message-ID'] = make_msgid(idstring='he-s36-' + run, domain='zakaznik.example')
    message['X-Hebe-Certification'] = run
    message.set_content(text, charset='utf-8')
    return message


class CustomerMailbox:
    def __init__(self, password, ca):
        if not password:
            raise ValueError('customer password is required')
        self.password = password
        self.context = ssl.create_default_context(cadata=ca)

    def smtp(self, authenticate=True):
        smtp = smtplib.SMTP(HOST, 587, timeout=15)
        try:
            smtp.ehlo()
            smtp.starttls(context=self.context)
            smtp.ehlo()
            if authenticate:
                smtp.login(CUSTOMER, self.password)
            return smtp
        except BaseException:
            smtp.close()
            raise

    def send(self, message):
        # Check the parsed address count too; duplicate fields or display-name tricks
        # cannot turn this helper into a different persona's sender.
        if message.get_all('From') != [CUSTOMER] or message.get_all('To') not in ([MARKETA], [HEBE]):
            raise ValueError('customer sender and one certification recipient required')
        with self.smtp() as smtp:
            refused = smtp.send_message(message, from_addr=CUSTOMER, to_addrs=[message['To']])
            if refused:
                raise RuntimeError('certification recipient refused')
        return {'messageId': message['Message-ID'], 'subject': message['Subject'], 'to': message['To']}

    def read(self, run, root_message_id):
        """Read only headers of customer mail; correlate a reply by subject or References."""
        if not re.fullmatch(r'[a-z0-9-]{8,80}', run) or not root_message_id:
            raise ValueError('run and original Message-ID required')
        imap = imaplib.IMAP4(HOST, 143, timeout=15)
        try:
            imap.starttls(ssl_context=self.context)
            imap.login(CUSTOMER, self.password)
            status, _ = imap.select('INBOX', readonly=True)
            if status != 'OK':
                raise RuntimeError('customer INBOX unavailable')
            status, values = imap.uid('SEARCH', None, 'ALL')
            if status != 'OK':
                raise RuntimeError('customer search failed')
            uids = values[0].split()
            if len(uids) > 500:
                raise RuntimeError('customer mailbox exceeds bounded certification read')
            replies = []
            for uid in uids:
                status, values = imap.uid('FETCH', uid, '(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID SUBJECT IN-REPLY-TO REFERENCES FROM)])')
                if status != 'OK':
                    raise RuntimeError('customer header read failed')
                raw = b''.join(v[1] for v in values if isinstance(v, tuple))
                if not raw:
                    raise RuntimeError('missing customer message headers')
                message = email.message_from_bytes(raw, policy=policy.default)
                references = re.findall(r'<[^<>\s]+>', str(message.get('References', '')) + ' ' + str(message.get('In-Reply-To', '')))
                if f'[HE-S36 {run}]' in str(message.get('Subject', '')) or root_message_id in references:
                    replies.append({'uid': uid.decode('ascii'), 'messageId': str(message.get('Message-ID', '')),
                                    'subject': str(message.get('Subject', '')), 'references': references})
            return replies
        finally:
            imap.logout()

    def substrate(self):
        """R1/R2 refused envelopes; no DATA, message, relay or mailbox write."""
        results = {}
        for row, authenticated, sender in [('R1', False, CUSTOMER), ('R2', True, MARKETA)]:
            with self.smtp(authenticated) as smtp:
                code, response = smtp.mail(sender)
                if code not in (503, 530, 550, 553, 554) or b'5.7.' not in response:
                    raise RuntimeError(row + ' did not refuse the forbidden envelope with a policy error')
                results[row] = {'code': code, 'dataSent': False}
        return results


def main():
    try:
        payload = json.load(sys.stdin)
        mailbox = CustomerMailbox(payload['password'], payload['ca'])
        if payload['operation'] == 'send':
            result = mailbox.send(complaint(payload['text'], payload['run'], payload['recipient']))
        elif payload['operation'] == 'read':
            result = mailbox.read(payload['run'], payload['messageId'])
        elif payload['operation'] == 'substrate':
            result = mailbox.substrate()
        else:
            raise ValueError('unknown customer operation')
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as error:
        # Protocol exception strings may contain authentication details. Report only type.
        print(json.dumps({'error': type(error).__name__}))
        return 1


if __name__ == '__main__':
    sys.exit(main())
