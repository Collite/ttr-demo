# Shared by tests/*.sh. Usage in a test:  CTX=… POD=… NS=… ; source "$(dirname "$0")/lib-test.sh"
HERE_T="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXTEND_DIR="$(cd "$HERE_T/.." && pwd)"
# shellcheck source=../lib.sh
source "$EXTEND_DIR/lib.sh"

PASSES=0; FAILS=0
ok()  { echo "  ✓ $*"; PASSES=$((PASSES + 1)); }
bad() { echo "  ✗ $*"; FAILS=$((FAILS + 1)); }

# expect <label> <actual> <op> <expected>   (op: -eq -ne -ge -le -gt -lt for integers, = != for strings)
expect() {
  local label="$1" actual="$2" op="$3" want="$4"
  if [ "$op" = "=" ] || [ "$op" = "!=" ]; then
    if [ "$actual" "$op" "$want" ]; then ok "$label ($actual)"; else bad "$label: got '$actual', want $op '$want'"; fi
  elif [ -n "$actual" ] && [ "$actual" "$op" "$want" ] 2>/dev/null; then ok "$label ($actual)"
  else bad "$label: got '$actual', want $op $want"; fi
}

# expect_between <label> <actual decimal> <low> <high>
expect_between() {
  if [ -n "$2" ] && python3 -c "import sys; sys.exit(0 if $3 <= float('$2') <= $4 else 1)" 2>/dev/null; then
    ok "$1 ($2 in [$3, $4])"
  else bad "$1: got '$2', want within [$3, $4]"; fi
}

finish() {
  echo "== $(basename "$0"): $PASSES passed, $FAILS failed"
  [ "$FAILS" -eq 0 ]
}

# scratch_copy <src-db> <scratch-db> — a throwaway copy. TEMPLATE needs the source idle; a fixture
# with live readers falls back to pg_dump | pg_restore inside the server's pod.
scratch_copy() {
  pgq postgres "DROP DATABASE IF EXISTS \"$2\"" >/dev/null
  if ! pgq postgres "CREATE DATABASE \"$2\" TEMPLATE \"$1\"" >/dev/null 2>&1; then
    echo "  (TEMPLATE copy refused — source in use; copying $1 → $2 with pg_dump | pg_restore)"
    pgq postgres "CREATE DATABASE \"$2\"" >/dev/null
    pgsh "pg_dump -U postgres -Fc -d '$1' | pg_restore -U postgres --no-owner -d '$2'" >/dev/null 2>&1 || true
  fi
}

drop_scratch() {
  if [ "${KEEP_SCRATCH:-0}" = 1 ]; then echo "  (KEEP_SCRATCH=1 — kept $1)"; return; fi
  pgq postgres "DROP DATABASE IF EXISTS \"$1\"" >/dev/null
}

run_extend() { # run_extend <db> <until>  — the real runner, quiet
  "$EXTEND_DIR/run-extend.sh" "$CTX" "$1" "$2" "$POD" > "${TMPDIR:-/tmp}/extend-$1-$2.log" 2>&1
}

# The facts, as `table:date_col:order_col:item_col` (order_col empty for inventory).
SALES="store_sales:ss_sold_date_sk:ss_ticket_number:ss_item_sk catalog_sales:cs_sold_date_sk:cs_order_number:cs_item_sk web_sales:ws_sold_date_sk:ws_order_number:ws_item_sk"
# returns as `table:date_col:order_col:item_col:sales_table:sales_order:sales_item:sales_date`
RETURNS="store_returns:sr_returned_date_sk:sr_ticket_number:sr_item_sk:store_sales:ss_ticket_number:ss_item_sk:ss_sold_date_sk catalog_returns:cr_returned_date_sk:cr_order_number:cr_item_sk:catalog_sales:cs_order_number:cs_item_sk:cs_sold_date_sk web_returns:wr_returned_date_sk:wr_order_number:wr_item_sk:web_sales:ws_order_number:ws_item_sk:ws_sold_date_sk"

# base_sk <fact> — the d_date_sk of the fact's recorded base end (SQL scalar subquery text)
base_sk() { echo "(SELECT d.d_date_sk FROM _extend_base b JOIN date_dim d ON d.d_date = b.base_end WHERE b.fact = '$1')"; }

# extended_rows_sql <fact> — SQL selecting the fact's extended rows (whole rows, alias t)
extended_rows_sql() {
  local spec
  for spec in $SALES; do IFS=: read -r t d o i <<<"$spec"
    [ "$t" = "$1" ] && { echo "SELECT t.* FROM $t t WHERE t.$d > $(base_sk "$t")"; return; }; done
  for spec in $RETURNS; do IFS=: read -r t d o i st so si sd <<<"$spec"
    [ "$t" = "$1" ] && { echo "SELECT t.* FROM $t t JOIN $st s ON s.$so = t.$o AND s.$si = t.$i WHERE s.$sd > $(base_sk "$st")"; return; }; done
  [ "$1" = inventory ] && echo "SELECT t.* FROM inventory t WHERE t.inv_date_sk > $(base_sk inventory)"
}

ALL_FACTS="store_sales catalog_sales web_sales store_returns catalog_returns web_returns inventory"

# fp_upto <db> <week_seq> — md5 per fact over the extended rows dated in weeks <= week_seq
# (a return with no return date counts in its sale's week). One line per fact: `fact md5 rows`.
fp_upto() {
  local db="$1" w="$2" sql="" spec t d o i st so si sd
  for spec in $SALES; do IFS=: read -r t d o i <<<"$spec"
    sql+="SELECT '$t' f, md5(coalesce(string_agg(x::text, '|' ORDER BY x::text), '')) h, count(*) n FROM ($(extended_rows_sql "$t")) x JOIN date_dim dd ON dd.d_date_sk = x.$d WHERE dd.d_week_seq <= $w UNION ALL "
  done
  for spec in $RETURNS; do IFS=: read -r t d o i st so si sd <<<"$spec"
    sql+="SELECT '$t' f, md5(coalesce(string_agg(x::text, '|' ORDER BY x::text), '')) h, count(*) n FROM $t x JOIN $st s ON s.$so = x.$o AND s.$si = x.$i JOIN date_dim ds ON ds.d_date_sk = s.$sd LEFT JOIN date_dim dr ON dr.d_date_sk = x.$d WHERE s.$sd > $(base_sk "$st") AND coalesce(dr.d_week_seq, ds.d_week_seq) <= $w UNION ALL "
  done
  sql+="SELECT 'inventory' f, md5(coalesce(string_agg(x::text, '|' ORDER BY x::text), '')) h, count(*) n FROM ($(extended_rows_sql inventory)) x JOIN date_dim dd ON dd.d_date_sk = x.inv_date_sk WHERE dd.d_week_seq <= $w"
  pgq "$db" "SELECT f || ' ' || h || ' ' || n FROM ($sql) z ORDER BY f"
}

total_rows() { # total_rows <db> — all rows of the seven facts
  local f sql=""
  for f in $ALL_FACTS; do sql+="SELECT count(*) AS n FROM $f UNION ALL "; done
  pgq "$1" "SELECT sum(n) FROM (${sql% UNION ALL }) z"
}
