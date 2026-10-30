# Hartland demo — quirks & gotchas

metadata — formerly `veles` (2026-06-13 → 2026-10), originally `ai-platform/infra/metadata`.

> Operational field notes for the Kantheon bilingual (US/CZ) TPC-DS pattern-answering
> demo on the live `hartland` cluster. Everything here **bit us** during bring-up
> (Stage 3.3, Jul 2026). Read this before touching the demo model, the read spine, or
> the golems — most of these fail *silently* or with a misleading symptom.
>
> Companion docs: [`demo-transcript.md`](./demo-transcript.md) (the narrative),
> [`plan-demo-build.md`](./plan-demo-build.md) (the build). Deployment truth is in
> `olymp/clusters/hartland/`.

---

## 0. The meta-quirk — golem masks query failures as "0 rows"

**The single most misleading behaviour.** When a golem turn's query node fails downstream
(translator rejection, empty result, RLS zeroing), golem reports the turn as
`STATUS_DONE` with `rowCount = 0` — **not** an error. So "0 rows" can mean *the query was
rejected*, not *the data is empty*. Every time a query "returns nothing," the real cause
is usually upstream and only visible in the **query-service log** (`ttr-server/query-*`),
where you'll find the actual `translator_rejected` / error message.

**Rule:** never trust a 0-row turn at face value. Pull the `ttr-query` log for the
`correlation_id` and read the real response before concluding anything about the data.

---

## 1. Model serving (metadata / Ariadne)

### 1.1 Package filtering is by FILE PATH, not the declared `package`
metadata classifies a model object into a package by looking for `/<package>/` **in the
object's source-file path** (`MetadataServiceImpl.kt`), *not* by the `package hartland`
declaration in the `.ttrm`. The git-source `id` is hardcoded `github-model`
(`application.conf`), so the clone lands at `/tmp/metadata-git/github-model/…` — whose
paths contain no `/hartland/` segment. Result: `GetModel(["hartland"])` matched **zero**
files even though ResolveArea returned `["hartland"]`.

**Fix (live):** `METADATA_GIT_CHECKOUT_DIR=/tmp/metadata-git/hartland` in
`olymp/clusters/hartland/apps/metadata/values.yaml`, so every source path carries
`/hartland/`.

### 1.2 Two refreshes are needed after a model edit — metadata AND golem
metadata pulls the model from `Collite/ttr-demo` (branch `master`, subdir `model/`) on a
poll interval; golem fetches the **ModelBundle from metadata once at boot and caches it**.
So after you push a model change:

1. **metadata**: force a re-fetch — `MetadataService/Refresh {force:true}` over gRPC (see §5.3),
   or wait for the poll. Confirm with `ListQueries` (parse status flips to PARSED).
2. **golem**: `kubectl rollout restart deployment/golem-hartland -n kantheon` (and
   `-finance`). Without this, golem keeps serving the **stale** pattern SQL — which then
   fails at the translator and surfaces as §0's phantom "0 rows."

Forgetting step 2 cost hours: veles showed 15/15 parsed while golem still sent the old SQL.

### 1.3 Parse status is async
Right after `Refresh`, `ListQueries` may show `PARSE_STATUS_PENDING` for a few queries —
parsing runs on a background worker. Poll until it settles to PARSED/FAILED.

### 1.4 metadata gRPC has no server reflection
`grpcurl -plaintext … list` fails ("server does not support the reflection API"). Drive it
with the proto file:
`-import-path tatrman-server/shared/proto/src/main/proto -import-path <plan-proto extracted dir> -proto org/tatrman/meta/v1/meta.proto`.
The extracted plan/common protos live under a `build/extracted-include-protos/*` dir.

---

## 2. Query SQL — Calcite acceptance (the translator, not Postgres)

Pattern-query `sourceText` is parsed by **Calcite** (via the translator), which is
**stricter than Postgres**. A query can run fine against `hartland_us` in `psql` and still
report `PARSE_STATUS_FAILED` in metadata. Seen so far:

### 2.1 Reserved words as identifiers
A CTE named `returns` → `parse_failed: Encountered ", returns"`. `returns` is a Calcite
reserved word. Rename the CTE (we used `rets`). Watch for other reserved words used as
table/CTE/column aliases.

