# Runbook — a Hebe instance's identity on hartland

> HE-P1 · S1.1 T6 (`project/kantheon/features/hebe/tasks/tasks-p1-s1.1-identity-substrate.md`; HE contracts §2, §3,
> §9). The live realm facts behind it: [`probes.md`](./probes.md) §6.

A Hebe instance acts as **one** Keycloak user, its `bound_user` (instance `marketa` acts as Markéta). It holds that
user's **offline token** and mints her access token from it whenever it needs one: `grant_type=refresh_token` on the
confidential client `hebe`. Her password is typed once, to seed the token, and never again. Every call Hebe makes to
iris-bff carries her own bearer, so the platform sees Markéta, with exactly her roles.

Three things make it work. Each is a vault key the instance's ClusterExternalSecret hands to the pod:

| Vault key (hartland) | In the pod's `hebe-<id>` Secret as | Written by |
|---|---|---|
| `hebe-client-secret` | `keycloak-client-secret` (and the realm import) | `just hebe-seed-client-secrets` |
| `hebe-<id>-offline-token` | `keycloak-offline-token` | `just hebe-seed-offline-token <id> <user>` |
| *(literal)* `hebe` | `keycloak-client-id` | the CES template |

`hebe-console-oidc-client-secret` (the console's OIDC edge) is seeded by the same first script, but it is not part of
the instance's identity.

## 1. First seed (once per instance)

From a machine logged in with `az login` (Collite tenant), in a ttr-demo checkout:

1. `just hebe-seed-client-secrets`: creates both client secrets if the vault lacks them, and leaves existing ones
   alone. Do this **before** the realm PR merges, because the realm import reads them.
2. Merge the realm PR (olymp, `platform/auth/keycloak/overlays/hartland`). ArgoCD's PostSync job imports the
   `hebe` client. Check that `kubectl --context hartland -n auth get jobs` shows `keycloak-config-sync` Succeeded.
3. `just hebe-seed-offline-token marketa marketa`: prompts for the user's password, mints with
   `scope=openid offline_access`, and stores the token only when Keycloak answered `typ: Offline` for that user. It
   prints the length and `typ`, never the token. It refuses to overwrite an existing seed.
4. `just hebe-seed-offline-token marketa marketa --verify`: mints an access token from the vault's seed and prints
   `sub`, `preferred_username`, `azp` and `exp`. Expect `preferred_username=marketa azp=hebe`. It then opens an
   iris-bff session with that bearer and expects `POST /v1/session → 201`. Those two lines are S1.1 T4's proof that
   the identity substrate works. The vault is not changed.

If step 3 fails, the script names Keycloak's own error and the usual cause:

| Keycloak says | Cause |
|---|---|
| `Invalid user credentials` | wrong password. 30 misses start the realm's temporary lockout. |
| `Invalid client or Invalid client credentials` | the realm PR is not applied, or the vault value is not the one Keycloak imported. Re-sync the `auth` app. |
| `Offline tokens not allowed for the user or client` | the user lacks the realm role `offline_access`. Every user gets it from `default-roles-kantheon` (probes §6 Q-1), so something removed it. |
| a `Refresh` token, not `Offline` | the `hebe` client no longer offers the `offline_access` scope (realm JSON). Nothing was stored. |

## 2. What the instance shows

`hebe doctor` (and `/ready`, which gates the pod's readiness on the same mint):

| State | `hebe doctor` → `OBO mint` | `/ready` → `identity` |
|---|---|---|
| healthy | PASS `sub=… preferred_username=marketa azp=hebe aud=… exp=…` | ok, `preferred_username=marketa azp=hebe` |
| no seed in the Secret | FAIL `not configured: security.obo_grant=refresh_token requires the 'keycloak-offline-token' secret …` | 503 `OBO not configured: …` |
| seed dead (lapsed or signed out) | FAIL `mint failed: Keycloak refresh-token grant failed: HTTP 400`, hint: re-seed | 503 `OBO mint failed: …` |
| seed for the wrong user | FAIL `token is for <x>, bound_user is marketa` | 503 `… bound_user is marketa` |

A dead seed does not kill the pod: liveness is `/health`. With `readinessProbe.path: /ready`, though, the pod leaves
the Service, so the console is unreachable until the seed is fixed. Telegram polling and the scheduler keep running,
and routines that need the platform report the never-silent "platform unavailable" on the user's channels.

A **missing** seed is retried every minute, so a seed that arrives in the Secret later is picked up without a restart.
A seed that was read but no longer mints (dead, or the wrong user) needs the pod restarted after the Secret holds the
new one.

## 3. The 30-day rule (VM off → re-seed)

The realm's *Offline Session Idle* is **30 days**. The offline session dies 30 days after its last mint. A running
instance mints every few minutes, so the session never idles while the pod is up. *Offline Session Max Limited* is
off, so the token has no maximum age, and *Revoke Refresh Token* is off, so a mint does not spend the seed. The pod
keeps the token Keycloak hands back in memory, and after a restart it starts again from the vault seed, which is
still valid.

**If the hartland VM (or the instance) stays off for more than 30 days, the seed is dead.** After it comes back,
`/ready` answers `OBO mint failed`. Re-seed:

```sh
just hebe-seed-offline-token marketa marketa --rotate     # prompts for the password, replaces the vault's seed
just hebe-seed-offline-token marketa marketa --verify
kubectl --context hartland -n kantheon annotate externalsecret hebe-marketa force-sync="$(date +%s)" --overwrite
kubectl --context hartland -n kantheon rollout restart deploy/hebe   # once the Secret holds the new seed
```

## 4. Rotation

- **The offline token** (a suspected leak, or a different user): `--rotate` as above. The old offline session is not
  revoked by the script. Sign it out in the admin console (realm `kantheon` → Users → the user → Sessions → the
  `hebe` offline session → Sign out) once the pod runs on the new seed, or let it lapse after 30 idle days.
- **The `hebe` client secret:** in this order:
  1. `az keyvault secret set --vault-name hartland --name hebe-client-secret --value "$(openssl rand -hex 32)" --output none`
  2. wait for ESO (≤ 1 h), or force it: annotate the `hebe-client-secret` ExternalSecret in `auth`, and each instance's
     `hebe-<id>` ExternalSecret in `kantheon`, with `force-sync=$(date +%s)`;
  3. sync the `auth` Application so the PostSync job re-imports the realm;
  4. restart every Hebe instance once its Secret has the new value.

  Offline tokens survive a client-secret rotation, because they belong to the client, not to its secret. Between
  steps 3 and 4 the instances' mints fail with `invalid_client`.
- **The `hebe-console` secret:** the same 1 → 3, then let the console's `hebe-console-oidc` Secret (ns `kantheon`)
  refresh. Signed-in browser sessions sign in again.

## 5. The alternative: token exchange

`security.obo_grant = "token_exchange"` stays selectable in Hebe (⚑HE-1 → α). The instance then holds no user
token. It exchanges its own client-credentials token for the bound user's (impersonation). Keycloak 26's standard
token exchange (V2) refuses impersonation, so this needs the legacy preview `KC_FEATURES=token-exchange:v1`, a
`hebe` client with a service account, and an impersonation permission on the realm (the v1 contracts' §3.2). HE-D-1
chose the offline token instead: no preview feature, no realm-wide impersonation right, and a credential scoped to one
user that the admin console can sign out. Its cost is the 30-day rule above.
