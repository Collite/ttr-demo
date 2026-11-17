# Hebe mail certification rig — S3.6

This stage adds customer-only mail helpers to the existing engine rig. It retains
the exact S3.5b Hebe `0.11.14` image/digest, engine, OBO, admission, receipts and
isolation checks. No dependency pin, producer code, deployment or realm is changed.

`just hebe-verify --profile mail` fixes context and hosts to bp-dsk, checks email
registration using full readiness plus authenticated console status, delivery,
R1/R2 refused envelopes and the service's active SMTP/IMAP doctor. It currently
leaves unperformed walk/stranger rows OPEN. Its first live run failed the
email-registration row: full readiness says only `up`, while authenticated console
status returns `channels: []`. No configured-channel inference substitutes for
observing registration; the stage stops for planner triage. The permitted R3 token-policy evidence
method remains a clarification gate. An OPEN row exits 3 and cannot certify the
stage. The two disabled Telegram rows alone are N/A.

Use the existing public CA as described in `../engine/README.md`. The persona
password is supplied privately as `HEBE_VERIFY_PASSWORD`, never on the command
line. Keep outputs under the worktree's `build/he-s36/`. The helper reads the
existing customer password Secret (vault key `mail-customer-password`) in memory,
passes it only through exec stdin to a bounded disposable pod in `kantheon`, and
removes that pod in `finally`. It never logs in to another person's mailbox.
SMTP/IMAP both use verified STARTTLS against `mail.middleware.svc`.

Agent-owned helper commands, from this code worktree:

```sh
just hebe-mail substrate
just hebe-mail send --run he-s36-<unique-id> --recipient marketa@hartland.example \
  --fixture design/hebe-demo/rig-hb/mail/complaint-4711.txt
just hebe-mail read --run he-s36-<unique-id> --message-id '<returned-message-id>'
```

The `send` result contains only the Message-ID, subject and recipient; retain it
in ignored working output and the PR. A separate send of the same fixture to
`hebe-marketa@hartland.example` is T3's stranger test. Each send has a unique
Message-ID; do not blindly retry a send whose result was lost. Customer reads use
read-only INBOX selection and `BODY.PEEK` headers; they never set Seen, expunge or
delete mail. R1/R2 issue MAIL envelopes only, never DATA. Authentication or protocol
errors fail rather than masquerading as an empty mailbox or a refused sender.

`WALK.md` is the human walk sheet; fill its results in the PR after execution.
`complaint-4711.txt` is Jana's fixed Czech fixture. No mail or walk action is
performed by running `just hebe-verify-test`; the test suite mocks all transports.
