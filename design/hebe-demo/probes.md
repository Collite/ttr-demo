# HB-P0 — probes: the live truth of the cluster Hebe

> **Partial P0 deliverable, 2026-07-27.** Probed while unblocking the Kantheon demo estate, not
> as a planned P0 run — so it answers the *identity / constellation-client* rows of the
> contracts-§2 table in depth and leaves the rest explicitly unprobed (§5). No cluster
> mutations were made for this document.
>
> Headline: **HB-P1 cannot start.** The OBO path is blocked on kantheon code that does not
> exist in any image, plus a Keycloak preview feature that is off. Neither is configuration.
> This is exactly the stop-and-flag condition [`plan.md`](./plan.md) names in its global
> pre-flight.

---

## 1. Blocker A — the P4 constellation client is not wired

Every building block for `kantheon_question` exists and is unit-tested. **None of it is
constructed in production code.** Repo-wide, `--include='*.kt'`, excluding `build/`:

| Symbol | Defined | Unit test | Constructed in prod |
|---|---|---|---|
| `IrisBffClient` | 1 | 4 refs | **never** |
| `ClientCredentialsExchangeGrant` | 1 | 1 ref | **never** |
| `OboTokenService` | 1 | spec | **never** |

Supporting parts that *do* exist: `KantheonDelivery`, `ConclusionRenderer`,
`RoutineRow.bodyKind` (a free string, so `kantheon_question` persists fine),
`scheduler/offline/*` (Catchup/Outbox/FallbackRouter all already reason about
`kantheon_question` in comments).

What is missing is the assembly:

1. `AgentFactory` never builds an `OboTokenService` — grep for it in `cli-app` returns only a
   doc-comment cross-reference in `ConsoleAuth.kt`.
2. Nothing turns a fired routine into an iris-bff call: no dispatch on `bodyKind`.

**Consequence.** The running Hebe cannot call the constellation at all, *regardless of
identity*. Fixing Keycloak would change nothing observable.

Evidence: `agents/hebe/modules/tools/builtin/.../kantheon/IrisBffClient.kt` (definition only);
`agents/hebe/modules/security/.../auth/OboTokenService.kt:125` (`ClientCredentialsExchangeGrant`,
definition only); the only call sites are `IrisBffClientTest.kt` and `OboTokenServiceSpec.kt`.

## 2. Blocker B — Keycloak will refuse this exchange

Hebe's k8s grant is a two-step: `client_credentials` → service token, then RFC 8693 exchange
with **`requested_subject`** — i.e. *impersonation*. Against Keycloak **26.5.1** (live image):

- **Standard token exchange (V2) explicitly rejects it.** `StandardTokenExchangeProvider.supports()`
  returns false when `requested_subject` is present: *"Parameter 'requested_subject' is not
  supported for standard token exchange"*.
- **Only legacy V1 handles it**, and per the 26.5 docs V1 is *"a preview feature not enabled by
  default."*
- V1 additionally rejects **public** clients on this path and requires the caller's service
  account to hold impersonation permission (`canClientImpersonate`).

Live state: the Keycloak StatefulSet has **no `KC_FEATURES` set at all** → V1 is off → the
exchange 403s.

So the identity substrate needs, in olymp:

- `KC_FEATURES=token-exchange:v1` on the Keycloak overlay
- a **confidential** `hebe` client in `realm/kantheon.json`, `serviceAccountsEnabled: true`
  (the realm currently ships only `iris`, `argocd`, `grafana`)
- impersonation permission for that service account (realm-management role, or fine-grained)
- a vault key for the client secret + an extra `data:` entry in
  `clusterexternalsecret-hebe-dev.yaml` (`keycloak-client-secret`, deliberately omitted when
  that CES was written because nothing read it)

⚠️ Enabling `token-exchange:v1` is a **preview** feature that grants a service account
user-impersonation rights on the demo realm. Worth a deliberate decision (⚑), not a side effect
of another task.

## 3. What this means for the demo

Beat 1 of the *Kantheon* demo (the overnight inbox item) does **not** actually require Hebe.
`iris/v1.ChatTurnRequest` already carries the origin fields, and the proto comment is explicit:

```proto
TurnOrigin origin = 6;          // SCHEDULED = 2 (Hebe routine)
optional string origin_ref = 7; // routine_id for SCHEDULED
// scheduled turns are persisted/routed/rendered exactly like user turns;
// origin is metadata … iris-bff must NOT gate on it.
```

A turn posted with `origin: SCHEDULED` therefore renders **identically** to one Hebe produced —
by design. With `iris` having `directAccessGrantsEnabled: true`, a script can mint Maya's token
by ROPC (demo-quirks §5.3) and post the brief. That is the path taken for the demo; it is a
**stand-in for Beat 1's artefact, not for Hebe** — the HB demo's own beats (phone deep-link,
memory, delegation, governance strikes) all still need the real thing.

