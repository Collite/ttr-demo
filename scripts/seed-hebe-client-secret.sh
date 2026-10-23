#!/usr/bin/env bash
# Seed the two Keycloak client secrets Hebe's realm clients read (HE-P1 · S1.1 T3; tasks-bora-unblock B-2.1).
#
#   ./seed-hebe-client-secret.sh       # idempotent: creates each key only if the vault lacks it
#
# Run it BEFORE merging the realm PR (olymp platform/auth/keycloak/overlays/hartland). The realm import's
# ExternalSecrets read these keys, and a missing key keeps the PostSync sync job from starting.
#
#   hebe-client-secret               the `hebe` client (HE-D-1). Every hebe-<id> instance Secret also carries it,
#                                    as `keycloak-client-secret`, and mints its user's token with it.
#   hebe-console-oidc-client-secret  the `hebe-console` client (HE-D-5). The console's Envoy Gateway OIDC edge
#                                    also reads it (the hebe-console-oidc Secret in ns kantheon).
#
# Each value is 32 random bytes as 64 hex characters. Hex, because `+/=` in a client secret can break the edge's
# `Authorization: Basic` header. A value is NEVER printed and never passed in argv. It exists only in a
# mode-0600 temp file, removed on exit, and in the vault. Rotation is a runbook step
# (design/hebe-demo/runbook-identity.md), not a flag: a new value needs the realm re-imported and every
# instance restarted, in that order.
set -euo pipefail

VAULT="${VAULT:-hartland}"
KEYS="hebe-client-secret hebe-console-oidc-client-secret"
HEX_CHARS=64

case "${1:-}" in
  "") ;;
  *) echo "usage: $0" >&2; exit 2 ;;
esac

TMP="$(umask 077; mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

say() { printf '==> %s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

command -v az >/dev/null 2>&1 || die "az CLI not found"
command -v openssl >/dev/null 2>&1 || die "openssl not found"
az account show >/dev/null 2>&1 || die "not logged in to Azure — run: az login"

for key in $KEYS; do
  if az keyvault secret show --vault-name "$VAULT" --name "$key" >/dev/null 2>&1; then
    # A value of the wrong shape would sync fine and fail at the first login or mint. Report it, but do not replace
    # it: something may already use it.
    LEN=$(az keyvault secret show --vault-name "$VAULT" --name "$key" --query value -o tsv | tr -d '\n' | wc -c | tr -d ' ')
    if [ "$LEN" -lt 32 ]; then
      die "'$key' is present but only $LEN characters long. Check what wrote it before replacing it (runbook-identity.md, rotation)."
    fi
    say "'$key' already present in vault '$VAULT' ($LEN chars) — left as it is"
    continue
  fi
  openssl rand -hex 32 | tr -d '\n' > "$TMP/$key"
  ACTUAL=$(wc -c < "$TMP/$key" | tr -d ' ')
  [ "$ACTUAL" = "$HEX_CHARS" ] || die "generated $ACTUAL characters for '$key', expected $HEX_CHARS"
  az keyvault secret set --vault-name "$VAULT" --name "$key" --file "$TMP/$key" --encoding utf-8 --output none
  az keyvault secret show --vault-name "$VAULT" --name "$key" --query value -o tsv | tr -d '\n' > "$TMP/$key.rt"
  cmp -s "$TMP/$key" "$TMP/$key.rt" || die "vault round-trip altered '$key'. Do not merge the realm PR on it."
  say "stored '$key' in vault '$VAULT' ($HEX_CHARS hex chars, round-trip verified)"
done

cat <<NEXT

==> done. The values are in the vault only; they were never printed.
    next: merge the realm PR (B-2.2), then seed the instance's offline token (B-3):
          scripts/seed-hebe-offline-token.sh marketa marketa
NEXT
