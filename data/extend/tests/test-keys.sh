#!/usr/bin/env bash
# LR-P4 T1 — keys on an EXTENDED database: unique in every fact, extended order numbers >= 1e9
# (originals below), every extended return has its extended sale, date_dim covers 2026–2030.
#   test-keys.sh <ctx> <db> [pod]
set -uo pipefail
CTX="${1:?usage: test-keys.sh <ctx> <db> [pod]}"; DB="${2:?db}"; POD="${3:-hartland-pg-1}"; NS="${EXTEND_NS:-data}"
source "$(dirname "$0")/lib-test.sh"
OFF=1000000000

echo "== keys on $DB"
expect "the database was extended (_extend_meta has weeks)" "$(pgq "$DB" "SELECT count(*) FROM _extend_meta" 2>/dev/null)" -gt 0
expect "date_dim holds every day of 2026–2030" "$(pgq "$DB" "SELECT count(*) FROM date_dim WHERE d_year BETWEEN 2026 AND 2030")" -eq 1826

for spec in $SALES; do IFS=: read -r t d o i <<<"$spec"
  expect "$t: (item, $o) unique" "$(pgq "$DB" "SELECT count(*) FROM (SELECT 1 FROM $t GROUP BY $i, $o HAVING count(*) > 1) z")" -eq 0
  expect "$t: extended rows have $o >= 1e9" \
    "$(pgq "$DB" "SELECT count(*) FROM ($(extended_rows_sql "$t")) x WHERE x.$o < $OFF" 2>/dev/null)" -eq 0
  expect "$t: original rows have $o < 1e9" \
    "$(pgq "$DB" "SELECT count(*) FROM $t WHERE $d <= $(base_sk "$t") AND $o >= $OFF" 2>/dev/null)" -eq 0
  expect "$t: has extended rows" "$(pgq "$DB" "SELECT count(*) FROM ($(extended_rows_sql "$t")) x" 2>/dev/null)" -gt 0
done
for spec in $RETURNS; do IFS=: read -r t d o i st so si sd <<<"$spec"
  expect "$t: (item, $o) unique" "$(pgq "$DB" "SELECT count(*) FROM (SELECT 1 FROM $t GROUP BY $i, $o HAVING count(*) > 1) z")" -eq 0
  expect "$t: every return with $o >= 1e9 has its extended sale" \
    "$(pgq "$DB" "SELECT count(*) FROM $t r LEFT JOIN $st s ON s.$so = r.$o AND s.$si = r.$i WHERE r.$o >= $OFF AND (s.$so IS NULL OR s.$sd <= $(base_sk "$st"))" 2>/dev/null)" -eq 0
  expect "$t: no extended return before its sale" \
    "$(pgq "$DB" "SELECT count(*) FROM $t r JOIN $st s ON s.$so = r.$o AND s.$si = r.$i WHERE r.$o >= $OFF AND r.$d < s.$sd")" -eq 0
  expect "$t: has extended rows" "$(pgq "$DB" "SELECT count(*) FROM $t WHERE $o >= $OFF")" -gt 0
done
expect "inventory: (date, item, warehouse) unique" \
  "$(pgq "$DB" "SELECT count(*) FROM (SELECT 1 FROM inventory GROUP BY inv_date_sk, inv_item_sk, inv_warehouse_sk HAVING count(*) > 1) z")" -eq 0
expect "inventory: has extended rows" "$(pgq "$DB" "SELECT count(*) FROM ($(extended_rows_sql inventory)) x" 2>/dev/null)" -gt 0
finish
