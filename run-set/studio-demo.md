# The Studio demo — runbook (hartland)

Three beats on one object, `returns_review` (SO design §4, D-26). In **V**, Maya looks at the model. In **E**, she
changes it, Dan approves it, and the Golem picks it up. In **R**, Dan runs the report that change added. The change is
re-enacted live. `demo/returns-review` holds the same change pre-authored, and `scripts/demo-compare.sh` checks the live
branch against it (SD-D4).

| who | logs in to | plays |
|---|---|---|
| Maya | the Studio `https://studio.hartland.collite.cz`, Iris `https://iris.hartland.collite.cz` | the modeler (licence `modeler`) |
| Dan | GitHub (the reviewer's account, write access on `Collite/ttr-demo`), then the Studio | the approver; Reports (`kantheon-role-finance`) |
| operator | a terminal with `kubectl --context hartland`, `gh`, `git`, `jq`, `zstd`, and a `Collite/ttr-demo` clone | the pre-show, the clocks, the fallbacks |

The personas' passwords live in the realm file only. Never copy them anywhere (olymp#155). Always pass
`--context hartland`: the box's current context can be `dbf-prod`.

## Open before the first rehearsal (2026-10-28)

G1–G5 must close before a rehearsal can pass. G6 has a manual workaround in this runbook. G7–G10 can only be checked
at the rehearsal itself. Each one breaks a specific step:

| # | gate | breaks | owner |
|---|---|---|---|
| G1 | `studio-report` released and deployed (olymp P1·S1.2 waits on a `studio-report/v…` tag) | Reports is absent from the rail, so there is no beat R | ttr-platform → olymp |
| G2 | ttr-platform `tasks-final-live-checks.md`: L-Setup, L-App, L-V, R6 | the pre-show's `modules` / `served` answers | ttr-platform |
| G3 | **ttr-core#325**: `ttr-lexicon` drops a term whose `for:` is package-qualified, and the synthesizer writes it that way | the Golem never sees "returns review" (the lexicon has no row for it; check 8 below) | ttr-core (fixed in `grammar/v0.18.17`), then `toolchain.lock` `[ttr-core].ref` — **closed 2026-10-29** by the lock bump |
| G4 | **ttr-core#326**: without `file`, `insert-entity` puts the entity in `model/er/calendar.ttrm` and `add-term` puts the terms in `model/lexicon/*/automation.ttrm` | Dan reviews the entity in the calendar file; the compare fails | ttr-core (fixed in `designer/v0.1.2`, 2026-10-29), then ttr-platform's re-vendor + a Viewer cut + `studio` image |
| G5 | **ttr-platform#84**: Propose writes the roster line (D-22; Bora ruled 2026-10-29, built in ttr-platform#85) — closes when a `studio-bff` with it is deployed | without it `model-gate` T6.2 (exact entity count) goes red, so Merge is refused | ttr-platform → olymp |
| G6 | **kantheon#272**: the golem caches the model at boot | a new entity is unknown to the Golem until `POST /v1/refresh`; the runbook does it by hand (E7) | kantheon |
| G7 | the report query's lowering through the door has never run (`CURRENT_DATE`, `EXTRACT(QUARTER …)`, quoted `"year"`/`"quarter"`) | the first preview in R2 is that test | — (rehearsal) |
| G8 | the query and the entity are both named `returns_review`; hartland's LQ files keep them apart because the Golem's lookup tries a query name first | the Golem may bind the query, not the entity | — (rehearsal: read the protocol in E7) |
| G9 | where a live layout save lands is unconfirmed: the hosted graph wizard writes `<root>/graphs/<slug>.ttrg` (`designer-authoring` `CreateGraphWizard.tsx`), not `model/layouts/returns_review.ttrg` | E5 and the compare's layout file | — (rehearsal; if there is no path to `model/layouts/`, the layout leaves the branch) |
| G10 | the hosted Designer's remove is not wired (`removeNode` returns `false`, studio 0.11.17) | reverting through the Studio (After the show) | — (rehearsal: the GitHub revert is the fallback) |

When G4 and G5 land, re-author `demo/returns-review` to what the Studio then writes (see the last section).

## Pre-show (operator, ~15 min, the morning of the show)

Set up the shell first:

```bash
cd ttr-demo && git fetch -q origin
STUDIO=https://studio.hartland.collite.cz
```

1. **Master is where the show starts: no `returns_review` on it** (this check moved here from the gate, ttr-demo#145).
   ```bash
   git grep -n -E 'def (query|entity) returns_review\b|returns_review_q' origin/master -- model   # → no output
   ```
2. **Metadata serves master.**
   ```bash
   kubectl --context hartland get --raw /api/v1/namespaces/ttr-server/services/metadata:7260/proxy/status \
     | jq '{ready, issues, served: [.sources[] | select(.id == "github-model") | .version]}'
   git rev-parse origin/master
   ```
   You should see `ready: true`, `issues: []` and the same SHA in both outputs.
3. **Roll fuzzy (`06` 4.1) and refresh both golems.**
   ```bash
   kubectl --context hartland -n ttr-server rollout restart deploy/fuzzy
   kubectl --context hartland -n ttr-server rollout status deploy/fuzzy
   kubectl --context hartland -n ttr-server logs deploy/fuzzy --since=10m | grep 'Compiled lexicon loaded'
   for d in golem-hartland golem-hartland-finance; do
     kubectl --context hartland -n kantheon exec deploy/$d -c golem -- curl -s -m 60 -X POST http://127.0.0.1:7420/v1/refresh
   done   # → {"status":"refreshed"} twice
   ```
4. **The App and the protection.** Use the org listing. `/repos/…/installation` needs the App's own JWT and answers a
   person's token with 401.
   ```bash
   gh api /orgs/Collite/installations \
     --jq '.installations[] | select(.app_slug == "tatrman-studio") | {suspended_at, repository_selection, permissions}'
   gh api /repos/Collite/ttr-demo/rulesets --jq '.[] | {name, enforcement}'
   ```
   You should see `suspended_at: null`, `contents`/`pull_requests`/`actions: write`, and `master-protect: active`.
5. **The Studio as Maya.** Log in as Maya in the browser. Then take her bearer: DevTools → Network → any `/api/`
   request → Request headers → `authorization`. Keep it in the shell only.
   ```bash
   read -rs AUTH   # paste "Bearer eyJ…"
   curl -s -H "Authorization: $AUTH" "$STUDIO/api/studio/modules?explain=true" | jq '.modules[] | {id, enabled, features, reason}'
   curl -s -H "Authorization: $AUTH" "$STUDIO/api/studio/licence" | jq '{valid, expires, modules}'
   curl -s -H "Authorization: $AUTH" "$STUDIO/api/model/served" | jq .
   curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: $AUTH" "$STUDIO/api/reports/health"
   ```
   What to expect:
   - `model` enabled with `["viewer","modeler"]`, and `reports` enabled. Anything absent carries a `reason` starting
     with `metadata:` / `capability:` / `licence:`.
   - The licence is `valid` and not about to expire.
   - `masterSha` equals `servedSha`. A master SHA means the App can read the repo. `toolchain.mismatch` is `false`
     (R6).
   - `reports/health` returns `200`.
6. **No leftover change.** `curl -s -H "Authorization: $AUTH" "$STUDIO/api/model/changes" | jq '.changes[] | {name, branch, state}'`
   should show no open *Returns review*. Discard a leftover in the Studio (before review), or close its PR.
7. **The reference branch contains master and is green.**
   ```bash
   git merge-base --is-ancestor origin/master origin/demo/returns-review && echo contains-master
   gh workflow run model-gate.yml -R Collite/ttr-demo --ref demo/returns-review && sleep 5 && \
     gh run watch -R Collite/ttr-demo "$(gh run list -R Collite/ttr-demo --workflow model-gate.yml --branch demo/returns-review --limit 1 --json databaseId -q '.[0].databaseId')"
   ```
   If master has moved, Bora rebases the branch onto it (`git push --force-with-lease`). Then run
   `scripts/regenerate-local.sh`, commit what it rebuilds (`generated/`, `model/layouts/agent/`) in the bot's form
   ("regenerate: generated/ for <sha>"), and run the gate again.
8. **The reference's lexicon carries the new words** (G3). This prints one `en` row and one `cs` row:
   ```bash
   git show 'origin/demo/returns-review:generated/lexicon.tar.zst' | zstd -dcq | tar -xO docs/lexicon.json \
     | jq -r '.entries[] | select(.targetRef == "er.entity.returns_review") | "\(.lang)\t\(.sourceTag)\t\(.termNormalized)"'
   ```
   Until ttr-core#325 lands it prints nothing, and beat E's last step can't work.
9. **The windows.** Open, side by side:
   - the Studio as Maya, on Home;
   - GitHub as Dan, on `Collite/ttr-demo` → Pull requests;
   - Iris as Maya;
   - this terminal.

## Beat V — see the model (Maya, ~3 min)

1. **Model** → the catalog: **er**, then **db**, then **md** with the sales star. *"This is the Hartland model: the
   business view, the physical tables, the cubes. All of it is text in git; this page reads what's served."*
2. **Model language** EN → CS → EN. *"The words are part of the model, in both languages."*
3. Open the **sales** layout. *"A working view somebody saved."* Then open the Golem's layout, **agent_hartland**.
   *"This is what the assistant knows: generated from its agent definition, never hand-drawn."*

## Beat E — change the model (Maya → Dan, ~12 min including the waits)

E1. **New change** → name it *Returns review* → the change opens (branch `model/maya/<n>`, made from the served SHA).

E2. **The query, as text.** Open **Source files** → **New source file**. Set **Source path** to
`model/er/returns-review.ttrm` and paste this as **Source text**:

```
package hartland

model er

def query returns_review {
    sourceText: """sql
SELECT r.request_number AS request_id, r.customer, i.category,
       r.requested_date AS requested_at, rr.received_date AS received_at,
       r.state AS status, l.quantity * l.unit_price AS amount
FROM return_request r
JOIN return_request_line l ON r.request_number = l.request_number
JOIN item i ON l.item = i.sk
LEFT JOIN return_receipt rr ON l.line_id = rr.line_id
"""
}
```

Then **Apply to model** and **Save**. *"A logical query: one row per returned line, with what we know about it."*

E3. **The entity on it.** Authoring → **New entity**. **Entity name** `returns_review`, **Binding** *On query*, **Query**
`…er.query.returns_review` → **Create entity**. *"The Studio derives the attributes from the query's columns and binds
the entity at creation. Nothing unbound reaches review."* (D-22)

E4. **The words.** On the `returns_review` node, open the menu → **Add term**. Add `returns review` (EN), then
`přehled reklamací` (CS). Then **Save**.

E5. **The layout** (optional on stage; G9). Make a graph of `returns_review` with `return_request`, `return_receipt`,
`customer` and `date_dim`, and save it as `returns_review`. Positions are free: the compare ignores them. The
pre-authored file is `model/layouts/returns_review.ttrg`. If the save lands anywhere else, skip this step on stage
and record the path.

E6. **The report it will feed** (beat R's half).
- **Source files** → **New source file**, `model/er/reports.ttrm`, with this text:
  ```
  package hartland

  model er

  def query report_returns_review_q {
      sourceText: """sql
  SELECT returns_review.category AS category,
         COUNT(DISTINCT returns_review.request_id) AS requests,
         COUNT(DISTINCT CASE WHEN returns_review.received_at IS NOT NULL THEN returns_review.request_id END) AS received,
         COUNT(DISTINCT CASE WHEN returns_review.status <> 'closed' THEN returns_review.request_id END) AS "open",
         SUM(returns_review.amount) AS amount
  FROM returns_review
  JOIN date_dim ON returns_review.requested_at = date_dim.cal_date
  WHERE date_dim."year" = EXTRACT(YEAR FROM CURRENT_DATE)
    AND date_dim."quarter" = EXTRACT(QUARTER FROM CURRENT_DATE)
  GROUP BY returns_review.category
  ORDER BY category
  """
  }
  ```
  Then **Apply to model** and **Save**. `"year"` and `"quarter"` stay quoted: both are reserved words in the SQL
  parser.
- On the query's node menu → **New report from this query**:
  - **Report id** `returns_review_q`. The form proposes `report_returns_review_q`; overwrite it.
  - **Title EN** *Returns review, this quarter*.
  - **Title CS** *Přehled reklamací, toto čtvrtletí*.
  - **Allowed roles** `kantheon-role-finance`.

  Then **Create report**. The Studio commits `report.yaml` and `template.xlsx` together.

E7. **Propose.** The header shows *Regenerating the model before review…* for about 30 s while the bot rebuilds
`generated/` and the Golem's layout on the branch. Then the change is *In review*, and **View pull request** opens it.
- **Dan, in GitHub:** open the PR → **Files changed**. *"Plain text — the query, the entity, its binding, two words,
  a report."* The bot's regenerate commit sits beside Maya's. The checks run about 5 minutes (`model-gate`, with the
  Kotlin load). Fill the wait with what the gate checks: the model loads strict, the lexicon and the snapshot are
  current, every entity is bound. Then **Review changes** → **Approve**.
- **Maya, in the Studio:** **Merge**. The change goes *merged*, then *served* within about a minute, once metadata
  serves the merge SHA. The catalog then lists `returns_review`.
- **Operator:** run the compare on Maya's branch once *In review* shows, before the merge, so the branch exists and
  holds the bot's commit:
  ```bash
  scripts/demo-compare.sh model/maya/<n>   # exit 0 = clean; else the paths that differ
  ```
- **The Golem** (Iris, as Maya; "a couple of minutes" on stage). The words reach fuzzy on its 120 s tick. The entity
  reaches the Golem only on a refresh (G6). So once *served* shows, the operator runs:
  ```bash
  for d in golem-hartland golem-hartland-finance; do
    kubectl --context hartland -n kantheon exec deploy/$d -c golem -- curl -s -m 60 -X POST http://127.0.0.1:7420/v1/refresh
  done
  ```
  Then ask: **"What does the returns review show by category?"** The question must contain the declared form
  "returns review" (or «přehled reklamací»). The task list's "How many returns are under review?" does not contain
  it. Open the turn's protocol: the mention binds `er.entity.returns_review` as MODEL_OBJECT, not the query (G8).

The clocks to expect and to record (fill in at each rehearsal):

| step | expected | measured |
|---|---|---|
| Propose → *In review* | ~30 s (regenerate) | |
| PR opened → `model-gate` green | ~5 min | |
| Merge → *served* (metadata `/status` = merge SHA) | ≤ ~1 min (olymp P0: +28 s) | |
| Merge → fuzzy `Compiled lexicon loaded` | ≤ ~3 min (olymp P0: +2 m 48 s) | |
| golem refresh → the Golem binds "returns review" | seconds | |

## Beat R — the report (Dan, ~3 min)

Dan logs in to the Studio.

1. **Reports** → *Returns review, this quarter* → **Preview** (the first table, up to 500 rows). It shows one row per
   item category for the current quarter. On 2026-10-28 that was 11 rows for 2026-Q4, 10 categories and one row with
   none, counted read-only on hartland-pg.
2. **Download** the XLSX: one sheet, the title, the as-of date, the table.
3. **History** shows the run Dan just made.

If someone asks where the numbers come from: *"From Hartland's Czech company, the default connection. The same model
also serves the US company; the report will name its world once the query service carries one."* (D-32;
ttr-server#261.)

## Fallbacks

| it fails | do |
|---|---|
| Propose: `diagnostics-red`, or the regenerate run fails (the change shows `diagnostics.regenerate.runUrl`) | Show the run. Then open the pre-authored PR by hand: `gh pr create -R Collite/ttr-demo --base master --head demo/returns-review --title "Returns review" --body "Pre-authored (SO demo)."`. Dan reviews and approves that. |
| Merge in the Studio: `409 not-mergeable` | Dan merges on the PR page in GitHub (merge commit). The protection applies there too. |
| *served* lags (> 2 min after the merge; check 2's command shows the old SHA) | The operator triggers metadata from inside the cluster: `POST http://metadata.ttr-server:7260/refresh`, e.g. from a one-off curl pod in `ttr-server`. This is the operator's hand, never the Studio's (`06` 4.1, RF-3). |
| The Golem doesn't bind the new words | Run the golem refresh again. Check fuzzy's `Compiled lexicon loaded` after the merge and pre-show check 8 on `origin/master`. Read the turn's protocol. |
| `demo-compare.sh` prints paths | Not a stage failure. Record the paths in STATUS and file each against the contract that owns it (ttr-demo contracts §5). |

## After the show

- **Revert** (W-7: a revert is just another reviewed change).
  - **Through the Studio, if it can remove:** as Maya, **New change** *Revert returns review*. Use
    `remove-definition --force` on `er.entity.returns_review`, which also drops its binding, terms and roster line,
    and remove the two queries, `model/reports/returns_review_q/` and the layout. Then Propose; Dan approves and
    merges.
  - **Otherwise (G10):** the merged PR's **Revert** button in GitHub. Dan approves the revert PR once `model-gate` is
    green, then merges it.
- **Master is back:** `git diff <pre-show master SHA> origin/master -- model generated` prints nothing.
- Then run pre-show checks 1–3 and 7 again for the next show.
- The change branches (`model/maya/*`) stay. Sweeping them is Bora's.

## Re-authoring the branch (when G4/G5 land, or the compare reports a difference)

`demo/returns-review` must hold exactly what the Studio writes. That means the Studio's own ops through the published
synthesizer, not the inline-`terms` vector. Reproduce them against a master checkout:
1. The drawer's file, as in E2.
2. `insert-entity { name, on }` with no `file` or `terms`.
3. `add-term { target, term, lang }` twice.
4. The report: `ttr-report new` for the report query, or the BFF's `POST /api/reports/new`.
5. Whatever Propose adds: the roster line, `  'returns_review',` alone before `];` of `EXPECTED_ENTITIES` (G5,
   `modeler.toml [studio.entity-roster]`), no comment line.

Commit the result as Maya's half and the report half, then `scripts/regenerate-local.sh` in the bot's form. The
2026-10-28 replay with `grammar/v0.18.12` (= Viewer 0.11.4) wrote the same text as the branch, in
`model/er/calendar.ttrm` and `model/lexicon/{en,cs}/automation.ttrm` (G4). `demo-compare.sh` against the replay is the
check.
