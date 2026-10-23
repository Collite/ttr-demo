#!/usr/bin/env bash
# HB-P1 T1 / HE-P1 · S1.2 T1 — Markéta's Hebe on hartland, one check per target row
# (project/kantheon/features/hebe/tasks/tasks-p1-s1.2-instance-console-telegram.md; HB contracts §2 as amended by HE-D-4).
#
#   design/hebe-demo/rig-hb/verify.sh                 # every check; PASS / FAIL / SKIP / MANUAL per line
#   HEBE_VERIFY_PASSWORD=… verify.sh                  # + the console sign-in checks (the personas' demo password)
#   HEBE_VERIFY_TELEGRAM=ok HEBE_VERIFY_STRANGER=dropped verify.sh   # + the two phone checks, once seen
#
# Exit: 0 every check PASS · 1 any FAIL · 3 no FAIL, but a check is SKIP or MANUAL (T8 needs 0, twice, the second run
# after `kubectl --context hartland -n kantheon rollout restart deploy/hebe`).
#
# Reads only. kubectl only GETs (`get`, and `get --raw` through the API server's service proxy, because port-forward and
# exec are not used here). The sign-in checks drive the real browser flow through the public edge as marketa and maya
# (edge_login.py); they write nothing. The durability check keeps one small state file ($HEBE_VERIFY_STATE) so a run
# after a restart can see that the receipt chain survived.
set -uo pipefail

CONTEXT="${CONTEXT:-hartland}"
NS="${NS:-kantheon}"
SVC="${SVC:-hebe}"
PORT="${PORT:-8765}"
INSTANCE="${INSTANCE:-marketa}"
BOUND_USER="${BOUND_USER:-marketa}"
OTHER_USER="${OTHER_USER:-maya}"           # a hartland user who is NOT in console_users
HOST="${HOST:-hebe.hartland.collite.cz}"
IMAGE_REPO="${IMAGE_REPO:-ghcr.io/collite/hebe}"
REGISTRY="${REGISTRY:-capabilities-mcp:7501}"
STATE="${HEBE_VERIFY_STATE:-${HOME}/.config/hebe-verify/${INSTANCE}.json}"
HERE="$(cd "$(dirname "$0")" && pwd)"

PASS=0 FAIL=0 OPEN=0
pass()   { PASS=$((PASS + 1)); printf 'PASS    %-24s %s\n' "$1" "$2"; }
fail()   { FAIL=$((FAIL + 1)); printf 'FAIL    %-24s %s\n' "$1" "$2"; }
skip()   { OPEN=$((OPEN + 1)); printf 'SKIP    %-24s %s\n' "$1" "$2"; }
manual() { OPEN=$((OPEN + 1)); printf 'MANUAL  %-24s %s\n' "$1" "$2"; }

kc() { kubectl --context "$CONTEXT" "$@"; }
# GET through the API server's service proxy. Prints the body even on a non-2xx answer (kubectl then exits non-zero
# and puts the body in its error line, so take the JSON from wherever it is).
proxy_get() { kc get --raw "/api/v1/namespaces/$NS/services/$1/proxy$2" 2>&1 | sed -n 's/^[^{]*\({.*}\)[^}]*$/\1/p' | head -1; }
# One field of a JSON document on stdin, by a Python expression over `d` ("" when it fails).
jq_py() { python3 -I -c "import json,sys
try:
    d = json.load(sys.stdin); v = $1
    print('' if v is None else (json.dumps(v) if isinstance(v, (dict, list)) else v))
except Exception:
    print('')"; }

# ── 1. the pod ──────────────────────────────────────────────────────────────────────────────────────────────────
check_pod() {
  local deploy ready want image
  deploy="$(kc -n "$NS" get deploy "$SVC" -o json 2>/dev/null)" || { fail pod "no deployment $NS/$SVC on context $CONTEXT"; return; }
  ready="$(jq_py "d['status'].get('readyReplicas', 0)" <<<"$deploy")"
  want="$(jq_py "d['spec']['replicas']" <<<"$deploy")"
  image="$(jq_py "d['spec']['template']['spec']['containers'][0]['image']" <<<"$deploy")"
  [ "${ready:-0}" = "$want" ] && [ "$want" != 0 ] || { fail pod "ready ${ready:-0}/$want ($image)"; return; }
  case "$image" in "$IMAGE_REPO":*) pass pod "ready $ready/$want, $image" ;; *) fail pod "ready, but on $image (want $IMAGE_REPO:<tag>)" ;; esac
}

