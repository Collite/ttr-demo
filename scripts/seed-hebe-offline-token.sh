#!/usr/bin/env bash
# Seed a Hebe instance's offline token: the credential it acts as its bound user with (HE-D-1; HE-P1 · S1.1 T3;
# tasks-bora-unblock B-3; HE contracts §3, §9).
#
#   ./seed-hebe-offline-token.sh <instance> <user>             # prompts for <user>'s password; refuses to overwrite
#   ./seed-hebe-offline-token.sh <instance> <user> --rotate    # the same, replacing the vault's seed
#   ./seed-hebe-offline-token.sh <instance> <user> --verify    # no seed: mint from the vault's seed, print who it is,
#                                                              # and open an iris-bff session with it (T4's proof)
#
# The seed is one password grant on the confidential client `hebe` with `scope=openid offline_access`. Keycloak answers
# with an OFFLINE refresh token (`typ: Offline`), and the script stores it as vault secret
# `hebe-<instance>-offline-token`. The instance's ClusterExternalSecret hands it to the pod as
# `keycloak-offline-token`. The pod then mints with `grant_type=refresh_token`, and the password is never used again.
#
# The token lives as long as Keycloak keeps the offline session: 30 days without a mint ends it (the realm's offline
# idle). A running instance mints every few minutes, so only a VM that stays off longer than that needs a re-seed:
# `--rotate`, then force ESO to refresh the instance Secret and restart the pod (design/hebe-demo/runbook-identity.md
# §3). The old offline session is not revoked here. It lapses after 30 idle days, or the user's Sessions tab in the
# admin console signs it out. The verify step leaves the vault alone: with the realm's "Revoke Refresh Token" off, a
# refresh does not spend the seed. It then shows the platform accepts the minted bearer: `POST $IRIS_BFF_URL/v1/session`
# must answer 201 (an empty session for the user, as an Iris login makes). Set IRIS_BFF_URL= to skip that step.
#
# The password, the client secret and both tokens are NEVER printed and never passed in argv. curl reads them from
# mode-0600 files (`--data-urlencode name@file`, the bearer as `-H @file`), az writes from one (`--file`), and the
# directory is removed on exit.
set -euo pipefail

VAULT="${VAULT:-hartland}"
KC_URL="${KC_URL:-https://keycloak.hartland.collite.cz}"
KC_REALM="${KC_REALM:-kantheon}"
CLIENT_ID="${CLIENT_ID:-hebe}"
CLIENT_SECRET_NAME="${CLIENT_SECRET_NAME:-hebe-client-secret}"
IRIS_BFF_URL="${IRIS_BFF_URL-https://iris.hartland.collite.cz/bff}"

usage() { echo "usage: $0 <instance> <user> [--rotate|--verify]" >&2; exit 2; }
[ $# -ge 2 ] && [ $# -le 3 ] || usage
INSTANCE="$1"
BOUND_USER="$2"
MODE=seed
case "${3:-}" in
  --rotate) MODE=rotate ;;
  --verify) MODE=verify ;;
  "") ;;
  *) usage ;;
esac
case "$INSTANCE" in
  ""|*[!a-z0-9-]*) echo "instance must be [a-z0-9-]+ (it names the vault secret): '$INSTANCE'" >&2; exit 2 ;;
esac

SEED_NAME="hebe-${INSTANCE}-offline-token"
TOKEN_URL="${KC_URL}/realms/${KC_REALM}/protocol/openid-connect/token"

TMP="$(umask 077; mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

