#!/usr/bin/env bash
# HE-P1 · S1.3 T5 (HE contracts §9) — install Hebe's routine fixtures (data/hebe/routines/*.json) on an instance,
# idempotently by name: an installed routine is updated in place (same id, same Iris session), never duplicated.
#
#   data/hebe/install-routines.sh                       # over a port-forward to svc/hebe (Hebe admits it as `local`)
#   data/hebe/install-routines.sh --edge                # through the public console, signed in as marketa
#                                                       #   (persona password in $HEBE_VERIFY_PASSWORD, never argv)
#   data/hebe/install-routines.sh --fire monday-brief   # install, then fire one (pre-show, ops manual §7.3 step 3)
#
# The same calls as `hebe routines install|fire` (POST /api/routines …), without the hebe binary on this machine.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
CONTEXT="${CONTEXT:-hartland}"
NS="${NS:-kantheon}"
HOST="${HOST:-hebe.hartland.collite.cz}"
LOCAL_PORT="${LOCAL_PORT:-18765}"
EDGE=0
FIRE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --edge) EDGE=1 ;;
    --fire) FIRE="${2:?--fire needs a routine name}"; shift ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done

api() { python3 -I "$HERE/routines_api.py" "$@"; }

if [ "$EDGE" = 1 ]; then
  WHERE=(--edge "$HOST")
else
  kubectl --context "$CONTEXT" -n "$NS" port-forward svc/hebe "$LOCAL_PORT:8765" >/dev/null 2>&1 &
  PF=$!
  trap 'kill "$PF" 2>/dev/null || true' EXIT
  for _ in $(seq 1 30); do
    curl -fsS -o /dev/null "http://127.0.0.1:$LOCAL_PORT/healthz" 2>/dev/null && break
    sleep 0.5
  done
  WHERE=(--url "http://127.0.0.1:$LOCAL_PORT")
fi

api "${WHERE[@]}" install "$HERE"/routines/*.json
[ -z "$FIRE" ] || api "${WHERE[@]}" fire "$FIRE"
api "${WHERE[@]}" list