# ── 2. /ready and what it says (the doctor's checks, readable without exec) ───────────────────────────────────────
READY_JSON=""
check_ready() {
  READY_JSON="$(proxy_get "$SVC:$PORT" /ready)"
  [ -n "$READY_JSON" ] || { fail ready "no JSON from /ready through the service proxy"; return; }
  if [ "$(jq_py "d['ok']" <<<"$READY_JSON")" = True ]; then
    pass ready "200: $(jq_py "', '.join(c['name'] for c in d['checks'])" <<<"$READY_JSON")"
  else
    fail ready "503, failing: $(jq_py "', '.join(c['name'] + ' (' + c['detail'][:80] + ')' for c in d['checks'] if not c['ok'])" <<<"$READY_JSON")"
  fi
}

ready_check() { jq_py "next((c for c in d['checks'] if c['name'] == '$1'), {}).get('$2')" <<<"$READY_JSON"; }

check_identity() {
  local ok detail
  ok="$(ready_check identity ok)"; detail="$(ready_check identity detail)"
  [ -n "$detail" ] || { fail obo-identity "/ready has no identity check (is the platform axis on?)"; return; }
  if [ "$ok" = True ] && [[ "$detail" == *"preferred_username=$BOUND_USER azp=hebe"* ]]; then
    pass obo-identity "$detail"
  else
    fail obo-identity "$detail"
  fi
}

check_receipts_key() {
  local ok detail
  ok="$(ready_check receipts ok)"; detail="$(ready_check receipts detail)"
  [ "$ok" = True ] && pass receipts-key "${detail:-provisioned}" || fail receipts-key "${detail:-no receipts check in /ready}"
}

# ── 3. the registry: registered, heartbeating, and NOT a routing candidate ────────────────────────────────────────
check_registry() {
  local one routing nonroutable
  one="$(proxy_get "${REGISTRY}" "/v1/capabilities/hebe-${INSTANCE}")"
  nonroutable="$(jq_py "(d.get('capability') or {}).get('agent', {}).get('nonRoutable')" <<<"$one")"
  [ -n "$(jq_py "d.get('capability')" <<<"$one")" ] || { fail registry "hebe-$INSTANCE is not registered in capabilities-mcp"; return; }
  [ "$nonroutable" = True ] || { fail registry "hebe-$INSTANCE is registered but not non_routable ($nonroutable)"; return; }
  routing="$(proxy_get "${REGISTRY}" /v1/capabilities/agents)"
  if [ "$(jq_py "any(a.get('agentId') == 'hebe-$INSTANCE' for a in d['agents'])" <<<"$routing")" = False ]; then
    pass registry "hebe-$INSTANCE registered, non_routable, absent from the routing view"
  else
    fail registry "hebe-$INSTANCE appears in the routing view (/v1/capabilities/agents)"
  fi
}

# ── 4. the console through the edge ───────────────────────────────────────────────────────────────────────────────
check_console_redirect() {
  local out code location
  out="$(curl -sS -o /dev/null -w '%{http_code} %{redirect_url}' "https://$HOST/" 2>&1)"
  code="${out%% *}"; location="${out#* }"
  if [ "$code" = 302 ] && [[ "$location" == https://keycloak.*"/protocol/openid-connect/auth?"*"client_id=hebe-console"* ]]; then
    pass console-redirect "302 → Keycloak, client hebe-console"
  else
    fail console-redirect "GET https://$HOST/ → $code ${location:0:100}"
  fi
}

# Sets LOGIN_JSON (edge_login.py's line) and LOGIN_STATUS (the console's HTTP status, 0 when the flow broke first). Call
# it plainly, not in $(…): a subshell would lose both.
LOGIN_JSON="" LOGIN_STATUS=""
sign_in() {
  LOGIN_JSON="$(python3 -I "$HERE/edge_login.py" "$HOST" "$@")"
  LOGIN_STATUS="$(jq_py "d.get('status')" <<<"$LOGIN_JSON")"
}
why() { jq_py "d.get('error') or d.get('body')" <<<"$LOGIN_JSON" | head -c 160; }

check_console_logins() {
  if [ -z "${HEBE_VERIFY_PASSWORD:-}" ]; then
    for c in console-$BOUND_USER console-$OTHER_USER console-forged; do skip "$c" "set HEBE_VERIFY_PASSWORD (the personas' demo password)"; done
    return
  fi
  export HEBE_VERIFY_PASSWORD
  sign_in "$BOUND_USER"
  [ "$LOGIN_STATUS" = 200 ] && pass "console-$BOUND_USER" "signed in through the edge, /api/status 200" \
    || fail "console-$BOUND_USER" "status ${LOGIN_STATUS:-?}: $(why)"
  sign_in "$OTHER_USER"
  [ "$LOGIN_STATUS" = 403 ] && pass "console-$OTHER_USER" "a hartland user outside console_users: 403 at Hebe" \
    || fail "console-$OTHER_USER" "status ${LOGIN_STATUS:-?} (want 403): $(why)"
  sign_in "$OTHER_USER" --forge-identity "$BOUND_USER"
  case "$LOGIN_STATUS" in
    403) pass console-forged "$OTHER_USER sending x-forwarded-user: $BOUND_USER is still $OTHER_USER (403)" ;;
    200) fail console-forged "200: the edge let a client's identity header through — $OTHER_USER was admitted as $BOUND_USER" ;;
    *) fail console-forged "status ${LOGIN_STATUS:-?} (want 403): $(why)" ;;
  esac
}

