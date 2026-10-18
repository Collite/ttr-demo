#!/usr/bin/env bash
# AU-hartland P1·S1.1 T1 — the build is guarded: a second run at the same as_of changes no row and says
# "already built"; a run at another as_of is refused ("reset first") and changes nothing either.
# Works on a throwaway copy of <db>:   test-idempotent.sh <ctx> <db> [pod]
set -uo pipefail
CTX="${1:?usage: test-idempotent.sh <ctx> <db> [pod]}"; SRC="${2:?db}"; POD="${3:-hartland-pg-1}"; NS="${EXTEND_NS:-data}"
source "$(dirname "$0")/lib-test.sh"
S="${SRC}_au_idem"

echo "== idempotency, on a scratch copy of $SRC ($S)"
scratch_copy "$SRC" "$S"
run_automation "$S"; rc=$?
expect "run 1 builds (exit 0)" "$rc" -eq 0
as_of=$(as_of_of "$S")
expect "run 1 recorded its as_of" "$as_of" != ""
first=$(fp_build "$S"); base=$(fp_base "$S")

run_automation "$S"; rc=$?
expect "run 2 (default as_of = the same day) exits 0" "$rc" -eq 0
expect "run 2 says it was already built" "$(grep -c 'already built' "$(log_of build "$S")")" -ge 1
expect "run 2 changes no row" "$(fp_build "$S")" = "$first"

run_automation "$S" "$as_of"; rc=$?
expect "run 3 (as_of named explicitly, the same day) exits 0" "$rc" -eq 0
expect "run 3 changes no row" "$(fp_build "$S")" = "$first"

other=$(pgq "$S" "SELECT (DATE '$as_of' - 7)::text")
run_automation "$S" "$other"; rc=$?
expect "run 4 at another as_of ($other) is refused" "$rc" -ne 0
expect "run 4 says reset first" "$(grep -c 'reset first' "$(log_of build "$S")")" -ge 1
expect "run 4 changes no row" "$(fp_build "$S")" = "$first"
expect "no base row moved either" "$(fp_base "$S")" = "$base"

drop_scratch "$S"
finish
