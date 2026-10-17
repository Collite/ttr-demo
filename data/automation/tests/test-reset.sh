#!/usr/bin/env bash
# AU-hartland P1·S1.1 T1 (S1.2 T6 extends the journal) — the reset undoes the build exactly: the extension's
# tables, views and internals are gone, the two added columns stay but are NULL, every base table is back to
# its original rows byte for byte (the inventory the build topped up comes back from _automation_undo), a
# second reset is a no-op, and a rebuild after the reset writes exactly what the first build wrote.
# Works on a throwaway copy of <db>:   test-reset.sh <ctx> <db> [pod]
set -uo pipefail
CTX="${1:?usage: test-reset.sh <ctx> <db> [pod]}"; SRC="${2:?db}"; POD="${3:-hartland-pg-1}"; NS="${EXTEND_NS:-data}"
source "$(dirname "$0")/lib-test.sh"
S="${SRC}_au_reset"

echo "== reset, on a scratch copy of $SRC ($S)"
scratch_copy "$SRC" "$S"
# The copy may already be built (a cluster world): reset it to its base first.
run_reset "$S"; expect "first reset exits 0" "$?" -eq 0
orig=$(fp_base "$S")

run_automation "$S"; rc=$?
expect "the build exits 0" "$rc" -eq 0
built=$(fp_build "$S")
expect "the build changed a base table (customer centers at least)" "$(fp_base "$S")" != "$orig"
expect "the build journaled the inventory it changed" "$(pgq "$S" "SELECT count(*) FROM _automation_undo WHERE tbl = 'inventory'")" -gt 0

run_reset "$S"; rc=$?
expect "reset exits 0" "$rc" -eq 0
expect "every base table is back to its original rows" "$(fp_base "$S")" = "$orig"
left=0; for r in $AU_TABLES $AU_VIEWS $AU_INTERNALS; do left=$((left + $(exists "$S" "$r"))); done
expect "no extension table, view or internal is left" "$left" -eq 0
expect "customer.c_center_sk kept, all NULL" "$(pgq "$S" "SELECT count(*) || ':' || count(c_center_sk) FROM customer" | cut -d: -f2)" -eq 0
expect "date_dim.d_working_day kept, all NULL" "$(pgq "$S" "SELECT count(d_working_day) FROM date_dim")" -eq 0
expect "fk_c_center dropped with the extension" "$(pgq "$S" "SELECT count(*) FROM pg_constraint WHERE conname = 'fk_c_center'")" -eq 0

run_reset "$S"; rc=$?
expect "a second reset exits 0" "$rc" -eq 0
expect "a second reset is a no-op" "$(fp_base "$S")" = "$orig"

run_automation "$S"; rc=$?
expect "the rebuild exits 0" "$rc" -eq 0
expect "reset + rebuild writes exactly what the first build wrote" "$(fp_build "$S")" = "$built"

drop_scratch "$S"
finish
