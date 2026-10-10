#!/usr/bin/env bash
# LR-P4 T1 — the extension is incremental: a later date adds exactly the weeks between, the weeks
# already extended stay byte-identical, and the same (or an earlier) date again is a no-op.
# Works on a throwaway copy of <db>:   test-incremental.sh <ctx> <db> [pod]
set -uo pipefail
CTX="${1:?usage: test-incremental.sh <ctx> <db> [pod]}"; SRC="${2:?db}"; POD="${3:-hartland-pg-1}"; NS="${EXTEND_NS:-data}"
source "$(dirname "$0")/lib-test.sh"
S="${SRC}_ext_inc_test"
FIRST=2026-03-31; SECOND=2026-06-30
week_of() { pgq "$S" "SELECT d_week_seq FROM date_dim WHERE d_date = DATE '$1'"; }

echo "== incremental, on a scratch copy of $SRC ($S)"
scratch_copy "$SRC" "$S"

run_extend "$S" "$FIRST"; rc=$?
expect "run 1 to $FIRST exits 0" "$rc" -eq 0
m1=$(pgq "$S" "SELECT count(*) FROM _extend_meta" 2>/dev/null)
w1=$(pgq "$S" "SELECT max(target_week_seq) FROM _extend_meta" 2>/dev/null)
expect "run 1 ends with the week of $FIRST" "$w1" = "$(week_of "$FIRST")"
expect "run 1: one _extend_meta row per target week, no gaps" "$m1" -eq \
  "$(pgq "$S" "SELECT max(target_week_seq) - min(target_week_seq) + 1 FROM _extend_meta" 2>/dev/null)"
fp1=$(fp_upto "$S" "$w1" 2>/dev/null)
n1=$(total_rows "$S")
expect "run 1 wrote rows" "$(echo "$fp1" | awk '{s += $3} END {print s + 0}')" -gt 0

run_extend "$S" "$SECOND"; rc=$?
expect "run 2 to $SECOND exits 0" "$rc" -eq 0
w2=$(week_of "$SECOND")
expect "run 2 adds exactly the weeks $((w1 + 1))..$w2" \
  "$(pgq "$S" "SELECT count(*) || ':' || min(target_week_seq) || '-' || max(target_week_seq) FROM _extend_meta WHERE target_week_seq > $w1" 2>/dev/null)" \
  = "$((w2 - w1)):$((w1 + 1))-$w2"
expect "run 2 leaves every row of weeks <= $w1 as run 1 wrote it" "$(fp_upto "$S" "$w1" 2>/dev/null)" = "$fp1"
n2=$(total_rows "$S")
expect "run 2 adds rows" "$n2" -gt "$n1"

run_extend "$S" "$SECOND"; rc=$?
expect "run 3 (same date) exits 0" "$rc" -eq 0
expect "run 3 adds no week" "$(pgq "$S" "SELECT count(*) FROM _extend_meta")" -eq $((m1 + w2 - w1))
expect "run 3 adds no row" "$(total_rows "$S")" -eq "$n2"

run_extend "$S" "$FIRST"; rc=$?
expect "run 4 (an earlier date) exits 0" "$rc" -eq 0
expect "run 4 adds no row" "$(total_rows "$S")" -eq "$n2"

drop_scratch "$S"
finish
