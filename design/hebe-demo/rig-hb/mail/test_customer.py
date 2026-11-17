"""Customer-only identity, verified TLS, non-mutating reads and fail-closed rows."""
import importlib.util
from pathlib import Path
import ssl
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent


def load(name):
    spec = importlib.util.spec_from_file_location('he_s36_' + name, HERE / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


customer, rows = load('customer'), load('rows')


class Customer(unittest.TestCase):
    def setUp(self):
        self.tls = patch.object(customer.ssl, 'create_default_context', return_value=ssl.create_default_context())
        self.context = self.tls.start()
        self.addCleanup(self.tls.stop)
        self.mailbox = customer.CustomerMailbox('private-password', 'public-ca')

    def test_only_customer_can_send_and_tls_precedes_login(self):
        message = customer.complaint('Objednávka 4711 dorazila poškozená.', 'cert-20261117-001')
        self.assertEqual(message['From'], customer.CUSTOMER)
        self.assertEqual(message['To'], customer.MARKETA)
        self.assertIn('4711', message.get_content())
        self.assertIn('zakaznik.example>', message['Message-ID'])
        with patch.object(customer.smtplib, 'SMTP') as factory:
            smtp = factory.return_value
            smtp.__enter__.return_value = smtp
            smtp.send_message.return_value = {}
            result = self.mailbox.send(message)
            self.assertEqual(result['messageId'], message['Message-ID'])
            smtp.login.assert_called_once_with(customer.CUSTOMER, 'private-password')
            names = [c[0] for c in smtp.mock_calls]
            self.assertLess(names.index('starttls'), names.index('login'))
            smtp.starttls.assert_called_once_with(context=self.context.return_value)
            factory.assert_called_once_with(customer.HOST, 587, timeout=15)
            smtp.send_message.assert_called_once_with(message, from_addr=customer.CUSTOMER, to_addrs=[customer.MARKETA])
            del message['From']
            message['From'] = customer.MARKETA
            with self.assertRaises(ValueError):
                self.mailbox.send(message)
        self.context.assert_called_once_with(cadata='public-ca')
        with self.assertRaises(ValueError):
            customer.complaint('text', 'bad\nheader')
        with self.assertRaises(ValueError):
            customer.complaint('text', 'cert-20261117-001', 'outside@example.org')

    def test_customer_read_is_readonly_and_preserves_seen_flags(self):
        raw = b'Message-ID: <reply@hartland.example>\r\nSubject: Re: example\r\nReferences: <root@zakaznik.example>\r\n\r\n'
        with patch.object(customer.imaplib, 'IMAP4') as factory:
            imap = factory.return_value
            imap.select.return_value = ('OK', [b'1'])
            imap.uid.side_effect = [('OK', [b'7']), ('OK', [(b'7', raw), b')'])]
            found = self.mailbox.read('cert-20261117-001', '<root@zakaznik.example>')
            self.assertEqual(found[0]['messageId'], '<reply@hartland.example>')
            imap.login.assert_called_once_with(customer.CUSTOMER, 'private-password')
            imap.starttls.assert_called_once_with(ssl_context=self.context.return_value)
            imap.select.assert_called_once_with('INBOX', readonly=True)
            self.assertIn('BODY.PEEK', imap.uid.call_args_list[1].args[2])
            self.assertFalse(imap.store.called)
            self.assertFalse(imap.expunge.called)
            self.assertFalse(imap.close.called)
            imap.logout.assert_called_once()

    def test_protocol_failure_is_not_an_empty_mailbox_or_successful_send(self):
        with patch.object(customer.imaplib, 'IMAP4') as factory:
            imap = factory.return_value
            imap.select.return_value = ('NO', [b'failure'])
            with self.assertRaises(RuntimeError):
                self.mailbox.read('cert-20261117-001', '<root@zakaznik.example>')
            imap.logout.assert_called_once()
        with patch.object(customer.smtplib, 'SMTP') as factory:
            smtp = factory.return_value
            smtp.starttls.side_effect = ssl.SSLError('untrusted peer')
            with self.assertRaises(ssl.SSLError):
                self.mailbox.smtp()
            smtp.login.assert_not_called()
            smtp.close.assert_called_once()

    def test_substrate_probes_send_no_data_and_require_policy_refusal(self):
        with patch.object(self.mailbox, 'smtp') as connect:
            smtp = connect.return_value.__enter__.return_value
            smtp.mail.return_value = (530, b'5.7.1 authentication or sender refused')
            self.assertEqual(set(self.mailbox.substrate()), {'R1', 'R2'})
            self.assertEqual([c.args[0] for c in connect.call_args_list], [False, True])
            smtp.send_message.assert_not_called()
            smtp.data.assert_not_called()
            for response in [(250, b'OK'), (451, b'4.7.1 temporarily unavailable')]:
                smtp.mail.return_value = response
                with self.assertRaises(RuntimeError):
                    self.mailbox.substrate()


class RowTable(unittest.TestCase):
    def test_every_required_row_needs_evidence_and_no_na_or_typos_pass(self):
        self.assertEqual(rows.exit_code(rows.table({})), 3)
        good = {name: ('PASS', 'observed live') for name in rows.ROWS}
        self.assertEqual(rows.exit_code(rows.table(good)), 0)
        for name in rows.ROWS:
            missing = dict(good)
            del missing[name]
            self.assertEqual(rows.exit_code(rows.table(missing)), 3)
        bad = {**good, 'R2': ('FAIL', 'sender accepted')}
        self.assertEqual(rows.exit_code(rows.table(bad)), 1)
        for invalid in [{**good, 'R3-person': ('N/A', 'human walk absent')},
                        {**good, 'typo': ('PASS', 'unknown')}]:
            with self.assertRaises(ValueError):
                rows.table(invalid)


if __name__ == '__main__':
    unittest.main()