### 2.2 GROUP BY / ORDER BY on a SELECT alias
`SELECT (y - birth_year) AS buyer_age … GROUP BY buyer_age` → `Column 'buyer_age' not
found`. Postgres allows grouping by a select alias; **Calcite forbids it** (aliases aren't
in scope for GROUP BY per the SQL standard). Group by the underlying column or repeat the
expression.

### 2.3 Named-parameter placeholders are single-curly `{name}` ONLY
The translator's `ParameterBridge` recognises **only** `{name}`. Colon (`:name`), at-sign
(`@name`), and double-curly (`{{name}}`) are **not** rewritten and Calcite chokes on the
raw character. All 15 demo queries originally used `:colon` params → all failed. Convert
every parameter reference to `{brace}`.

### 2.4 A query can parse yet return 0 rows through the pipeline (translator quirk)
`buyer_age_profile` in a derived-table + `GROUP BY <subquery col>` form **parses** but
returns **0 rows** through the full pipeline (identical SQL returns rows in raw Postgres).
The `GROUP BY birth_year` form serves rows but the translator appears to **drop the
`birth_year IS NOT NULL` filter** (a null-age bucket leaks into the output). Net: this one
query has a form-dependent translator interaction. Left in the row-serving form with an
inline NOTE; tracked as a demo-polish follow-up (a real translator issue, not a query bug).

---

## 3. Parameters, schema, language (the golem → query-mcp → spine hops)

### 3.1 A resolved pattern's `source_language` is a MODEL property, not the LLM's guess
golem originally forwarded the LLM's `source_language` guess; SQL patterns went out tagged
`transdsl` → `translator_rejected: "Expect message object but got SELECT"`. Fixed in
`MiniPlanExecutor` (use `pq.sourceLanguage`, fall back to the node value only if
unspecified) **and** by pinning `"source_language": "sql"` in the golem prompts.

### 3.2 query-mcp must set `source_schema=DB` for physical SQL
Physical (DB-level) SQL was parsed against the **ER** schema by default →
`'ss_sold_date_sk' is a db object; parsed against er`. query-mcp now defaults
`source_schema=DB` when `source_language=SQL`.

### 3.3 Text parameters are case-sensitive (fix implemented, pending toolchain release)
`WHERE channel = {channel}` with the utterance "…for **Marketplace**" binds
`channel="Marketplace"`, but the data literal is lowercase `'marketplace'` → 0 rows. This
is **not** golem's job to normalise — it belongs in the parametrized-query normalization
pass (ttr-translator). Fix implemented: a RESOLVE-stage pass (`CaseFoldingParams`) folds
`=`/`<>` comparisons that involve a text parameter to `LOWER()` on both sides, so
"Marketplace"/"marketplace"/"MARKETPLACE" all match — tatrman branch
`feat/case-insensitive-text-params`. **Reaches hartland only after a ttr-translator release
+ ttr-translate repoint + redeploy** (tag-driven publish). Until then, phrase demo
utterances with the lowercase channel token.

### 3.4 Locale picks golem's PROMPT bundle — it sets the answer's language, not the UI's
Hit 2026-07-27. An English session, English question, English routing chips — then the answer
bubble came back with a **Czech** caption ("Vývoj tržeb Marketplace v roce 2025…") and Czech
follow-up chips, over US warehouse data (Reno DC, Allentown DC…).

Nothing was mistranslating. Golem selects its prompt bundle by locale —
`/etc/golem/shem/prompts/<locale>/intent.yaml` — so the locale on the request decides the
language the **plan-composer prompt** is written in, and therefore the language of the caption
and the LLM-topped-up chips. The gateway's `prompt_logs` shows it plainly: golem's composer
prompt began `Jsi plánovač domény Hartland Analytics`.

Three layers each did something reasonable and the combination was wrong:
- the SPA's language picker was **UI-only** by design (`useAgentSession.ts`: *"locale is a UI
  concern now"*) and never sent anything to the BFF;
