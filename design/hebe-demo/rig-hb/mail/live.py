"""Run customer-only helpers in a disposable bp-dsk pod; sensitive input via stdin."""
import argparse
import base64
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'engine'))
import probe


def secret(namespace, name, key):
    result = probe.kubectl('-n', namespace, 'get', 'secret', name, '-o', 'json')
    if result.returncode:
        raise RuntimeError('required certification credential/CA unavailable: ' + name)
    return base64.b64decode(json.loads(result.stdout)['data'][key]).decode()


def run(operation, **arguments):
    if operation not in ('send', 'read', 'substrate'):
        raise ValueError('unknown customer operation')
    payload = {**arguments, 'operation': operation,
               'password': secret('middleware', 'mail-customer-password', 'password'),
               'ca': secret('auth', 'root-ca-secret', 'tls.crt')}
    return probe.run((HERE / 'customer.py').read_text(), payload, namespace='kantheon', stage='s36-mail')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['substrate', 'read', 'send'])
    parser.add_argument('--run')
    parser.add_argument('--message-id')
    parser.add_argument('--recipient', choices=['marketa@hartland.example', 'hebe-marketa@hartland.example'])
    parser.add_argument('--fixture', type=Path)
    args = parser.parse_args()
    if args.operation != 'substrate' and not args.run:
        parser.error('--run is required for read/send')
    if args.operation == 'read' and not args.message_id:
        parser.error('--message-id is required for read')
    if args.operation == 'send' and (not args.fixture or not args.recipient):
        parser.error('--fixture and --recipient are required for send')
    result = run(args.operation, run=args.run, messageId=args.message_id, recipient=args.recipient,
                 text=args.fixture.read_text() if args.fixture else None)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, RuntimeError, OSError) as error:
        raise SystemExit('customer helper failed: ' + type(error).__name__) from None
