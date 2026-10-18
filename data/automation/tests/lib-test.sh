# Shared by data/automation/tests/*.sh. Usage in a test:  CTX=… POD=… NS=… ; source "$(dirname "$0")/lib-test.sh"
# The assertions and the scratch-copy helpers are the extend suite's (one place: ../../extend/tests/lib-test.sh);
# this adds the automation runners, the table lists and the fingerprints.
HERE_A="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AUTO_DIR="$(cd "$HERE_A/.." && pwd)"
# shellcheck source=../../extend/tests/lib-test.sh
source "$AUTO_DIR/../extend/tests/lib-test.sh"

log_of() { echo "${TMPDIR:-/tmp}/automation-$1-$2.log"; }
out_of() { echo "${TMPDIR:-/tmp}/automation-out-$1"; }   # where a test build writes expected/ and events/
run_automation() { # run_automation <db> [as-of] — the real runner, quiet; its output in $(log_of build <db>), its
  # CSVs under $(out_of <db>) — never over the committed data/automation/expected/ and events/
  rm -rf "$(out_of "$1")"
  AUTOMATION_OUT="$(out_of "$1")" "$AUTO_DIR/run-automation.sh" "$CTX" "$1" "${2:-}" "$POD" > "$(log_of build "$1")" 2>&1
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
AU_INTERNALS="_automation_meta _automation_base _automation_plan _automation_events _automation_undo _automation_expected"
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

# The recipes' parameters (17 §1) — automation.conf mirrors them as p_*; money ones × the world's scale.
param() { conf "p_$1"; }
scale_of() { # scale_of <db> — 1, or threshold_scale_cz in a CZ world
  if [ "$(pgq "$1" "SELECT to_regclass('public._localize_meta') IS NOT NULL")" = t ]; then conf threshold_scale_cz; else echo 1; fi
}

# probe_release <db> <as-of> <tolerance> <threshold> — 17 §3 end to end: `order routes` (sorted, comma-joined) for every
# candidate (state placed/held), from the three contexts and the overlapping switch.
probe_release() {
  pgq "$1" "WITH o AS (SELECT so_order_number, so_value FROM sales_order WHERE so_state IN ('placed', 'held')),
                 stock AS (SELECT DISTINCT ON (inv_item_sk, inv_warehouse_sk) inv_item_sk, inv_warehouse_sk, inv_quantity_on_hand
                             FROM inventory ORDER BY inv_item_sk, inv_warehouse_sk, inv_date_sk DESC),
                 out_ AS (SELECT DISTINCT wo_warehouse_sk FROM warehouse_outage WHERE wo_from_date <= DATE '$2' AND wo_to_date >= DATE '$2'),
                 short AS (SELECT s.sl_order_number, count(*) n FROM o JOIN sales_line s ON s.sl_order_number = o.so_order_number
                             LEFT JOIN stock st ON st.inv_item_sk = s.sl_item_sk AND st.inv_warehouse_sk = s.sl_warehouse_sk
                             LEFT JOIN out_ ON out_.wo_warehouse_sk = s.sl_warehouse_sk
                            WHERE out_.wo_warehouse_sk IS NOT NULL OR coalesce(st.inv_quantity_on_hand, 0) < s.sl_quantity GROUP BY 1),
                 l AS (SELECT s.sl_order_number, s.sl_line_no, s.sl_item_sk, s.sl_unit_price, oo.so_customer_sk, oo.so_channel, oo.so_placed_date
                         FROM o JOIN sales_order oo USING (so_order_number) JOIN sales_line s ON s.sl_order_number = o.so_order_number),
                 a AS (SELECT l.sl_order_number, l.sl_line_no, COALESCE(cp.cp_price, pl.pl_price) AS price FROM l
                         LEFT JOIN customer_price cp ON cp.cp_item_sk = l.sl_item_sk AND cp.cp_customer_sk = l.so_customer_sk
                              AND cp.cp_valid_from <= l.so_placed_date AND (cp.cp_valid_to IS NULL OR cp.cp_valid_to >= l.so_placed_date)
                         LEFT JOIN price_list pl ON pl.pl_item_sk = l.sl_item_sk AND pl.pl_channel = l.so_channel
                              AND pl.pl_valid_from <= l.so_placed_date AND (pl.pl_valid_to IS NULL OR pl.pl_valid_to >= l.so_placed_date)),
                 price AS (SELECT l.sl_order_number, count(*) n FROM l JOIN a USING (sl_order_number, sl_line_no)
                            WHERE a.price IS NULL OR abs(l.sl_unit_price - a.price) > $3 GROUP BY 1),
                 due AS (SELECT oo.so_order_number, count(*) n FROM o JOIN sales_order oo USING (so_order_number)
                           JOIN invoice i ON i.inv_customer_sk = oo.so_customer_sk WHERE i.inv_status = 'open' AND i.inv_due < DATE '$2' GROUP BY 1),
                 v AS (SELECT o.so_order_number k, o.so_value, coalesce(sh.n, 0) n_short, coalesce(pr.n, 0) n_price, coalesce(d.n, 0) n_due
                         FROM o LEFT JOIN short sh ON sh.sl_order_number = o.so_order_number
                         LEFT JOIN price pr ON pr.sl_order_number = o.so_order_number LEFT JOIN due d ON d.so_order_number = o.so_order_number)
            SELECT k || ' ' || array_to_string(array_remove(ARRAY[
                     CASE WHEN n_due > 0 THEN 'hold_ar' END,
                     CASE WHEN n_short > 0 OR n_price > 0 THEN 'hold_sales' END,
                     CASE WHEN n_short = 0 AND n_price = 0 AND n_due = 0 AND so_value <= $4 THEN 'release' END,
                     CASE WHEN n_short = 0 AND n_price = 0 AND n_due = 0 AND so_value > $4 THEN 'release_confirmed' END], NULL), ',')
              FROM v ORDER BY k"
}

# probe_decide <db> <as-of> <return_window> <abuse_share> <care_threshold> <small_value> — 17 §4.1 end to end:
# `line route` for every received line, from the four contexts and the exclusive switch.
probe_decide() {
  pgq "$1" "WITH q AS (SELECT l.rl_line_id line_id, l.rl_request_number request_number, l.rl_item_sk item, l.rl_quantity quantity,
                             l.rl_quantity * l.rl_unit_price line_value, l.rl_reason reason, l.rl_requested_resolution resolution,
                             l.rl_requested_variant_sk variant, r.rr_customer_sk customer, r.rr_order_number order_number
                        FROM return_request_line l JOIN return_request r ON r.rr_request_number = l.rl_request_number
                       WHERE l.rl_state = 'received'),
                 b AS (SELECT q.line_id, o.so_delivered_date delivered,
                              CASE WHEN o.so_delivered_date >= DATE '$2' - $3 THEN 1 ELSE 0 END in_window,
                              CASE WHEN s.sl_item_sk IS NULL THEN 0 ELSE 1 END on_order
                         FROM q LEFT JOIN sales_order o ON o.so_order_number = q.order_number AND o.so_customer_sk = q.customer
                         LEFT JOIN sales_line s ON s.sl_order_number = q.order_number AND s.sl_item_sk = q.item),
                 sh AS (SELECT q.line_id,
                               COALESCE((SELECT sum(rl.rl_quantity * rl.rl_unit_price) FROM return_request_line rl
                                           JOIN return_request rr ON rr.rr_request_number = rl.rl_request_number
                                          WHERE rr.rr_customer_sk = q.customer AND rr.rr_requested_date >= DATE '$2' - 365 AND rl.rl_state <> 'rejected'), 0)
                               / NULLIF((SELECT sum(s.sl_ext_sales_price) FROM sales_line s
                                          WHERE s.sl_customer_sk = q.customer AND s.sl_sold_date >= DATE '$2' - 365), 0) share
                          FROM q),
                 rv AS (SELECT rl_request_number request_number, sum(rl_quantity * rl_unit_price) request_value FROM return_request_line GROUP BY 1),
                 lt AS (SELECT DISTINCT ON (inv_item_sk, inv_warehouse_sk) inv_item_sk, inv_warehouse_sk, inv_quantity_on_hand
                          FROM inventory ORDER BY inv_item_sk, inv_warehouse_sk, inv_date_sk DESC),
                 st AS (SELECT q.line_id, coalesce(li.inv_quantity_on_hand, 0) item_on_hand, coalesce(lv.inv_quantity_on_hand, 0) variant_on_hand
                          FROM q JOIN customer c ON c.c_customer_sk = q.customer
                          LEFT JOIN lt li ON li.inv_item_sk = q.item AND li.inv_warehouse_sk = c.c_center_sk
                          LEFT JOIN lt lv ON lv.inv_item_sk = q.variant AND lv.inv_warehouse_sk = c.c_center_sk)
            SELECT q.line_id || ' ' || CASE
                     WHEN b.delivered IS NULL OR b.on_order = 0 THEN 'reject_not_ours'
                     WHEN b.in_window = 0 THEN 'reject_late'
                     WHEN sh.share > $4 THEN 'reject_abuse'
                     WHEN rv.request_value > $5 THEN 'to_customer_care'
                     WHEN q.line_value < $6 AND q.reason IN ('damaged', 'did_not_arrive') THEN 'refund_no_return'
                     WHEN q.reason IN ('damaged', 'did_not_arrive') AND st.item_on_hand >= q.quantity THEN 'replacement_no_return'
                     WHEN q.resolution = 'exchange' AND st.variant_on_hand >= q.quantity THEN 'exchange'
                     ELSE 'refund_after_return' END
              FROM q JOIN b USING (line_id) JOIN sh USING (line_id) JOIN st USING (line_id) JOIN rv ON rv.request_number = q.request_number
             ORDER BY q.line_id"
}

