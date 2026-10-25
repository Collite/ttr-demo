#!/usr/bin/env bash
# Verify hebe's provisioning end to end on hartland, AFTER the olymp PR has merged to master
# and ArgoCD has synced. Read-only: it mutates nothing. Prints a pass/fail line per link in the
# chain so a failure names the hop, not just "hebe is red".
#
#   ./verify-hebe-provisioning.sh                 # instance marketa (HE-P1)
#   INSTANCE=dev ./verify-hebe-provisioning.sh    # another instance: Secret hebe-<id>, schema hebe_<id>
#
# Steps 3 and 6 exec into a pod (psql, curl): run by an operator, not by Claude (pod exec is denied to it).
set -uo pipefail

CONTEXT="${CONTEXT:-hartland}"
INSTANCE="${INSTANCE:-marketa}"
BOUND_USER="${BOUND_USER:-$INSTANCE}"     # [security] bound_user: the user the OBO token must be for
SECRET="hebe-$INSTANCE"
SCHEMA="hebe_$INSTANCE"
EMBED_MODEL="${EMBED_MODEL:-text-embedding-3-small}"   # [llm] embedding_model in clusters/<c>/apps/hebe/values.yaml (olymp#152)
FAILED=0

ok()   { printf '  \033[32mPASS\033[0m  %s\n' "$*"; }
bad()  { printf '  \033[31mFAIL\033[0m  %s\n' "$*"; FAILED=1; }
head_() { printf '\n== %s\n' "$*"; }
k() { kubectl --context "$CONTEXT" "$@"; }

head_ "1. ArgoCD apps"
for app in auth data hebe; do
  line=$(k -n argocd get application "$app" -o jsonpath='{.status.sync.status}/{.status.health.status}' 2>/dev/null)
  [ "$line" = "Synced/Healthy" ] && ok "app $app — $line" || bad "app $app — ${line:-<not found>}"
done

head_ "2. ExternalSecret $SECRET -> Secret"
es=$(k -n kantheon get externalsecret "$SECRET" -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null)
[ "$es" = "True" ] && ok "ExternalSecret $SECRET Ready" \
  || bad "ExternalSecret $SECRET not Ready (${es:-missing}) — check the ESO log; a bad template
        function or a missing vault key shows up here first"

# Key names only — values are never read or printed by this script. The seven the instance runs on
# (olymp clusters/hartland/platform/auth/clusterexternalsecret-hebe-marketa.yaml).
names=$(k -n kantheon get secret "$SECRET" -o go-template='{{range $k,$v := .data}}{{$k}} {{end}}' 2>/dev/null)
for want in pg llm-gateway-key receipts.signing_key keycloak-client-id keycloak-client-secret keycloak-offline-token telegram; do
  case " $names " in *" $want "*) ok "secret key present: $want" ;; *) bad "secret key MISSING: $want" ;; esac
done

# The one field whose LENGTH is load-bearing. Length only; never the value.
seedlen=$(k -n kantheon get secret "$SECRET" -o jsonpath='{.data.receipts\.signing_key}' 2>/dev/null | base64 -d | wc -c | tr -d ' ')
[ "$seedlen" = "32" ] && ok "receipts.signing_key is 32 bytes" \
  || bad "receipts.signing_key is ${seedlen:-0} bytes, must be 32 (hebe: 'Ed25519 seed must be 32 bytes')"

head_ "3. pgvector in the hebe database"
PRIMARY=$(k -n data get pods -l cnpg.io/cluster=postgres \
  -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.metadata.labels.cnpg\.io/instanceRole}{"\n"}{end}' \
  | awk '/primary/{print $1; exit}')
if [ -z "$PRIMARY" ]; then
  bad "no CNPG primary found"
else
  ext=$(k -n data exec -i "$PRIMARY" -c postgres -- psql -U postgres -d hebe -tAc \
        "SELECT extversion FROM pg_extension WHERE extname='vector'" 2>/dev/null | tr -d ' \n')
  [ -n "$ext" ] && ok "extension vector $ext installed in db hebe" \
    || bad "extension vector NOT installed in db hebe — Flyway V2 will fail on vector(1536)"
  tables=$(k -n data exec -i "$PRIMARY" -c postgres -- psql -U postgres -d hebe -tAc \
        "SELECT count(*) FROM information_schema.tables WHERE table_schema='$SCHEMA'" 2>/dev/null | tr -d ' \n')
  [ "${tables:-0}" -gt 0 ] 2>/dev/null && ok "schema $SCHEMA has $tables tables" \
    || bad "schema $SCHEMA has no tables — Flyway has not migrated this instance (or the schema is missing)"
  dbstate=$(k -n data get database hebe -o jsonpath='{.status.applied}' 2>/dev/null)
  [ "$dbstate" = "true" ] && ok "CNPG Database hebe applied" \
    || bad "CNPG Database hebe not applied: $(k -n data get database hebe -o jsonpath='{.status.message}' 2>/dev/null)"
fi

head_ "4. hebe pod"
phase=$(k -n kantheon get pods -l app.kubernetes.io/name=hebe -o jsonpath='{.items[0].status.phase}' 2>/dev/null)
ready=$(k -n kantheon get pods -l app.kubernetes.io/name=hebe -o jsonpath='{.items[0].status.containerStatuses[0].ready}' 2>/dev/null)
[ "$phase" = "Running" ] && [ "$ready" = "true" ] && ok "pod Running and Ready" \
  || bad "pod phase=${phase:-none} ready=${ready:-none}"

