# Hebe mail certification rig — S3.6

This stage adds customer-only mail helpers to the existing engine rig. It retains
the exact S3.5b Hebe `0.11.14` image/digest, engine, OBO, admission, receipts and
isolation checks. No dependency pin, producer code, deployment or realm is changed.

`just hebe-verify --profile mail` fixes context/hosts to bp-dsk and keeps every
engine check. Registration requires named `email=Up` in full readiness and the
same runtime channel in authenticated console status. It repeats R1/R2 refused
envelopes and the application's active SMTP/IMAP doctor on every run.

HE-D-33 distinguishes three evidence kinds in the output:

- **live:** runtime registration/delivery/engine, customer-only R1/R2, application
  doctor, and the stranger receipt/two mailbox polls once T3 is performed;
- **inherited qualification:** negative-token cases mapped in
  `qualification-baseline.json` to accepted Olymp#304/#305/#307. Wrong audience
  has production-config local21/21 provenance; absent audience, malformed,
  engine-only and naturally expired cases also have live19/19 provenance. Foreign
  signing-key rejection is the accepted local JWT-module unit qualification71,
  through the same JwtTokenVerifier used by OidcJwtTokenVerifier, not a newly run
  foreign-issuer SASL case. No historical fingerprint is invented: mounted-input
  hashes derive directly from accepted immutable Git revisions;
- **human:** an explicit current-run/deployment record of fresh Markéta SSO,
  own-mailbox card read and actual Reply/Forward actions. Channel health does not
  substitute for that record. T4–T6 remain human actions.

Each profile run compares actual James image/mounted auth+TLS files, Roundcube
image/effective OAuth+STARTTLS values/public CA and Keycloak mail mapper,
optional/default associations, client flags and issuer/JWKS URLs. Keycloak admin
GETs use the existing credential only in local process memory; the session logs
out in finally. No realm write, credential file, pod credential copy or additional
mail identity is used. The current valid-token doctor still runs separately.

The accepted authored realm is expanded only by two independently checked
Keycloak26.5.1 rules: service-account enablement adds its built-in `service_account`
scope; the groups mapper forces `multivalued=true` on token issuance. Primary-source
links are in the baseline. The current immutable issuer process started Nov7,
before the accepted Nov15 live checks; this is stated as a runtime witness, not a
fabricated old effective-config snapshot. The local qualification's disposable
issuer image is identified separately. All other extra scopes/mappers/config,
issuer/JWKS URLs, substrate/TLS/client changes fail the comparison; missing case
coverage or an unavailable observation stays OPEN. Material drift stops the stage.

**T2 is partial:** only R3-person/mail-stranger/mail-threads may still be OPEN.
The command continues to exit3 while any row is OPEN. `rows.pre_walk` checks this
explicit partial gate; it is never a complete-profile PASS. T7 requires two runs
with no FAIL/OPEN. Only the two disabled Telegram rows can be N/A.

The agent prepares a non-PASS template with `walk_record.template(run, deployment)`
under ignored build/. Set `HEBE_VERIFY_MAIL_RUN` to that unique run and
`HEBE_VERIFY_MAIL_WALK_FILE` to the completed working JSON record after the walk.
The agent records the person's observations/references, not credentials. The rig
checks actor/time, current exact Hebe/mail/webmail identities and admission hash,
action completeness, distinct card/root/task identities, command/outcome/note
semantics and matching run. Missing/inconsistent records stay non-PASS; changed
deployment/run fails. Two final runs can reference the same completed walk while
rechecking live rows and admission. Results/references go in the PR description;
no walk proof file is added to project/.

The post-walk thread row also re-reads `mail_threads` and `engine_tasks` in a
`BEGIN READ ONLY` transaction on the existing bp-dsk Postgres primary. It requires
the recorded roots/kinds/task/proposal references to remain closed and consistent.
Authenticated console receipts must match four certification starts and the
performed answers. The existing Markéta OBO seed/verified-CA probe pattern checks
each controlled instance through the contracted engine history and active-task
GETs: all four must be COMPLETED with zero active tasks. A Tasklist claim alone
does not prove cleanup. Record the forwarded fixture's `cleanupTaskId` and, if its
cleanup used Hebe rather than Tasklist, `cleanupReceiptId`. These observations
repeat on both final profile runs; unavailable observations remain OPEN.

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
just hebe-mail-fixture --run he-s36-<unique-id>
just hebe-mail read --run he-s36-<unique-id> --message-id '<returned-message-id>'
```

The fixture command checks the current admission baseline and console access,
then sends the complaint once to Markéta and once to Hebe. It checkpoints before
each send in `build/he-s36/mail-state.json`; an uncertain send stops for inspection
and is never blindly repeated. The same run/deployment can resume completed sends.
It records two empty customer polls at least twenty seconds apart and the exact
body-free `mail.dropped` receipt. Subsequent profiles load this checkpoint (override
with `HEBE_VERIFY_MAIL_STATE`), repeat the customer read and receipt lookup, and
require the current run/deployment to match. Human steps still remain OPEN.

Send results contain only the Message-ID, subject and recipient; retain their
references in the PR. Each send has a unique Message-ID. Customer reads use
read-only INBOX selection and `BODY.PEEK` headers; they never set Seen, expunge or
delete mail. R1/R2 issue MAIL envelopes only, never DATA. Authentication or protocol
errors fail rather than masquerading as an empty mailbox or a refused sender.

`WALK.md` is the human walk sheet; fill its results in the PR after execution.
`complaint-4711.txt` is Jana's fixed Czech fixture. No mail or walk action is
performed by running `just hebe-verify-test`; the test suite mocks all transports.