- `ChatTurnRequestDto` had **no locale field** to send it in;
- `ChatDispatcher` and the golem client each carried a hardcoded Kotlin default `"cs"`, read
  from no config — correct for a Czech-first estate, wrong for this one.

Fixed by making locale a real per-turn value: the SPA sends the picker's language on every
turn, the BFF falls back to `iris.locale` / **`IRIS_LOCALE`** (set to `en` on hartland), and it
flows to both Themis's `ResolveContext` and golem's `GolemContext`. Blank is treated as absent
so golem falls back to its Shem's own default rather than being handed `""`.

Reflex: if an agent answers in the wrong language, look at the *prompt bundle it loaded*, not
at the model. `SELECT prompt_text FROM prompt_logs ORDER BY created_at DESC LIMIT 1` in the
`llm_gateway` DB tells you in one query.

Still hardcoded Czech (functional, not display): the row-select verb the FE sends,
`Vyber řádek N` — golem parses it as an instruction, so localising it needs a typed row-select
verb agreed with golem first.

---

## 4. Governance — the validator (ttr-validate / Argos)

### 4.1 TopN is a HARD ceiling and `row_limit` is (currently) dead-plumbing
The validator injects a `LIMIT` (TopN) into **every** plan. Its service default
(`VALIDATE_DEFAULT_TOP_N`) is an **authoritative ceiling**: `effectiveCap =
min(caller.default_top_n, serviceDefault)` — a caller can only ask for *fewer* rows, never
more. Separately, `row_limit` set by query-mcp on `RunRequest` is **never read** by any
downstream service, and `ttr-query` never forwards the caller's budget into
`ValidationOptions.default_top_n`. So today the *only* lever is the service-wide default.

The default `30` silently truncated the 72-row monthly series (→ 2024 months 1–10). Set
to **100** on hartland (`olymp/clusters/hartland/apps/validate/values.yaml`,
`VALIDATE_DEFAULT_TOP_N=100`) so full aggregate series render whole **and** a deliberately
larger query is *visibly* capped — the governance beat in the narrative.

The design fix (caller `row_limit` → `default_top_n`, requestor states the *want*, validator
decides the *get*) is tracked as **NEW-4** in
`project/server/design-corpus/implementation/tasks/backlog-row-limit-vs-topn.md`.

### 4.2 Helm `extraEnv` REPLACES, it does not merge
Overriding `extraEnv` in an olymp values file **drops** the chart's default env list. When
you add `VALIDATE_DEFAULT_TOP_N`, you must repeat the chart's `METADATA_HOST`/`METADATA_GRPC_PORT`
entries verbatim, or the validator loses its metadata wiring.

---

## 5. Deployment & live-verification mechanics

### 5.1 Images must be multi-arch — the hartland node is amd64
Local builds are arm64; jib non-CI builds only the local arch. Prefix `CI=true` to force a
multi-arch (arm64+amd64) build, or the node can't pull. golem's jib is parameterised
(`-PimageRepo -PimageTag`); query-mcp's `to.image` is hardcoded (override with
`-Djib.to.image=…`).

### 5.2 Port-forwards die when the Bash call returns
A background `kubectl port-forward` started in one tool call is killed when that call ends.
Run the whole token-mint → turn → resume flow in a **single** shell invocation.

### 5.3 The live-turn recipe (Maya persona)
- **Token (ROPC):** realm `kantheon`, public client `iris` (directAccessGrants),
  `POST /realms/kantheon/protocol/openid-connect/token`,
  `grant_type=password&client_id=iris&username=maya&password=Hartland!2026&scope=openid`.
  Keycloak svc `auth-keycloak-keycloakx-http` (ns `auth`, port 80).
- **Turn:** `POST /v1/answer/sync` to `golem-hartland` (ns `kantheon`, port 7420), body
  `{"id","golemId":"golem-hartland","question"}`; caller derived from the bearer.
- **Clarifications:** param-fill asks **one parameter at a time**; resume via
  `POST /v1/resume {resume_token, free_text_answer}`. The resume token is nested at
  `envelopes[0].pendingClarification.resumeToken`. Result rows land in the envelope's
  `contentJson`; step counts in `stepRecords[].rowCount`.
