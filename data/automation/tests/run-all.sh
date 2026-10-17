#!/usr/bin/env bash
# The data/automation suite.
#
#   tests/run-all.sh                     a throwaway local Postgres (pg-local.sh, no Docker) loaded with fixture.sql
#                                        into `au_fixture` — what CI and a laptop run
#   tests/run-all.sh <ctx> <db> [pod]    against <db> on that server instead (scratch copies only, never the world)
#
# Every test works on its own scratch copy (CREATE DATABASE … TEMPLATE) and drops it (KEEP_SCRATCH=1 keeps them).
# ONLY=<pattern> runs the matching tests (ONLY=reset → test-reset.sh). Exits 1 if any test failed.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"

if [ $# -eq 0 ]; then
  # shellcheck source=pg-local.sh
  source "$HERE/pg-local.sh"
  pg_local_start || exit 1
  trap pg_local_stop EXIT
  createdb au_fixture && psql -X -q -d au_fixture -f "$HERE/fixture.sql" || { echo "fixture load failed" >&2; exit 1; }
  CTX=local; SRC=au_fixture; POD=-
else
  CTX="$1"; SRC="${2:?usage: run-all.sh [<ctx> <db> [pod]]}"; POD="${3:-hartland-pg-1}"
fi
export CTX

rc=0; ran=0
for t in "$HERE"/test-*.sh; do
  case "$(basename "$t")" in *"${ONLY:-}"*) ;; *) continue ;; esac
  bash "$t" "$CTX" "$SRC" "$POD" || rc=1
  ran=$((ran + 1))
done
echo "== run-all: $ran test scripts, $([ "$rc" -eq 0 ] && echo 'all green' || echo 'FAILURES above')"
exit $rc