## 4. Probed state (contracts §2 rows covered here)

| Row | Probed value (2026-07-27) |
|---|---|
| Pod state | `Running 1/1`, 0 restarts, app `hebe` Synced/Healthy |
| Instance | `HEBE_PROFILE=k8s`, `HEBE_INSTANCE_ID=dev`, `HEBE_SECRETS_DIR=/var/run/secrets/hebe` |
| `hebe-dev` secret (key names only) | `pg`, `llm-gateway-key`, `receipts.signing_key` — **no** `keycloak-client-secret`, **no** `telegram` |
| Storage | PG `hebe` DB, schema `hebe_dev`, Flyway v7 applied, pgvector 0.8.2 in `hebe_dev` |
| LLM egress | gateway 2.0 key accepted — `GET /v1/models` → **200** with hebe's own mounted key |
| Web channel | binds `0.0.0.0:8765`, `/health` → `OK` |
| Keycloak OBO wiring | **absent** — no `hebe` realm client, no client secret, V1 exchange disabled (§2) |
| Constellation client | **not wired** (§1) |
| Registry / `non_routable` | **not probed** |
| Console auth mode + reachability | **not probed** (⚑2 undecided) |
| Telegram config surface + egress | **not probed** (⚑3 — Bora-serial, still the earliest hard gate) |
| Image version vs `hebe/v0.4.0` | **not established** — deployed tag is the mutable `:testing`; §1 shows the P4 features are absent from *source*, so no tag carries them yet |

## 5. Recommendation

1. **Do not start HB-P1.** Its DONE criteria ("OBO mint verified") are unreachable until the P4
   wiring exists in kantheon. Re-sequence: the wiring is a kantheon implementation effort that
   precedes HB-P1, not part of it.
2. **Split the identity substrate out** (§2) so it can land independently and be verified with a
   direct `curl` token-exchange probe, before any Hebe code depends on it.
3. **⚑ for Bora:** is `token-exchange:v1` (preview + impersonation rights) acceptable on this
   realm? If not, the alternative is changing Hebe's grant to something V2 supports, which is a
   kantheon design decision, not a deployment one.
4. Complete the remaining §4 rows in a proper P0 pass — especially ⚑3, which gates P1 anyway.

## 6. HE-P1 · S1.1 identity probes (2026-10-23, no mutation)

Re-probed for HE-P1 · S1.1 T1 (`project/kantheon/features/hebe/tasks/tasks-p1-s1.1-identity-substrate.md`).
The §2 blocker is settled by HE-D-1: Hebe mints with the `refresh_token` grant from an offline token on its own
confidential client `hebe`, with no token exchange. These probes answer what that path needs from the live realm. They
used one ordinary persona password grant on the public `iris` client (the persona-turn recipe) and two refreshes of
its refresh token, plus the public discovery document.

| Question | Probed value |
|---|---|
| Q-1 — `offline_access` on `marketa` | **held**, through the realm's default composite: a fresh access token's `realm_access.roles` = `offline_access`, `uma_authorization`, `default-roles-kantheon`, `kantheon-area-hartland`, `kantheon-bi-reader`. The realm file assigns it to nobody directly; every user gets it from `default-roles-kantheon`. |
| Q-2 — the `aud` iris-bff requires | **none.** An `iris` token for marketa carries `aud=account` (the account-console roles, nothing else) and `azp=iris`. iris-bff's hartland values set `auth.keycloakIssuer` + `jwksUri` and no audience ("`iss` + signature bind them to this realm"). automation's `auth` sets `jwksUrl` + `issuer`, no audience. A `hebe`-client token is accepted on the same terms. |
| *Revoke Refresh Token* | **off** — the same `iris` refresh token was used twice and both refreshes succeeded (with it on, the second answers `invalid_grant`). Not set in the realm file, so the Keycloak default holds. |
| *Offline Session Idle* | **2592000 s (30 days)** — `offlineSessionIdleTimeout` in the realm file. |
| *Offline Session Max Limited* | **off** — `offlineSessionMaxLifespanEnabled: false` in the realm file. The one client cap in the realm is `superset-db`'s own `client.offline.session.max.lifespan`, which does not touch `hebe`. |
| Access / refresh lifetimes | access 300 s, SSO refresh 1800 s (the realm's SSO idle). |
| Discovery | `offline_access` in `scopes_supported`; `refresh_token` and `password` in `grant_types_supported`. |

**VERDICT (Q-1):** marketa already holds `offline_access`. The realm PR maps no role to her.
**VERDICT (Q-2):** no audience is required, so the `hebe` client carries no audience mapper. If iris-bff ever pins an
`aud`, the mapper goes on `hebe` and `iris` together.
**VERDICT (realm settings):** they fit HE-D-1 as they stand. The offline token outlives restarts, a refresh does not
rotate it out, and it dies only after 30 days without a mint (the VM-off rule, runbook-identity).