- **metadata Refresh:** `MetadataService/Refresh {force:true}` (grpcurl, §1.4 for proto paths).

### 5.4 ArgoCD sync
The hartland apps auto-sync from olymp `master` (HEAD) + tatrman-server master. Force a
re-read with
`kubectl annotate application <app> -n argocd argocd.argoproj.io/refresh=hard --overwrite`.
A `extraEnv` change is a Deployment-spec change, so ArgoCD rolls the pod automatically.

### 5.4b Stale personal-registry images are the demo's likeliest "config" bug
Hit 2026-07-27 on the Iris SPA: every POST answered **403** (`/bff/v1/session`,
`/bff/v1/chat/stream`) and `/bff/v1/inbox` + `/bff/v1/discover` answered **404**, while the
identical curl to the same pod returned 201. Nothing in the current source can emit 403 on
those routes, and the FE config (`/env.js`) was correct.

Cause: `ghcr.io/boraperusic/iris-bff:0.1.0` — a laptop-built image older than the v0.5.0
snapshot import — still installed a Ktor **CORS** plugin whose allow-list was the Vite dev
server (`http://localhost:5173`). Browsers attach `Origin` to **every non-GET request,
including same-origin ones**, so each SPA POST tripped CORS → 403; curl sent no `Origin` and
sailed through. The 404s were the same image simply lacking DiscoverRoutes/InboxRoutes.
The FE's `:testing` bundle was stale in step (polled a malformed `//bff/ready` →
`ERR_NAME_NOT_RESOLVED`, still called the retired golem `/bff/v2/agent/graph`).

Reflexes:
- **A 403 that curl can't reproduce is a CORS allow-list, not authz.** Add
  `-H "Origin: https://<the-app-host>"` to the curl — that one header reproduces it.