# ── 5. durability: the receipt chain verifies, and survives a restart ─────────────────────────────────────────────
check_durability() {
  if [ -z "${HEBE_VERIFY_PASSWORD:-}" ]; then skip receipts-chain "needs the console sign-in (HEBE_VERIFY_PASSWORD)"; return; fi
  local records saved
  sign_in "$BOUND_USER" --path /api/receipts/verify
  [ "$LOGIN_STATUS" = 200 ] || { fail receipts-chain "GET /api/receipts/verify → ${LOGIN_STATUS:-?}: $(why)"; return; }
  local body; body="$(jq_py "d.get('body')" <<<"$LOGIN_JSON")"
  [ "$(jq_py "d.get('ok')" <<<"$body")" = True ] || { fail receipts-chain "verify failed: ${body:0:160}"; return; }
  records="$(jq_py "d.get('records')" <<<"$body")"
  saved="$(jq_py "d.get('records')" <"$STATE" 2>/dev/null || true)"
  if [ -n "$saved" ] && [ "${records:-0}" -lt "$saved" ]; then
    fail receipts-chain "the chain shrank: $records records now, $saved at the last run (state lost on restart?)"
    return
  fi
  mkdir -p "$(dirname "$STATE")" && printf '{"records": %s}\n' "${records:-0}" >"$STATE"
  pass receipts-chain "verifies, $records records${saved:+ (was $saved at the last run)}"
}

# ── 6. the phone (manual, HB-⚑3 / B-4) ────────────────────────────────────────────────────────────────────────────
check_phone() {
  case "${HEBE_VERIFY_TELEGRAM:-}" in
    ok) pass telegram "round trip confirmed by the operator" ;;
    "") manual telegram "message the bot from the presenter's phone; Hebe answers; then HEBE_VERIFY_TELEGRAM=ok" ;;
    *) fail telegram "the operator reported: $HEBE_VERIFY_TELEGRAM" ;;
  esac
  case "${HEBE_VERIFY_STRANGER:-}" in
    dropped|refused) pass unmapped-chat "a second account's message was $HEBE_VERIFY_STRANGER (record which in probes.md for Beat 6)" ;;
    "") manual unmapped-chat "message the bot from a second account; nothing reaches Hebe; then HEBE_VERIFY_STRANGER=dropped|refused" ;;
    *) fail unmapped-chat "the operator reported: $HEBE_VERIFY_STRANGER" ;;
  esac
}

command -v kubectl >/dev/null 2>&1 || { echo "kubectl not found" >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "python3 not found" >&2; exit 1; }
echo "Hebe instance $INSTANCE on $CONTEXT ($NS/$SVC, https://$HOST)"
check_pod
check_ready
check_identity
check_receipts_key
check_registry
check_console_redirect
check_console_logins
check_durability
check_phone
echo "$PASS pass · $FAIL fail · $OPEN open"
[ "$FAIL" -gt 0 ] && exit 1
[ "$OPEN" -gt 0 ] && exit 3
exit 0
