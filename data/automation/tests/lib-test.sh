# Shared by data/automation/tests/*.sh. Usage in a test:  CTX=… POD=… NS=… ; source "$(dirname "$0")/lib-test.sh"
# The assertions and the scratch-copy helpers are the extend suite's (one place: ../../extend/tests/lib-test.sh);
# this adds the automation runners, the table lists and the fingerprints.
HERE_A="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AUTO_DIR="$(cd "$HERE_A/.." && pwd)"
# shellcheck source=../../extend/tests/lib-test.sh
source "$AUTO_DIR/../extend/tests/lib-test.sh"

log_of() { echo "${TMPDIR:-/tmp}/automation-$1-$2.log"; }
run_automation() { # run_automation <db> [as-of] — the real runner, quiet; its output in $(log_of build <db>)
  "$AUTO_DIR/run-automation.sh" "$CTX" "$1" "${2:-}" "$POD" > "$(log_of build "$1")" 2>&1
}
run_reset() { # run_reset <db> — the real reset, quiet
  "$AUTO_DIR/run-reset.sh" "$CTX" "$1" "$POD" > "$(log_of reset "$1")" 2>&1
}
conf() { # conf <name> — a frozen parameter of automation.conf (`\set name value`)
  awk -v n="$1" '$1 == "\\set" && $2 == n { print $3; exit }' "$AUTO_DIR/automation.conf"
}

# contracts §1: the extension's tables, its views, its internals; the base tables it changes and the ones it reads.
AU_TABLES="sales_order sales_line price_list customer_price invoice warehouse_outage return_request_hdr return_request_line return_receipt credit_note refund_payment replacement_shipment reorder_proposal winback_mail"
AU_VIEWS="return_request document_flow"
AU_INTERNALS="_automation_meta _automation_base _automation_plan _automation_events _automation_undo"
BASE_CHANGED="customer date_dim inventory"
BASE_READ="web_sales catalog_sales web_returns catalog_returns item warehouse reason _extend_meta _extend_base"

# fp <db> <relation>... — one line per relation: `name md5 rows`, every row in text order. `_automation_meta`
# is fingerprinted without its run_at (a timestamp is not part of what a build wrote).
fp() {
  local db="$1" r sql=""; shift
  for r in "$@"; do
    if [ "$r" = _automation_meta ]; then
      sql+="SELECT '$r' t, md5(coalesce(string_agg(x::text, '|' ORDER BY x::text), '')) h, count(*) n FROM (SELECT step, as_of, rows FROM _automation_meta) x UNION ALL "
    else
      sql+="SELECT '$r' t, md5(coalesce(string_agg(x::text, '|' ORDER BY x::text), '')) h, count(*) n FROM $r x UNION ALL "
    fi
  done
  pgq "$db" "SELECT t || ' ' || h || ' ' || n FROM (${sql% UNION ALL }) z ORDER BY t"
}

# fp_base <db> — the base tables over their ORIGINAL columns (the two the extension adds left out): what a
# reset must give back byte for byte.
fp_base() {
  local db="$1" t cols sql=""
  for t in $BASE_CHANGED $BASE_READ; do
    cols=$(pgq "$db" "SELECT string_agg(quote_ident(column_name), ', ' ORDER BY ordinal_position) FROM information_schema.columns
                      WHERE table_schema = 'public' AND table_name = '$t' AND column_name NOT IN ('c_center_sk', 'd_working_day')")
    sql+="SELECT '$t' t, md5(coalesce(string_agg(x::text, '|' ORDER BY x::text), '')) h, count(*) n FROM (SELECT $cols FROM $t) x UNION ALL "
  done
  pgq "$db" "SELECT t || ' ' || h || ' ' || n FROM (${sql% UNION ALL }) z ORDER BY t"
}

# fp_build <db> — everything a build writes: the extension's tables, its internals, the changed base tables.
fp_build() { fp "$1" $AU_TABLES $AU_INTERNALS $BASE_CHANGED; }

exists() { # exists <db> <relation> → 1 | 0
  pgq "$1" "SELECT CASE WHEN to_regclass('public.$2') IS NULL THEN 0 ELSE 1 END"
}

as_of_of() { pgq "$1" "SELECT as_of FROM _automation_meta WHERE step = 'build'"; }

# ── the recipes' own context queries over the physical tables (17 §3) — "the data says what the recipe will" ──
# Each prints `order_number count` for the open orders (state placed/held) the context flags.
probe_shortfall() { # probe_shortfall <db> <as-of>
  pgq "$1" "WITH stock AS (SELECT DISTINCT ON (inv_item_sk, inv_warehouse_sk) inv_item_sk, inv_warehouse_sk, inv_quantity_on_hand
                             FROM inventory ORDER BY inv_item_sk, inv_warehouse_sk, inv_date_sk DESC),
                 out_ AS (SELECT DISTINCT wo_warehouse_sk FROM warehouse_outage WHERE wo_from_date <= DATE '$2' AND wo_to_date >= DATE '$2')
            SELECT s.sl_order_number || ' ' || count(*)
              FROM sales_order o JOIN sales_line s ON s.sl_order_number = o.so_order_number
              LEFT JOIN stock st ON st.inv_item_sk = s.sl_item_sk AND st.inv_warehouse_sk = s.sl_warehouse_sk
              LEFT JOIN out_ ON out_.wo_warehouse_sk = s.sl_warehouse_sk
             WHERE o.so_state IN ('placed', 'held')
               AND (out_.wo_warehouse_sk IS NOT NULL OR coalesce(st.inv_quantity_on_hand, 0) < s.sl_quantity)
             GROUP BY s.sl_order_number ORDER BY 1"
}
probe_price() { # probe_price <db> <tolerance>
  pgq "$1" "WITH l AS (SELECT s.sl_order_number, s.sl_line_no, s.sl_item_sk, s.sl_unit_price, o.so_customer_sk, o.so_channel, o.so_placed_date
                         FROM sales_order o JOIN sales_line s ON s.sl_order_number = o.so_order_number
                        WHERE o.so_state IN ('placed', 'held')),
                 a AS (SELECT l.sl_order_number, l.sl_line_no, COALESCE(cp.cp_price, pl.pl_price) AS price
                         FROM l
                         LEFT JOIN customer_price cp ON cp.cp_item_sk = l.sl_item_sk AND cp.cp_customer_sk = l.so_customer_sk
                              AND cp.cp_valid_from <= l.so_placed_date AND (cp.cp_valid_to IS NULL OR cp.cp_valid_to >= l.so_placed_date)
                         LEFT JOIN price_list pl ON pl.pl_item_sk = l.sl_item_sk AND pl.pl_channel = l.so_channel
                              AND pl.pl_valid_from <= l.so_placed_date AND (pl.pl_valid_to IS NULL OR pl.pl_valid_to >= l.so_placed_date))
            SELECT l.sl_order_number || ' ' || count(*)
              FROM l JOIN a USING (sl_order_number, sl_line_no)
             WHERE a.price IS NULL OR abs(l.sl_unit_price - a.price) > $2
             GROUP BY l.sl_order_number ORDER BY 1"
}
probe_overdue() { # probe_overdue <db> <as-of>
  pgq "$1" "SELECT o.so_order_number || ' ' || count(*)
              FROM sales_order o JOIN invoice i ON i.inv_customer_sk = o.so_customer_sk
             WHERE o.so_state IN ('placed', 'held') AND i.inv_status = 'open' AND i.inv_due < DATE '$2'
             GROUP BY o.so_order_number ORDER BY 1"
}
