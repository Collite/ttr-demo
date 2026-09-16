# Hartland demo — operations manual

> **The "how to run it" companion** to [`demo-transcript.md`](./demo-transcript.md) (the
> narrative) and [`demo-quirks.md`](./demo-quirks.md) (the gotchas). This document is the
> presenter/operator's runbook for the live **`hartland` showcase cluster**: how to reach it,
> how to log in, who the demo users are, what runs where, and the recipes that keep the demo
> repeatable. Deployment **truth** stays in `olymp/clusters/hartland/` + `olymp/platform/*` —
> this manual cites it; if they ever drift, the olymp repo wins.
>
> Status note: the `just demo-reset` / `pre-show` / `demo-check` recipes are **planned**
> (plan-cluster H5 / tasks-p3-s5) and may not exist yet on your checkout — §7 gives the manual
> equivalents to use until they land.

---

## 1. The cluster at a glance

- **One K3s node**, amd64, public IP **`20.218.224.115`** (Azure). Kube-context **`hartland`**
  (context = cluster name, olymp D24). 8 CPU; scheduling *requests* are shrunk estate-wide so
  everything fits — cold starts are slow by design, warm before the show (§7.3).
- **Base domain: `*.20-218-224-115.nip.io`** — nip.io wildcard DNS onto the node IP. No DNS
  setup needed on any machine; any resolver on the internet resolves these names.
- **GitOps**: ArgoCD self-manages the cluster from `olymp` `master` (app-of-apps
  `root-app-hartland.yaml`). App changes = olymp commits; ArgoCD auto-syncs
  (`demo-quirks.md` §5.4 for forcing a refresh).
- **Namespaces** (quirks §5.5): spine (veles, query, validate, translate, dispatch, workers,
  query-mcp, llm-gateway) → `ttr-server` · golems + capabilities-mcp → `kantheon` · CNPG
  warehouses (`hartland_us`, `hartland_cz`) → `data` · Keycloak → `auth` · Envoy Gateway →
  `gateway` · ArgoCD → `argocd` · monitoring → `monitoring`.
- **Model source**: veles serves the TTR-M model from **this repo** (`Collite/ttr-demo`,
  branch `demo-p2`, subdir `model/`); golems cache the ModelBundle at boot — see §7.4 for the
  two-step refresh after any model change.

### External URLs (the complete set)

Only five hostnames have routes through the gateway. **Everything else is ClusterIP —
in-cluster only** (reach it via `kubectl port-forward`, §6).

| Surface | URL | Login |
|---|---|---|
| **Iris** (the demo surface) | `https://iris.20-218-224-115.nip.io` | Keycloak SSO (demo personas) |
| Landing (cosmetic dispatcher) | `https://landing.20-218-224-115.nip.io` | none (auth off) |
| Keycloak (IdP + admin console) | `https://keycloak.20-218-224-115.nip.io` | `admin` + secret (§3.3) |
| ArgoCD (GitOps UI) | `https://argocd.20-218-224-115.nip.io` | Keycloak SSO **or** local `admin` (§3.4) |
| Grafana (monitoring) | `https://grafana.20-218-224-115.nip.io` | Keycloak SSO |

---

## 2. TLS — what to set up before the show

**Everything external is HTTPS**, terminated at the shared Envoy Gateway (`eg`, listener
`:443`) with a **wildcard certificate from the cluster's own private CA** — root
"**Kantheon hartland Kubernetes CA**" (cert-manager `selfsigned-issuer` → `hartland-root-ca`
→ ClusterIssuer `hartland-ca-issuer` → `gateway-tls` in ns `gateway`). A port-80 HTTP
listener also exists, but Keycloak's public hostname (`KC_HOSTNAME`) and every OIDC
redirect/web-origin is pinned `https://` — **use HTTPS only**, or logins will break on
mixed-scheme redirects.

Because the CA is private, an untouched browser shows a certificate warning on every
hostname. Two ways to handle it:

1. **(Recommended for demo machines)** Trust the root CA once, per machine. Extract it from
   the live cluster:

   ```sh
   kubectl --context hartland -n gateway get secret gateway-tls \
     -o jsonpath='{.data.ca\.crt}' | base64 -d > hartland-root-ca.crt
   ```

   macOS: `open hartland-root-ca.crt` → add to Keychain → set **Always Trust** for SSL
   (or: System Settings → Keychain Access). Firefox keeps its own store: Settings →
   Privacy & Security → Certificates → Import. After trusting, **all five hostnames go
   green** (the cert is a wildcard for `*.20-218-224-115.nip.io` + apex).