- **Check the image before the config.** `kubectl get deploy <x> -o jsonpath=…image` — a
  `boraperusic/*` repository or a `:testing` tag means the running code is unidentifiable and
  is the first suspect. The release lane is `ghcr.io/collite/<module>:<version>` (olymp#19).
- Envoy's access log is the fastest way to attribute a status code:
  `kubectl -n gateway logs -l gateway.envoyproxy.io/owning-gateway-name=eg | grep 403`
  gives `x-envoy-origin-path`, `response_code_details` (`via_upstream` = the app answered,
  not the gateway), and `upstream_host`.
- Verify a package is pullable **before** rolling: mint a GHCR token from the cluster's own
  `ghcr-pull` secret and HEAD the manifest — visibility on ghcr is per-package, so one
  working `collite/*` image proves nothing about the next.

Fixed by repointing both to `ghcr.io/collite/{iris,iris-bff}:0.6.0` (olymp branch
`iris-release-images`).

### 5.4c A healthy estate can still have a dead LLM path — check the key AND the tier
Hit 2026-07-27. Iris answered, but with a contentless clarification ("Which interpretation did
you mean?" + chips labelled " (0%)"). Every pod Healthy, no restarts, HTTP 200 throughout.

Themis's LLM calls were all returning **empty**. `LlmGatewayClient.complete` returns
`Result.failure` rather than throwing, so the graph nodes got `""`, every JSON parse died on
`Expected start of the object '{', but had 'EOF'`, and routing fell through to a blank
clarification. Two independent causes, either sufficient:

1. **No ttrk key.** Gateway 2.0 gates `/v1` per consumer. `themis` existed as a governance
   *team* but had no row in `virtual_keys` — missed in the LG-P6·S1 migration that keyed
   kleio/kallimachos/pinakes/golem.
2. **Wrong tier.** Themis asked for `haiku`/`sonnet`. Those are real catalog aliases, but they
   pin **Anthropic** models — and hartland's `llm-gateway-secrets` holds only
   `azure-openai-key`. The generic tiers `mini`/`fast`/`deep` are the ones the catalog routes
   to the Azure deployment, and are what `LlmGatewayPromptExecutor` emits.

The decisive probe — run it from inside `ttr-server` with a *known-good* key (golem's), one
model per line, and read the status codes side by side:

```
MODEL=haiku    HTTP=401  {"code":"invalid_api_key"}        ← upstream Anthropic, not your ttrk key
MODEL=sonnet   HTTP=502  {"code":"upstream_error"}         ← Anthropic again
MODEL=gpt-4.1  HTTP=200                                    ← Azure works
```
Using a key you know works separates "my key is bad" (401 at the gateway edge) from "the
provider behind that alias has no credentials" (401/502 forwarded from upstream). They look
identical in a consumer's logs.

Reflexes:
- `SELECT id FROM teams` vs `SELECT team_id FROM virtual_keys` in the `llm_gateway` DB — a team
  with no key is the signature of a missed consumer migration.
- `kubectl -n ttr-server get secret llm-gateway-secrets` — which providers actually have
  credentials on THIS cluster. Only pick tiers that resolve to those.
- A gateway failure never surfaces as an exception in a consumer. Grep consumer logs for
  `had 'EOF'` — an empty LLM response is the tell.

### 5.4d Iris→Golem dispatch spoke /v2; kantheon's Golem serves /v1 (fixed 2026-07-28)
Hit 2026-07-27, the last hop of the Beat-2 chain. Themis routed correctly, Iris offered the
agent chips, `golem-hartland` was picked — and the bubble came back **empty**. iris-bff logged
a 404 from `http://golem-hartland:7420/v2/session` and a `NoTransformationFoundException`.

Not a misconfiguration. iris-bff's only dispatch client was `GolemV2HttpClient`, which speaks
the **pre-fork** new-golem API (`/v2/session`, `/v2/chat/stream`). The kantheon Kotlin Golem
implements none of it — its whole route surface is:

```
POST /v1/answer/sync   POST /v1/answer  (SSE)   POST /v1/resume   POST /v1/refresh
```

`AgentClient`'s own KDoc said as much ("the map is the seam native Golem/Pythia clients plug
into **in their own arcs**") — the arc simply hadn't run. A native `GolemV1AgentClient` now
ships in iris-bff (`dispatch/golem/`), and `iris.dispatch.agent-endpoints` binds to it; the
`golem-v2` key keeps the transitional client. **No olymp change** — the endpoints are already
configured; it takes effect on the next iris-bff image.

Three things that surface only at this seam, worth knowing when reading its logs:
- Golem's terminal SSE frame is a whole **`ConversationalResponse`**, not one envelope — a turn
  can be several bubbles, and `status` is stated rather than inferred. (That matters: golem's
  param-fill clarification envelope *also* carries an `error_code`, so shape-inference reads a
  pending question as a failed turn.)
- Golem answers admission failures with a **Rule-6 JSON body, not SSE**. Deserialising that as
  the success shape is what produced the silent empty bubble. Non-2xx now maps to
  `GOLEM_UNAUTHORIZED` / `GOLEM_FORBIDDEN` / `GOLEM_ENDPOINT_NOT_FOUND` with golem's own
  `humanMessage`.
- Golem runs the graph to completion *before* emitting the terminal frame (pinging every 5s
  meanwhile), so the dispatch client must have **no request timeout** — only a socket-idle one.

Still v2-only, deliberately: typed actions (drilldowns/refetch) and artifact refresh, which
golem has no `/v1` counterpart for at all.

### 5.5 Namespaces
Spine (metadata, query, validate, translate, dispatch, workers, query-mcp) → `ttr-server`.
Golems + capabilities-mcp → `kantheon`. Data (CNPG `hartland_us`/`hartland_cz`) → `data`.
Keycloak → `auth`. golem→metadata/query-mcp cross-ns, so those hosts must be FQDNs
(`metadata.ttr-server`, `query-mcp.ttr-server`), not bare names.

---

## 6. Data shape (hartland_us / hartland_cz)

- Two databases: `hartland_us`, `hartland_cz` (worker connections `pg-hartland-us`,
  `pg-hartland-cz`; also a `pg-tpcds`).
- Channel literals in the demo SQL are **lowercase** (`'store'`, `'web'`, `'marketplace'`)
  — see §3.3.
- Sales span 2024–2025 in full (24 months × 3 channels = 72 monthly rows); returns span
  2021–2026. `customer.c_birth_year` has a meaningful NULL population (drives the
  buyer_age null-age bucket, §2.4).
