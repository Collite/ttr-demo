#!/usr/bin/env bash
# LR (2026-10-11, ruling 11) — the reset undoes the extension exactly, and a re-extension after it
# equals a fresh one. Works on a throwaway copy of <db>:   test-reset.sh <ctx> <db> [pod]
set -uo pipefail
CTX="${1:?usage: test-reset.sh <ctx> <db> [pod]}"; SRC="${2:?db}"; POD="${3:-hartland-pg-1}"; NS="${EXTEND_NS:-data}"
source "$(dirname "$0")/lib-test.sh"
S="${SRC}_ext_reset_test"
UNTIL=2026-03-31

# fp_all <db> — md5 + rows over every row of each fact (originals and copies alike)
fp_all() {
  local f sql=""
  for f in $ALL_FACTS; do
    sql+="SELECT '$f' f, md5(coalesce(string_agg(t::text, '|' ORDER BY t::text), '')) h, count(*) n FROM $f t UNION ALL "
  done
  pgq "$1" "SELECT f || ' ' || h || ' ' || n FROM (${sql% UNION ALL }) z ORDER BY f"
}
reset() { "$EXTEND_DIR/run-reset.sh" "$CTX" "$1" "$POD" > "${TMPDIR:-/tmp}/reset-$1.log" 2>&1; }

echo "== reset, on a scratch copy of $SRC ($S)"
scratch_copy "$SRC" "$S"
# The copy may already be extended (the shared worlds are): reset it to its originals first.
reset "$S"; expect "first reset exits 0" "$?" -eq 0
orig=$(fp_all "$S")

run_extend "$S" "$UNTIL"; rc=$?
expect "extend to $UNTIL exits 0" "$rc" -eq 0
expect "it wrote rows" "$(pgq "$S" "SELECT count(*) FROM _extend_meta")" -gt 0

reset "$S"; rc=$?
expect "reset exits 0" "$rc" -eq 0
expect "every fact is back to its originals, byte for byte" "$(fp_all "$S")" = "$orig"
expect "_extend_meta is empty" "$(pgq "$S" "SELECT count(*) FROM _extend_meta")" -eq 0
expect "the base ends are kept" "$(pgq "$S" "SELECT count(*) FROM _extend_base")" -eq 4

reset "$S"; expect "a second reset is a no-op" "$(fp_all "$S")" = "$orig"

run_extend "$S" "$UNTIL"
again=$(fp_all "$S")
reset "$S"; run_extend "$S" "$UNTIL"
expect "reset + re-extend writes exactly what the first extension wrote" "$(fp_all "$S")" = "$again"

drop_scratch "$S"
finish