2. **(Fallback)** Click through the warning **once per hostname, per browser profile**. If
   you go this way, do it for *all five hosts* in *both* browser profiles (Maya's and the
   CFO's — Satellite G uses a second profile) during pre-show, never on stage. Watch out:
   the Iris SPA calls Keycloak cross-origin — if you skipped the Keycloak host, Iris hangs
   at a blank redirect.

In-cluster hops (SPA→iris-bff, bff→agents, agents→spine) are plain HTTP behind the gateway
— that is by design (Keycloak runs `proxy: xforwarded`; ArgoCD `server.insecure: true`);
nothing to configure. ArgoCD's OIDC discovery has `oidc.tls.insecure.skip.verify: true` for
the same private-CA reason — leave it.

---

## 3. Logging in — who, where, how

### 3.1 The one answer

**Yes — every *persona-facing* login is "Log in with Keycloak"**: one Keycloak per cluster,
realm **`kantheon`**, and Iris, ArgoCD, and Grafana are all OIDC clients of it (realm-as-code:
`olymp/platform/auth/keycloak/overlays/hartland/realm/kantheon.json`, re-applied idempotently
by the `keycloak-config-sync` PostSync job — manual realm edits get overwritten on the next
sync; durable changes go through that file). The two exceptions: **Landing** has auth off
(it's a link page), and the **Keycloak admin console + ArgoCD local admin** are
break-glass logins outside the realm.

Opening Iris redirects straight to the Keycloak login form (keycloak-js `login-required`,
public client `iris`, PKCE S256) — enter a persona from the table below and you land back in
Iris. Logout: Iris user menu → logout (post-logout redirect is registered). For the CFO
cameo, keep a **second browser profile** logged in as Dan/Tomáš — don't log Maya out.

### 3.2 The demo personas (realm `kantheon`)

All four share the password **`Hartland!2026`** (non-temporary). Username or email works.

| User | Email | Password | Realm roles | World / locale | Discover shows |
|---|---|---|---|---|---|
| **Maya Chen** — Senior Category Manager | `maya@hartland.example` (username `maya`) | `Hartland!2026` | `kantheon-area-hartland` | US / en-US | **1 card** (Hartland Analytics) |
| **Dan Whitaker** — CFO | `cfo@hartland.example` (username `dan`) | `Hartland!2026` | `kantheon-area-hartland` + `kantheon-role-finance` | US / en-US | **2 cards** (+ Hartland Finance) |
| **Markéta Nováková** — Senior Category Manager (CZ) | `marketa@hartland.example` (username `marketa`) | `Hartland!2026` | `kantheon-area-hartland` | CZ / cs-CZ | **1 card** |
| **Tomáš Horák** — Finanční ředitel (CZ) | `cfo-cz@hartland.example` (username `tomas`) | `Hartland!2026` | `kantheon-area-hartland` + `kantheon-role-finance` | CZ / cs-CZ | **2 cards** |

One locale per delivery (BM-8): EN delivery = Maya + Dan over `hartland_us`; CZ delivery =
Markéta + Tomáš over `hartland_cz`. The visibility contrast (1 vs 2 cards) is the Satellite-G
beat — verify it at pre-show (E-5 item 6).

### 3.3 Keycloak admin

Admin console at `https://keycloak.20-218-224-115.nip.io` — user **`admin`**, password from
the cluster secret (vault-sourced via ESO, `keycloak-admin-creds`):

```sh
kubectl --context hartland -n auth get secret keycloak-admin-creds \
  -o jsonpath='{.data.admin-password}' | base64 -d
```

Needed only for diagnostics (checking a user's roles, watching login events). Remember §3.1:
realm state is code — don't hand-edit users/clients you want to keep.

### 3.4 ArgoCD & Grafana

- **ArgoCD** — "LOG IN VIA KEYCLOAK" works for any realm user, but RBAC maps realm *groups*:
  `admins` → admin, everyone else → readonly (`policy.default: role:readonly`). The demo
  personas are in **no group** → they get read-only, which is exactly right for showing the
  estate. For admin work use the local `admin` +
  `kubectl --context hartland -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d`,
  or put your own user in the `admins` group via the realm file.
- **Grafana** — Keycloak OIDC (client `grafana`), same group mapping; admin fallback secret
  `grafana-admin` in ns `monitoring`.

---

## 4. How to work — the access map

### 4.1 Does everything run through Iris?

For the **audience-facing demo — yes, by design**. Iris is the only externally-routed persona
surface, and every agent on stage is reached *through* it:

```
Browser ── https ──► Envoy Gateway (:443, TLS, wildcard cert)
                        │ HTTPRoute iris.20-218-224-115.nip.io
                        ▼
                     iris (nginx SPA, ns kantheon) ── same-origin /bff proxy ──► iris-bff (:7410)
                                                                                   │ bearer forwarded (OBO)
                     ┌─────────────────────────────────────────────────────────────┤
                     ▼                       ▼                    ▼                ▼
                  themis-mcp (:7901)      golem-hartland(-finance) (:7420)      pythia · hebe
                  (routing)               (pattern/free-SQL answers)            (RCA · routines)
                                             │
                                             ▼  (all in ns ttr-server)
                                          query-mcp → theseus→proteus→argos→kyklop→arges
                                             │                                    │
                                          veles (model, from Collite/ttr-demo)  CNPG data ns:
                                                                                 hartland_us / hartland_cz
```

So: **Golem** = open a Discover card and chat (Beat 2) · **Pythia** = the *Investigate* chip
on an answer (never Golem→Pythia direct — routing goes back through Iris/Themis; the
investigation pane, budget meter and hypothesis tree render inside Iris) · **Hebe** = the
inbox item its routine wrote (Beat 1) and *create-from-chat* (Beat 6) · **Themis** = invisible
router, no surface · **Metis/Charon** = machinery behind the forecast beat, surfaced only as
ⓘ provenance.

**Iris is available outside the cluster** (that's the whole point); the *agents are not* —
no golem/pythia/themis/hebe HTTPRoute exists. Anything not in the §1 URL table is reachable
only in-cluster or by port-forward (§6).

### 4.2 The warehouse

`hartland_us` and `hartland_cz` live on the cluster's CNPG in ns `data`, read-only roles via
ESO secrets (`pg-hartland-us-ro`, `pg-hartland-cz-ro`; a legacy `pg-tpcds-ro` also exists).
The demo never writes to them, and `demo-reset` must never touch them. For ad-hoc `psql`:

```sh
kubectl --context hartland -n data port-forward svc/postgres-rw 5432:5432 &
kubectl --context hartland -n data get secret pg-hartland-us-ro -o yaml   # check the key names
PGPASSWORD="$(kubectl --context hartland -n data get secret pg-hartland-us-ro \
  -o jsonpath='{.data.password}' | base64 -d)" \
  psql -h localhost -U hartland_readonly -d hartland_us   # role per plan-cluster H2.1 (verify in the secret)
```

(The gateway also declares raw-TCP listeners on 5432/5433 for external Postgres — check the
TCPRoutes under `platform/data/*/overlays/hartland` before relying on them; port-forward is
the always-works path. Remember quirks §5.2: a port-forward dies with the shell call that
started it — do forward + query in one invocation when scripting.)

---

## 5. Verification & smoke — is the demo path alive?

Run before every rehearsal (this is the H4 `demo-check` scope until the recipe lands):

1. **Estate green**: `kubectl --context hartland -n argocd get applications` (or the ArgoCD
   UI) — everything Synced/Healthy.
2. **Model served**: veles `ListQueries` shows **15/15 `PARSED`** (grpcurl recipe: quirks
   §1.4; parse status is async — §1.3).
3. **One live turn per world** — the full ROPC recipe from quirks §5.3 in a single shell
   call: mint Maya's token (`grant_type=password&client_id=iris&username=maya&password=Hartland!2026&scope=openid`
   against `POST /realms/kantheon/protocol/openid-connect/token`), then
   `POST /v1/answer/sync` to `golem-hartland:7420` with a scripted question; expect rows,
   not 0 (and remember the §0 meta-quirk — *0 rows means check the query-service log*, not
   "no data").
4. **Persona contrast**: log in as Maya (1 Discover card) and Dan (2 cards).
5. **The run-set**: `hartland-query` oracle run (run-set/, H4) — all 15 queries return the
   oracle rows.
6. **LLM reachability**: Prometheus/llm-gateway probe — the demo answers live; a dead
   provider key is a show-stopper you want at T-60, not on stage.

---

## 6. Reaching the internals (ops/debug only)

| Target | Namespace / svc:port | Note |
|---|---|---|
| golem-hartland / -finance | `kantheon` / `:7420` | REST `/v1/answer/sync`, `/v1/resume` (quirks §5.3) |
| capabilities-mcp | `kantheon` / `:7501` | Shem registration; Discover reads this |
| veles | `ttr-server` / `:7260` http-ready, `:7261`+gRPC | no reflection — bring the protos (quirks §1.4) |
| query-mcp | `ttr-server` / `:7307` `/mcp` | the executor's query edge |
| llm-gateway | `ttr-server` / `:7280` `/v1` | Ktor 2.0 surface, `ttrk-` keys |
| themis-mcp | `ttr-server` / `:7901` | REST `/v1/resolve` |
| iris-bff | `kantheon` / `:7410` | normally only via the SPA's `/bff` proxy |
| Keycloak (in-cluster) | `auth` / `auth-keycloak-keycloakx-http:80` | token endpoint for scripted turns |
| Postgres | `data` / `postgres-rw:5432` | §4.2 |

`kubectl --context hartland -n <ns> port-forward svc/<svc> <local>:<port>` — one shell call
per scripted flow (quirks §5.2).

Logs worth knowing: **`ttr-server/query-*`** (the real error behind any "0 rows" —
quirks §0, grep the `correlation_id`) · golem pod logs in `kantheon` (turn orchestration) ·
`keycloak-config-sync` job logs in `auth` (realm import failures).

---

## 7. Standing operations

### 7.1 Demo reset (H5.1 T1 — scripted as `just demo-reset hartland` when it lands)

Truncate **session** state only: Iris sessions/SSE + feedback; Pythia investigations
**except** the pinned rehearsal investigation. **Preserve** the standing fixtures: the
"Channel Health" + "Rehearsal" dashboards, the "Monday channel health brief" Hebe routine,
all Keycloak users, and the warehouses (read-only, never dirtied). Until the recipe exists,
that means deleting session rows via each store's API/DB (iris-bff `iris` DB, pythia
`pythia` DB on the central PG) — do it with the fixture allow-list in front of you.

### 7.2 After a model or query change (the two-refresh rule — quirks §1.2)

1. Push to `Collite/ttr-demo` (branch `demo-p2`).
2. veles re-fetch: `VelesService/Refresh {force:true}` (or wait out the poll); confirm
   `ListQueries` → PARSED.
3. **`kubectl --context hartland -n kantheon rollout restart deployment/golem-hartland`**
   (and `golem-hartland-finance`) — golems cache the ModelBundle at boot; skipping this is
   the classic phantom-0-rows.

Never inside the freeze window (§7.5).

### 7.2b A ConfigMap sync is not a vocabulary reload (lexicon)

`lex-matcher` (the `fuzzy` deployment) loads the compiled lexicon archive **at boot** and
re-checks it on `refreshIntervalSeconds` — service default **3600**, overridable by
`FUZZY_REFRESH_INTERVAL_SECONDS`; a value `<= 0` means manual-only, with no background loop at
all. **This cluster sets 600** (olymp `clusters/hartland/apps/fuzzy/values.yaml`), so the window
is at most ten minutes rather than an hour. An ArgoCD sync that replaces the archive ConfigMap
therefore changes nothing the matcher is serving until then: the new vocabulary is on disk and the
old one is still in memory.

After any lexicon change, do one of:

1. wait out the refresh interval — up to **ten minutes** on this cluster;
2. `POST /refresh` on lex-matcher — admin-gated, a caller without the admin role gets 403;
3. **`kubectl --context hartland -n ttr-server rollout restart deploy/fuzzy`** — deterministic,
   and still the one to use before a show: the shorter interval bounds the window, it does not close it.

The record, because it is what makes this worth a section: on **2026-08-13** fuzzy loaded
**307 entries at 06:37**, ArgoCD synced the **351**-entry archive at **08:49**, and the next
refresh tick was **~09:37** — a 48-minute window in which every ConfigMap on the cluster showed
the new vocabulary and the matcher served the old one.

### 7.3 Pre-show (T-60 → T-10; scripted as `just pre-show hartland` when it lands)

1. `demo-reset` (§7.1).
2. **Warm everything**: the node idles with shrunk requests — first tokens are cold. One
   throwaway Golem turn + one Pythia turn (as a *throwaway* session, not Maya's).
3. **Fire the "Monday channel health brief" routine** — Beat 1 needs the inbox item.
4. LLM latency probe (§5.6).
5. Login checklist: browser profile 1 = Maya (or Markéta), profile 2 = CFO persona, both
   with the CA trusted (§2), both showing the right Discover cards.
6. Second screen: ArgoCD read-only view if you want the "it's all real" flash.

### 7.4 ArgoCD nudges

Force re-read: `kubectl annotate application <app> -n argocd argocd.argoproj.io/refresh=hard --overwrite`.
Values/`extraEnv` changes roll pods automatically (Deployment-spec change). Remember Helm
`extraEnv` **replaces** the chart list (quirks §4.2) — carry the defaults over.

### 7.4b The golem image tag is pinned by hand

`sys-image-updater` will never move the golem pin, so do not wait for it. Its golem rule names
the image `ghcr.io/boraperusic/golem` and writes back to
`clusters/hartland/apps/golem/values.yaml` — a path that no longer exists, replaced when
`appset-golems` took over from the single golem app. The running golems take their image from
`clusters/hartland/golems/_values.yaml` (`ghcr.io/collite/golem`), which the updater never
touches.

So after cutting a golem image: **bump the tag in `golems/_values.yaml` by hand and merge** —
on olymp, merge to `master` IS the deploy. Until the rule is fixed (out of scope here), treat a
new golem release as un-deployed until you have seen its tag in that file.

### 7.5 The freeze window (E-1/G1)

From "demo-ready declared" to show day: **no chart, image, or model changes** — images move
pin-to-pin by PR only; the Ariadne source ref is pinned. The only permitted operations are
`demo-reset` and the daily `demo-check`. The freeze covers this repo's `model/` + `run-set/`
too.

---

## 8. Troubleshooting quick table

| Symptom | First move |
|---|---|
| Answer comes back "0 rows" | quirks §0 — pull `ttr-server/query-*` log by `correlation_id`; it's almost never the data |
| Golem serves stale/old SQL after a model push | you forgot the golem rollout restart — §7.2 / quirks §1.2 |
| New lexicon term still not matching after an ArgoCD sync | §7.2b — a ConfigMap sync is not a vocabulary reload; fuzzy re-reads every 10 min here |
| Query fails parse in veles but runs in psql | Calcite is stricter — quirks §2 (reserved words, alias GROUP BY, `{brace}` params only) |
| Series truncated at N rows | validator TopN ceiling — `VALIDATE_DEFAULT_TOP_N` (=100 on hartland), quirks §4.1 |
| Text param matches nothing ("Marketplace") | case-sensitivity — phrase the utterance lowercase until the CaseFoldingParams release lands (quirks §3.3) |
| Browser hangs at blank page entering Iris | Keycloak host cert not accepted in *that* profile — §2 |
| Login loops / redirect error | scheme mismatch — you entered via `http://`; use `https://` (§2) |
| Discover shows wrong card count | check realm roles in Keycloak admin (§3.3); then capabilities-mcp registration (quirks: Shem assembles but never registers) |
| Pod stuck in Init (`wait-for-veles`) | cross-ns FQDN gate — check `velesGate.url` (golems `_values.yaml`) |
| Pod ImagePullBackOff after a local build | arm64-only image — rebuild with `CI=true` multi-arch (quirks §5.1) |
| ExternalSecret app perpetually OutOfSync | known ESO-defaulting noise — already normalized in ArgoCD values; hard-refresh |

---

*Sources of truth: `olymp/clusters/hartland/` (apps, golems, argocd, cert-manager) ·
`olymp/platform/auth/keycloak/{base,overlays/hartland}` (realm, SSO) ·
`olymp/platform/gateway/overlays/hartland` (gateway, TLS) · [`demo-quirks.md`](./demo-quirks.md) ·
[`tasks/tasks-p3-s5-dry-run-readiness.md`](./tasks/tasks-p3-s5-dry-run-readiness.md) (the
recipes this manual anticipates).*
