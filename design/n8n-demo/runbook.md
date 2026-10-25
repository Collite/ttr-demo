# První české workflow — rehearsal target: 8 minutes

**Status:** prepared; live seeding, execution and timed rehearsal remain pending after review/merge.
Use Hartland while it is up. n8n 2.44.6 Community Edition; English UI, Czech demo content.

## Preparation (outside the timed demo)

Use the merged checkout, Azure CLI logged into vault `hartland`, and `kubectl` access to context `hartland`.
The content seed reads `n8n-owner-password` and `pg-hartland-cz-ro` into private temporary files, then removes
those files. `--verify` only reads the owner password; it never reads the PG vault key. Other `--dir`
imports require only credentials referenced by their documents. It does not reset the owner or modify database grants.
Without Azure, supply private mode-0600
files with `--owner-password-file PATH` and `--pg-ro-password-file PATH`.

```sh
just n8n-seed-content
just n8n-seed-content --verify
just n8n-verify --phase 3
```

The seed upserts three named credentials and two workflows. It checks the returned version/checksum and
publishes with `POST /rest/workflows/{id}/activate`; PATCH alone only saves a draft in this n8n version.
The seed resolves Markéta’s personal project first; same-named objects in other projects are counted and ignored.
An archived example stays archived and a fresh copy is created. A repeated seed restores the reviewed graph
without duplicates. Publication enables the daily
07:00 Europe/Prague schedule and production webhook; it does not manually fire the sales query or send a test mail.

The first import generates a random webhook key in
`<state-home>/hartland-n8n/webhook-echo-key` (private directory, file 0600).
State-home is `XDG_STATE_HOME` only when non-empty and absolute, otherwise `$HOME/.local/state`.
Use `--webhook-key-file PATH` on both seed/verify/rig to override it. Preserve this file privately between rehearsals;
verification needs it because n8n masks secret values even for the owner. If a webhook credential already exists
and the original key file is missing, the seed fails without rotating it or overwriting content. Recover the
original file before rerunning; changing machines requires transferring that file privately. Never paste it into
chat, commit it, or put it in a shell command argument/environment value. Do not enable shell or HTTP tracing.

`--verify` checks the portable graph, credential IDs, settings and published version, refuses an unauthenticated
webhook request, then sends one small authenticated echo request. It creates an echo execution, but never sends a
sales-summary mail or changes credentials/workflows. V10 delegates to this verifier. V11 stays pending for P4.

The node credentials are `hartland-cz-pg` (read-only `hartland_cz_readonly` role), `mailpit-smtp` (internal port 25,
no authentication/TLS/STARTTLS), and `webhook-echo-key` (header auth). The SQL is the existing
`a1-2-revenue-by-channel` run-set oracle over `channel_sales` and `date_dim`, filtered to 2025.

## Demo beats (Czech)

1. **0:00–1:00 — Otevřeme automatizaci.** Open `https://n8n.hartland.collite.cz` and sign in as
   `marketa@hartland.example`, using the vault's `n8n-owner-password` through the authorized password workflow.
   The landing's n8n link follows in S3.2; until it is deployed, use this direct URL.
   “Tady je místo pro opakovatelné kroky nad stejným světem, ze kterého odpovídá Golem.”
2. **1:00–3:00 — Denní přehled prodeje.** Open the workflow. Explain Schedule → Postgres → Code → Send Email.
   “V sedm ráno přečteme tři souhrnné řádky přes účet, který nemůže měnit data. Ukazujeme referenční rok
   2025, nikoli dnešní prodeje. Z výsledků vznikne česká tabulka.” Confirm the timezone in Settings.
   Press **Execute workflow** once. Wait for success; do not press again while it is running.
3. **3:00–5:00 — Doručený přehled.** Open `https://mail.hartland.collite.cz`, sign in through Keycloak as
   Markéta if prompted. “Pošta neopustila demo. Tady je přehled podle kanálu a částky v korunách.”
   Open the newest `Denní přehled prodeje — <today>` message to `marketa@hartland.example` and show its table.
