# Hebe P2 engine certification — bp-dsk

Agent-owned execution of the approved S2.3d list in `project/kantheon/features/hebe/tasks/`.
This profile certifies the web engine walk. The unchanged full P1 profile still checks
the scheduled Monday brief and phone; neither is certified by an engine-profile PASS.

## Prerequisites and deployment

S2.3c/c1 exited at Olymp `b5da44d`: Hebe `0.11.10`, source
`ad971d35c025ea94812dda54afa637bf235540a2`, app/init digest
`sha256:0a4316a147f7fcdc3c35a7200daa29cf9166dc2441280b15e02c090b867b89d6`.
Engine CIB seven Run4 2.2.0; REST Service port 80 at
`http://process-engine.process-engine.svc/engine-rest`. Public issuer:
`https://keycloak.192-168-1-38.nip.io/realms/kantheon`.

The existing `bora` operator must be signed in at
`https://process.192-168-1-38.nip.io/`. The deployment command also requires that
operator's current personal bearer in a private `TTR_BEARER_FILE` (0600), or the
existing `TTR_BEARER` environment variable. Never put either credential in argv,
Git, a PR, or chat. The engine validates its signature, expiry and authorization;
the helper additionally refuses a bearer whose username is not `bora`.

```sh
just hebe-engine-deploy --olymp ../olymp
```

The helper creates a uniquely named short-lived Python probe in `process-engine`,
always using `--context bp-dsk`. Sensitive payload travels through exec stdin only;
no credential-bearing pod command, environment, volume, log or persistent resource.
It posts the saved `hebe-p2-cert.bpmn` as multipart `/deployment/create`, with duplicate
filtering and deploy-changed-only. It then executes the existing Olymp PE-P0
`provision-authorizations.py` unchanged. That reconciler provides the fixture's static
sales-manager start/read grants; this stage adds no ad-hoc wildcard grants.
The scratch pod is removed in `finally`, including on authentication failure.

The saved fixture derives from the reviewed Hebe component fixture: Czech names,
one enum outcome and optional string note, static `hartland-sales-managers` starter
and task candidates, twelve fixed JSON detail rows from a JUEL string expression,
30-day history TTL, async-after start, no script engine.

## Rig

Use the public cluster CA, retaining normal hostname verification. Keep its temporary
copy and working output under the code worktree's ignored `build/`, not `project/`.
The following are agent commands; Bora supplies only private credentials when needed.

```sh
mkdir -p build/he-s23d
kubectl --context bp-dsk -n auth get secret root-ca-secret \
  -o 'jsonpath={.data.tls\.crt}' | base64 --decode > build/he-s23d/root-ca.crt
export HEBE_VERIFY_CA_FILE="$PWD/build/he-s23d/root-ca.crt"
# HEBE_VERIFY_PASSWORD: the existing persona password, supplied privately, never argv.
just hebe-verify --profile engine
just hebe-verify-test
```

`just hebe-verify` without arguments retains the existing full P1 profile. The explicit
engine profile fixes bp-dsk hosts/context and exact released app/init image identity,
checks full pod readiness, OBO, receipt key, registry/nonrouting, console login as
Markéta and refusal of Maya/forged identity, receipt chain and durability, six applicable
doctor rows, authenticated deduplicated open-task count, and a real direct-header
isolation probe from another namespace. Only the two phone rows can be N/A, after
checking live configuration is Telegram-disabled and engine delivery is web-only.
Missing/failed engine or authentication checks fail; absent persona credentials remain
SKIP and exit 3, never a PASS. Legacy filesystem doctor rows do not represent PG-store
durability; the required `State durability` row must explicitly say both stores are PG.

Default engine state is `~/.config/hebe-verify/bp-dsk/engine/marketa.json`, separate
from the full P1 profile. `HEBE_VERIFY_STATE` is the full profile's original filename;
for engine it is a state-root override, under which `bp-dsk/engine/marketa.json` is used.
The complete live rig must pass twice, before and after the walk/restart/outage.

## Three controlled instances

Use the real console as Markéta, `https://hebe.192-168-1-38.nip.io/`. Save identifiers
and redacted outcomes in the PR description. Do not fabricate PASS from API-only reads.

1. Send `spusť kontrolu uvolnění pro 4711`. Require an explicit confirmation; send
   `ano`. Require one waiting/card response, ten detail rows and `+ 2 more`. Open its
   actual task and instance links in Tasklist/Cockpit. Send `schválit 4711`; verify
   history COMPLETED and one answer receipt, no second card/submission.
2. Start through the same confirmation flow. Claim the task in Tasklist as `bora`;
   require one handled-elsewhere line. Complete this controlled task as Bora in the
   existing UI; require no Hebe answer receipt for it.
3. Start through the same flow. With its card shown, restart only deployment/hebe;
   require the card remains single. During this same open task, stop only the engine
   deployment for three minutes, with a `finally`/EXIT handler restoring its original
   replica count even on failure. Do not alter GitOps or pins. Require one unreachable
   line and one recovery line. Send `zamítnout 4711 protože chybí doklad`; require
   completion with the rejection/note durable in history.

Live URL templates from the released configuration:
`{web}/#/seven/auth/task/{task}` and
`{web}/#/seven/auth/processes/instance/{instance}`, where
`web=https://process.192-168-1-38.nip.io/webapp`.
Across these three instances require exactly three `engine.start`, two `engine.answer`
receipts, verified chain and a second green rig. No ready PR before the whole live DONE.
Any producer/pin/contract need is a scope stop for the planner, not a repair here.

Cleanup is separate and only after retaining the reviewed history evidence:
`just hebe-engine-deploy --cleanup --olymp ../olymp`. It removes only deployments named
`hebe-p2-cert`, refuses any active instance, and never cascades. Scratch probes are
already cleaned automatically; credentials remain caller-owned. Remove stage `build/`
artifacts after merge, as Rule 6 requires.