# probe_reorder <db> <as-of> — H-3 (04): every (item, center) pair with demand in the last 8 weeks whose latest stock
# covers less than 3 weeks of it, as `item:warehouse`.
probe_reorder() {
  pgq "$1" "WITH d AS (SELECT sl_item_sk item, sl_warehouse_sk wh, sum(sl_quantity) / 8.0 weekly FROM sales_line
                        WHERE sl_sold_date > DATE '$2' - 56 AND sl_sold_date <= DATE '$2' GROUP BY 1, 2),
                 lt AS (SELECT DISTINCT ON (inv_item_sk, inv_warehouse_sk) inv_item_sk, inv_warehouse_sk, inv_quantity_on_hand
                          FROM inventory ORDER BY inv_item_sk, inv_warehouse_sk, inv_date_sk DESC)
            SELECT d.item || ':' || d.wh FROM d LEFT JOIN lt ON lt.inv_item_sk = d.item AND lt.inv_warehouse_sk = d.wh
             WHERE coalesce(lt.inv_quantity_on_hand, 0) < 3 * d.weekly ORDER BY 1"
}

digest() { cksum | awk '{print $1 ":" $2}'; }   # a portable fingerprint of stdin (md5 is md5sum on Linux)

# plan_of <db> <kind-pattern> — `key route` of the plan rows whose kind matches (SQL LIKE), sorted like the probes.
plan_of() { pgq "$1" "SELECT key || ' ' || coalesce(expected_route, '') FROM _automation_plan WHERE kind LIKE '$2' ORDER BY key"; }