# The two boot failures this whole change exists to prevent — surfaced by name, not by
# "read the logs yourself".
logs=$(k -n kantheon logs -l app.kubernetes.io/name=hebe --tail=200 2>/dev/null)
case "$logs" in
  *"Ed25519 seed must be 32 bytes"*) bad "boot log: bad receipts seed length" ;;
  *'type "vector" does not exist'*)  bad "boot log: pgvector missing at Flyway V2" ;;
  *"requires the 'pg' secret"*)      bad "boot log: pg secret absent or blank" ;;
  *'ERROR: relation "'*)             bad "log: a query found no hebe table — the connection lost $SCHEMA from its
        search_path (hebe < 0.11.5: a rolled-back first transaction undid the SET; kantheon#240)" ;;
  *) ok "no known boot-blocker in the last 200 log lines" ;;
esac
printf '%s\n' "$logs" | grep -qi "Successfully applied\|migrat" && ok "Flyway ran" || true

head_ "5. /ready (through the API server's pod proxy; no exec) and the OBO identity"
# The pod proxy answers for a pod that is not Ready, where the service proxy has no endpoint to send to.
pod=$(k -n kantheon get pods -l app.kubernetes.io/name=hebe --sort-by=.metadata.creationTimestamp \
  -o jsonpath='{.items[-1:].metadata.name}' 2>/dev/null)
readyjson=$(k get --raw "/api/v1/namespaces/kantheon/pods/${pod:-none}:8765/proxy/ready" 2>&1)
readyfield() { printf '%s' "$readyjson" | python3 -I -c 'import json, sys
s = sys.stdin.read(); i = s.find("{")
try:
    d = json.loads(s[i:]) if i >= 0 else {}
except ValueError:
    d = {}
'"$1" 2>/dev/null; }
readyline=$(readyfield 'names = [c.get("name") for c in d.get("checks", [])]
print(("ok " if d.get("ok") else "failing ") + ", ".join(d.get("failing") or names))')
case "$readyline" in
  "ok "*)      ok "/ready ok: ${readyline#ok }" ;;
  "failing "*) bad "/ready failing: ${readyline#failing }" ;;
  *)           bad "/ready unreadable: ${readyjson:0:160}" ;;
esac
# contracts §9: the OBO token is for the bound user (the identity check's detail carries sub/preferred_username/azp)
identity=$(readyfield 'print(next((c.get("detail", "") for c in d.get("checks", []) if c.get("name") == "identity"), ""))')
case "$identity" in
  *"preferred_username=$BOUND_USER "*) ok "OBO token is for $BOUND_USER (${identity%% preferred_username*})" ;;
  "") bad "/ready has no identity check (platform axis off, or /ready unreadable)" ;;
  *)  bad "OBO identity is not $BOUND_USER: ${identity:0:160}" ;;
esac

head_ "6. gateway key accepted, embeddings served (hebe's own key, from its mounted Secret)"
if [ "$ready" = "true" ]; then
  code=$(k -n kantheon exec deploy/hebe -- sh -c \
    'curl -sS -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $(cat $HEBE_SECRETS_DIR/llm-gateway-key)" http://llm-gateway.ttr-server:7280/v1/models' 2>/dev/null)
  case "$code" in
    200) ok "llm-gateway accepted hebe's ttrk- key (200)" ;;
    401) bad "llm-gateway rejected the key (401) — vault value and seeded virtual_keys hash disagree" ;;
    *)   bad "unexpected gateway response: ${code:-<no curl in image?>}" ;;
  esac
  # memory_write embeds every document; an embeddings row with no Azure deployment behind it answers 400 and the
  # write fails (hartland 2026-10-24: "The API deployment for this resource does not exist").
  emb=$(k -n kantheon exec deploy/hebe -- sh -c \
    "curl -sS -o /tmp/emb -w '%{http_code}' -H \"Authorization: Bearer \$(cat \$HEBE_SECRETS_DIR/llm-gateway-key)\" \
      -H 'Content-Type: application/json' -d '{\"model\":\"$EMBED_MODEL\",\"input\":[\"ping\"]}' \
      http://llm-gateway.ttr-server:7280/v1/embeddings; echo; head -c 200 /tmp/emb" 2>/dev/null)
  case "${emb%%$'\n'*}" in
    200) ok "embeddings ($EMBED_MODEL) served (200)" ;;
    *)   bad "embeddings ($EMBED_MODEL) answered ${emb%%$'\n'*}: $(printf '%s' "${emb#*$'\n'}" | tr -s ' \n' ' ' | head -c 160)" ;;
  esac
else
  printf '  SKIP  gateway check (pod not Ready)\n'
fi

head_ "7. the registry entry (contracts §9)"
entry=$(k get --raw "/api/v1/namespaces/kantheon/services/capabilities-mcp:7501/proxy/v1/capabilities/hebe-$INSTANCE" 2>&1 \
  | python3 -I -c 'import json, sys
s = sys.stdin.read(); i = s.find("{"); j = s.rfind("}")
try:
    d = json.loads(s[i:j + 1]) if 0 <= i < j else {}
except ValueError:
    d = {}
a = (d.get("capability") or {}).get("agent") or {}
print("registered non_routable" if a.get("nonRoutable") else ("registered ROUTABLE" if a else ""))' 2>/dev/null)
case "$entry" in
  "registered non_routable") ok "hebe-$INSTANCE registered in capabilities-mcp, non_routable" ;;
  "registered ROUTABLE")     bad "hebe-$INSTANCE registered but NOT non_routable — the cascade could delegate to it" ;;
  *)                         bad "hebe-$INSTANCE is not registered in capabilities-mcp" ;;
esac

printf '\n'
[ "$FAILED" = 0 ] && { printf 'ALL GREEN — hebe is provisioned.\n'; exit 0; }
printf 'One or more checks FAILED (see above).\n'; exit 1