say() { printf '==> %s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

# One field of a JSON file ("" when absent).
json_field() {
  python3 -c 'import json, sys
v = json.load(open(sys.argv[1])).get(sys.argv[2])
sys.stdout.write("" if v is None else str(v))' "$1" "$2"
}

# `name=value` lines for the named claims of the JWT in a file. No signature check: Keycloak has just issued it over
# TLS, and this only reports what it says.
jwt_claims() {
  python3 -c 'import base64, json, sys
tok = open(sys.argv[1]).read().strip()
part = tok.split(".")[1] if tok.count(".") == 2 else ""
part += "=" * (-len(part) % 4)
try:
    claims = json.loads(base64.urlsafe_b64decode(part))
except Exception:
    claims = {}
for k in sys.argv[2:]:
    v = claims.get(k, "")
    print("%s=%s" % (k, v))' "$@"
}
claim() { jwt_claims "$1" "$2" | sed "s/^$2=//"; }

# The vault secret [1] into file [2], without a trailing newline. Non-zero when absent.
vault_get() {
  az keyvault secret show --vault-name "$VAULT" --name "$1" --query value -o tsv 2>/dev/null | tr -d '\n' > "$2"
  [ -s "$2" ]
}

# POST to the token endpoint as `hebe`. The client secret goes from its file, any further `--data-urlencode` args as
# given. The body lands in $TMP/resp.json, and the HTTP status is echoed.
post_token() {
  curl -sS -o "$TMP/resp.json" -w '%{http_code}' -X POST "$TOKEN_URL" \
    --data-urlencode "client_id=${CLIENT_ID}" \
    --data-urlencode "client_secret@${TMP}/client_secret" \
    "$@"
}

# Keycloak's own error, which names the cause and carries no secret, plus what usually causes it here.
keycloak_error() {
  local status="$1" err desc
  err="$(json_field "$TMP/resp.json" error 2>/dev/null || true)"
  desc="$(json_field "$TMP/resp.json" error_description 2>/dev/null || true)"
  printf 'ERROR: Keycloak answered HTTP %s: %s%s\n' "$status" "${err:-?}" "${desc:+ ($desc)}" >&2
  case "$err $desc" in
    *"Offline tokens not allowed"*)
      echo "       '$BOUND_USER' lacks the realm role offline_access (probes.md §6 Q-1: default-roles-kantheon carries it)." >&2 ;;
    *unauthorized_client*|*invalid_client*|*"Invalid client"*)
      echo "       the '$CLIENT_ID' client or its secret: is the realm PR applied (B-2) and '$CLIENT_SECRET_NAME' the value it imported?" >&2 ;;
    *"Invalid user credentials"*)
      echo "       wrong password for '$BOUND_USER' (5+ misses start the realm's temporary lockout)." >&2 ;;
    *invalid_grant*)
      [ "$MODE" = verify ] && echo "       the offline session is gone (30 days without a mint, or signed out): re-seed with --rotate." >&2 ;;
  esac
  exit 1
}

command -v az >/dev/null 2>&1 || die "az CLI not found"
command -v curl >/dev/null 2>&1 || die "curl not found"
command -v python3 >/dev/null 2>&1 || die "python3 not found"
az account show >/dev/null 2>&1 || die "not logged in to Azure — run: az login"

vault_get "$CLIENT_SECRET_NAME" "$TMP/client_secret" \
  || die "vault '$VAULT' has no '$CLIENT_SECRET_NAME' — run scripts/seed-hebe-client-secret.sh and apply the realm PR first (B-2)"