4. **5:00–7:00 — Příchozí událost.** Run the command below. Show the echo JSON, then the new successful
   execution of `Webhook echo (test)` in n8n. “Stejný princip může začít událostí z jiného systému.”
5. **7:00–8:00 — Vazba na Tatrman.** “Tatrman uzly sem doplníme v další etapě; dnes ukazujeme běžné n8n uzly.”
   Do not present that later integration as already available.

## Echo from a terminal (no key in argv)

This is the safe equivalent of a `curl -X POST … -H 'X-Demo-Key: …'` example. It reads the original private key
file, keeps the header in memory, validates TLS and refuses redirects; only the echoed body is printed.

```sh
python3 - <<'PY'
import json, os, urllib.request
from pathlib import Path
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args): return None
state = os.environ.get('XDG_STATE_HOME', '')
state_home = Path(state) if state and Path(state).is_absolute() else Path.home()/'.local/state'
key_file = state_home/'hartland-n8n/webhook-echo-key'
request = urllib.request.Request('https://n8n.hartland.collite.cz/webhook/echo',
    json.dumps({'ahoj': 'světe'}).encode(),
    headers={'Content-Type': 'application/json', 'X-Demo-Key': key_file.read_text().strip()})
with urllib.request.build_opener(NoRedirect()).open(request, timeout=30) as response:
    print(response.read().decode())
PY
```

## Reset and quirks

**Close every editor tab on the two demo workflows before a reset.** On Community Edition the seed overwrites
unconditionally: PATCH ignores `expectedChecksum`, and there is no editor-lock protection. A stale tab’s next
save can put the mangled graph back. The seed still sends the checksum for licensed PATCH and publication.

`just n8n-seed-content` restores the reviewed name/nodes/connections, clears `pinData`, and publishes those versions.
Creation sends reviewed settings unchanged. On updates only, it restores reviewed settings and resets absent
`errorWorkflow`, `timezone`, `saveDataErrorExecution`,
`saveDataSuccessExecution`, `saveManualExecutions`, `saveExecutionProgress` to instance defaults, and resets an
absent `executionTimeout` to Hartland’s instance default `-1` (unlimited). It preserves the webhook key,
refreshes referenced DB/SMTP credentials and leaves unrelated workflows and other users’ projects untouched.
Archived examples stay archived; reset creates a fresh copy in Markéta’s project.

It leaves `staticData` (schedule state), metadata, node groups, executions and Mailpit messages alone.
Settings cannot in general be deleted through n8n’s merge PATCH. `--verify` requires exact reviewed settings,
except the modal’s automatically inserted defaults: `callerPolicy: workflowsFromSameOwner`,
`availableInMCP: false`, `timeSavedMode: fixed`. A different/additional setting fails naming its **key**, never its
value; correct it manually in Settings before retrying. Nonempty `pinData` always fails verification.
Before rehearsing, run `--verify` again.

In the first live rehearsal, deliberately pin rows and save, confirm verify fails, close the editor and reset;
archive the echo and confirm reset creates a fresh working copy. Also rehearse an open/stale tab save so the
operator sees that verify catches the resulting draft; close the tab before the final reset.

Community Edition has no SSO or workflow sharing: the n8n login is separate from Keycloak, and members see their
own workflows. Markéta is the owner/presenter. Mailpit's public inbox uses Keycloak and the Hartland role.
The cluster's NetworkPolicy enforcement is deferred separately; this runbook does not enable it.

If seeding fails, keep the safe endpoint/status diagnostic and rerun after resolving the cause. Do not dump raw
HTTP, credential objects or password files. An existing key with a wrong/missing file requires deliberate recovery,
not a rerun with a new key. If a webhook probe gets 404, check publication; if 401/403, check the original key file.

After the first live rehearsal record the elapsed time, delivery count and awkward steps in project/common/n8n/STATUS.md.
