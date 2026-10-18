#!/usr/bin/env bash
# AU-hartland P1 — undo the automation extension of a world (reset.sql, README.md "Reset"): every base row the
# build changed is restored from its journal, the extension's tables, views and internals are dropped, and the
# two added columns are kept but emptied. Then run-automation.sh builds it again — the way to move a world to
# another demo day, or to apply a changed automation.conf.
#
# ONE transaction, as the postgres superuser over the pod-local socket (the run-automation.sh path). A world
# that was never built resets to itself (a no-op).
#
# Usage: ./run-reset.sh <kube-context> <database> [pod]
#        `just automation-reset <us|cz> [ctx]` wraps it with the world's database and the pod.
# Refuses `tpc-ds-1g`, which is never built.
set -euo pipefail
CTX="${1:?usage: run-reset.sh <kube-context> <database> [pod]}"; DB="${2:?database}"; POD="${3:-hartland-pg-1}"
NS="${EXTEND_NS:-data}"
DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib.sh
source "$DIR/lib.sh"

if [ "$DB" = "tpc-ds-1g" ]; then
  echo "refusing to touch tpc-ds-1g — it is never built" >&2; exit 2
fi

was=""
if [ "$(pgq "$DB" "SELECT to_regclass('public._automation_meta') IS NOT NULL")" = t ]; then
  was=$(pgq "$DB" "SELECT as_of FROM _automation_meta WHERE step = 'build'")
fi
echo "== resetting the automation extension of $DB on $CTX ($([ -n "$was" ] && echo "built as of $was" || echo "not built"); single transaction) =="
t0=$(date +%s)
pg "$DB" -q -1 -f - < "$DIR/reset.sql"
t1=$(date +%s)
echo "Done in $((t1 - t0)) s (transaction). Build again with run-automation.sh / just automation-data."