if [ "$MODE" = verify ]; then
  vault_get "$SEED_NAME" "$TMP/seed" || die "vault '$VAULT' has no '$SEED_NAME' — nothing to verify (seed it first)"
  STATUS="$(post_token --data-urlencode "grant_type=refresh_token" --data-urlencode "refresh_token@${TMP}/seed")" \
    || die "could not reach $TOKEN_URL"
  [ "$STATUS" = 200 ] || keycloak_error "$STATUS"
  json_field "$TMP/resp.json" access_token > "$TMP/access"
  [ -s "$TMP/access" ] || die "Keycloak answered 200 without an access_token"
  WHO="$(claim "$TMP/access" preferred_username)"
  AZP="$(claim "$TMP/access" azp)"
  EXP="$(claim "$TMP/access" exp)"
  EXP_UTC="$(python3 -c 'import datetime, sys; print(datetime.datetime.fromtimestamp(int(sys.argv[1]), datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))' "${EXP:-0}")"
  say "minted from '$SEED_NAME': sub=$(claim "$TMP/access" sub) preferred_username=$WHO azp=$AZP exp=$EXP_UTC"
  [ "$WHO" = "$BOUND_USER" ] || die "the seed acts as '$WHO', not '$BOUND_USER' — re-seed it for the right user (--rotate)"
  [ "$AZP" = "$CLIENT_ID" ] || die "the token was minted for client '$AZP', not '$CLIENT_ID'"
  [ -n "$IRIS_BFF_URL" ] || exit 0
  { printf 'Authorization: Bearer '; cat "$TMP/access"; } > "$TMP/auth_header"
  STATUS="$(curl -sS -o "$TMP/session.json" -w '%{http_code}' -X POST "${IRIS_BFF_URL}/v1/session" \
    -H @"$TMP/auth_header" -H 'Content-Type: application/json' --data '{}')" || die "could not reach $IRIS_BFF_URL"
  if [ "$STATUS" != 201 ]; then
    printf 'ERROR: iris-bff answered HTTP %s to POST /v1/session: %s\n' "$STATUS" \
      "$(json_field "$TMP/session.json" errorCode 2>/dev/null || true)" >&2
    [ "$STATUS" = 401 ] && echo "       iris-bff refused the bearer: check its auth.keycloakIssuer and whether it now pins an audience (probes.md §6 Q-2)." >&2
    exit 1
  fi
  say "iris-bff accepted it: POST /v1/session → 201 (session $(json_field "$TMP/session.json" sessionId))"
  exit 0
fi

if [ "$MODE" = seed ] && vault_get "$SEED_NAME" "$TMP/existing"; then
  die "vault '$VAULT' already holds '$SEED_NAME'. Use --verify to check it, --rotate to replace it."
fi
rm -f "$TMP/existing"

# The password: prompted, never echoed, never in argv. It exists in one 0600 file only while one curl runs.
printf 'Password for %s (Keycloak realm %s): ' "$BOUND_USER" "$KC_REALM" >&2
IFS= read -rs PASSWORD || true
printf '\n' >&2
[ -n "${PASSWORD:-}" ] || die "no password given"
printf '%s' "$PASSWORD" > "$TMP/password"
unset PASSWORD

STATUS="$(post_token --data-urlencode "grant_type=password" --data-urlencode "username=${BOUND_USER}" \
  --data-urlencode "password@${TMP}/password" --data-urlencode "scope=openid offline_access")" \
  || { rm -f "$TMP/password"; die "could not reach $TOKEN_URL"; }
rm -f "$TMP/password"
[ "$STATUS" = 200 ] || keycloak_error "$STATUS"

json_field "$TMP/resp.json" refresh_token > "$TMP/seed"
json_field "$TMP/resp.json" access_token > "$TMP/access"
[ -s "$TMP/seed" ] || die "Keycloak answered 200 without a refresh_token"
TYP="$(claim "$TMP/seed" typ)"
[ "$TYP" = Offline ] || die "Keycloak issued a '$TYP' refresh token, not an Offline one: does the '$CLIENT_ID' client offer the offline_access scope (realm PR)? Nothing was stored."
WHO="$(claim "$TMP/access" preferred_username)"
[ "$WHO" = "$BOUND_USER" ] || die "the token is for '$WHO', not '$BOUND_USER'. Nothing was stored."

az keyvault secret set --vault-name "$VAULT" --name "$SEED_NAME" --file "$TMP/seed" --encoding utf-8 --output none
vault_get "$SEED_NAME" "$TMP/seed.rt" || die "vault round-trip: '$SEED_NAME' reads back empty"
cmp -s "$TMP/seed" "$TMP/seed.rt" || die "vault round-trip altered '$SEED_NAME'. The instance would fail to mint."
say "stored '$SEED_NAME' in vault '$VAULT': $(wc -c < "$TMP/seed" | tr -d ' ') chars, typ=$TYP, for $WHO"

cat <<NEXT

==> done. The offline token is in the vault only; it was never printed.
    check:  $0 $INSTANCE $BOUND_USER --verify
    next:   the instance's ClusterExternalSecret (olymp) hands it to the pod as 'keycloak-offline-token'.
NEXT
