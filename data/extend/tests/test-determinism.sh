#!/usr/bin/env bash
# LR-P4 T1 — the extension is deterministic: two fresh copies, one prolonged in two steps and one
# in a single run, hold byte-identical extended rows and the same _extend_meta (bar applied_at).
#   test-determinism.sh <ctx> <db> [pod] [until]
set -uo pipefail
CTX="${1:?usage: test-determinism.sh <ctx> <db> [pod] [until]}"; SRC="${2:?db}"; POD="${3:-hartland-pg-1}"; NS="${EXTEND_NS:-data}"
UNTIL="${4:-2026-10-31}"
source "$(dirname "$0")/lib-test.sh"
A="${SRC}_ext_det_a"; B="${SRC}_ext_det_b"

echo "== determinism, on two scratch copies of $SRC (to $UNTIL)"
scratch_copy "$SRC" "$A"; scratch_copy "$SRC" "$B"
run_extend "$A" 2026-03-31; rc1=$?
run_extend "$A" "$UNTIL";    rc2=$?
run_extend "$B" "$UNTIL";    rc3=$?
expect "copy A, step 1 exits 0" "$rc1" -eq 0
expect "copy A, step 2 exits 0" "$rc2" -eq 0
expect "copy B, one step exits 0" "$rc3" -eq 0

w=$(pgq "$A" "SELECT max(target_week_seq) FROM _extend_meta" 2>/dev/null)
fa=$(fp_upto "$A" "${w:-0}" 2>/dev/null); fb=$(fp_upto "$B" "${w:-0}" 2>/dev/null)
for f in $ALL_FACTS; do
  expect "$f: identical extended rows (md5, rows)" "$(echo "$fb" | awk -v f="$f" '$1 == f {print $2, $3}')" = \
    "$(echo "$fa" | awk -v f="$f" '$1 == f {print $2, $3}')"
done
expect "some rows were extended" "$(echo "$fa" | awk '{s += $3} END {print s + 0}')" -gt 0
meta="SELECT md5(string_agg(target_week_seq || ':' || template_week_seq || ':' || k || ':' || rows::text, ',' ORDER BY target_week_seq)) FROM _extend_meta"
expect "identical _extend_meta (weeks, templates, cycles, per-table counts)" "$(pgq "$B" "$meta" 2>/dev/null)" = "$(pgq "$A" "$meta" 2>/dev/null)"

drop_scratch "$A"; drop_scratch "$B"
finish
