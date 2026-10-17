#!/usr/bin/env bash
# AU-hartland P1·S1.1 T1 (added: the derivation rules, README.md) — the H-1 tables say what the facts say, and
# the demo day's open orders are CLEAN before S1.2 plants their defects: 17 §3's own context queries
# (shortfall, price_differences, overdue — tests/lib-test.sh `probe_*`) find nothing on them.
# Works on a throwaway copy of <db>:   test-orders.sh <ctx> <db> [pod]
set -uo pipefail
CTX="${1:?usage: test-orders.sh <ctx> <db> [pod]}"; SRC="${2:?db}"; POD="${3:-hartland-pg-1}"; NS="${EXTEND_NS:-data}"
source "$(dirname "$0")/lib-test.sh"
S="${SRC}_au_orders"
q() { pgq "$S" "$1"; }

echo "== orders, pricing, invoices, outages, centers, calendar — on a scratch copy of $SRC ($S)"
scratch_copy "$SRC" "$S"
run_automation "$S"; rc=$?
expect "the build exits 0" "$rc" -eq 0
A=$(as_of_of "$S"); off=$(conf web_order_offset); ty=$(conf template_year)
scale=1; [ "$(q "SELECT to_regclass('_localize_meta') IS NOT NULL")" = t ] && scale=$(conf threshold_scale_cz)
cap=$(q "SELECT $(conf confirmation_threshold) * $(conf open_value_cap) * $scale")

# ── sales_line / sales_order: one line per COMPLETE fact line of a kept order ────────────────────────────────
# Complete = quantity > 0, amount and warehouse known; kept = a complete line, a bill customer and a sold date
# on or before as_of (both shared across the order's lines in TPC-DS, so a line missing one takes the order's).
FACT="SELECT 'web' ch, ws_order_number + $off o, ws_item_sk i, ws_quantity q, ws_ext_sales_price x, ws_warehouse_sk w, ws_sold_date_sk d, ws_bill_customer_sk c FROM web_sales
      UNION ALL SELECT 'marketplace', cs_order_number, cs_item_sk, cs_quantity, cs_ext_sales_price, cs_warehouse_sk, cs_sold_date_sk, cs_bill_customer_sk FROM catalog_sales"
KEPT="SELECT f.o FROM ($FACT) f LEFT JOIN date_dim d ON d.d_date_sk = f.d GROUP BY f.o
      HAVING bool_or(f.q > 0 AND f.x IS NOT NULL AND f.w IS NOT NULL) AND count(f.c) > 0 AND min(d.d_date) <= DATE '$A'"
expect "sales_line = the complete lines of the kept orders" "$(q "SELECT count(*) FROM sales_line")" -eq \
  "$(q "SELECT count(*) FROM ($FACT) f WHERE f.o IN ($KEPT) AND f.q > 0 AND f.x IS NOT NULL AND f.w IS NOT NULL")"
expect "sales_order = the kept orders" "$(q "SELECT count(*) FROM sales_order")" -eq "$(q "SELECT count(*) FROM ($KEPT) k")"
expect "some fact lines of kept orders were left out as incomplete (the fixture has NULLs)" \
  "$(( $(q "SELECT count(*) FROM ($FACT) f WHERE f.o IN ($KEPT)") - $(q "SELECT count(*) FROM sales_line") ))" -gt 0
expect "web and marketplace numbers that overlap in the facts are both orders" "$(q "SELECT count(*) FROM web_sales w
    WHERE EXISTS (SELECT 1 FROM catalog_sales c WHERE c.cs_order_number = w.ws_order_number)
      AND EXISTS (SELECT 1 FROM sales_order o WHERE o.so_order_number = w.ws_order_number + $off AND o.so_channel = 'web')")" -gt 0
expect "every order's channel is its lines' channel" "$(q "SELECT count(*) FROM sales_line s JOIN sales_order o ON o.so_order_number = s.sl_order_number WHERE s.sl_channel <> o.so_channel")" -eq 0
expect "line numbers run 1..n per order, by item" "$(q "SELECT count(*) FROM (SELECT sl_line_no, row_number() OVER (PARTITION BY sl_order_number ORDER BY sl_item_sk) rn FROM sales_line) z WHERE sl_line_no <> rn")" -eq 0
expect "every order's value is the sum of its lines" "$(q "SELECT count(*) FROM sales_order o JOIN (SELECT sl_order_number, sum(sl_ext_sales_price) v FROM sales_line GROUP BY 1) l ON l.sl_order_number = o.so_order_number WHERE l.v <> o.so_value")" -eq 0
expect "every line carries its order's customer" "$(q "SELECT count(*) FROM sales_line s JOIN sales_order o ON o.so_order_number = s.sl_order_number WHERE s.sl_customer_sk IS DISTINCT FROM o.so_customer_sk")" -eq 0
expect "an order's warehouse is its lines' modal warehouse" "$(q "SELECT count(*) FROM sales_order o JOIN (SELECT sl_order_number, mode() WITHIN GROUP (ORDER BY sl_warehouse_sk) w FROM sales_line GROUP BY 1) l ON l.sl_order_number = o.so_order_number WHERE l.w <> o.so_warehouse_sk")" -eq 0
expect "no order placed after as_of" "$(q "SELECT count(*) FROM sales_order WHERE so_placed_date > DATE '$A'")" -eq 0
expect "delivered 3–7 days after placement iff placed more than $(conf delivered_after) days before as_of" "$(q "SELECT count(*) FROM sales_order WHERE so_state = 'released' AND NOT (
    (so_placed_date < DATE '$A' - $(conf delivered_after) AND so_delivered_date - so_placed_date BETWEEN 3 AND 7)
 OR (so_placed_date >= DATE '$A' - $(conf delivered_after) AND so_delivered_date IS NULL))")" -eq 0
expect "every order was placed by the shop" "$(q "SELECT count(*) FROM sales_order WHERE so_placed_by IS DISTINCT FROM 'shop' OR so_held_for IS NOT NULL")" -eq 0

# ── the demo day's open orders ──────────────────────────────────────────────────────────────────────────────
expect "exactly $(conf placed_orders) open orders (state placed), the rest released" "$(q "SELECT count(*) FILTER (WHERE so_state = 'placed') || '/' || count(*) FILTER (WHERE so_state NOT IN ('placed', 'released'))
    FROM sales_order")" = "$(conf placed_orders)/0"
# An order's value at the price list (the customer's price where valid, else the channel's) — what opening it costs.
LISTV="SELECT o.so_order_number, sum(round(coalesce(cp.cp_price, pl.pl_price) * s.sl_quantity, 2)) v
         FROM sales_order o JOIN sales_line s ON s.sl_order_number = o.so_order_number
         LEFT JOIN customer_price cp ON cp.cp_item_sk = s.sl_item_sk AND cp.cp_customer_sk = o.so_customer_sk
              AND cp.cp_valid_from <= o.so_placed_date AND (cp.cp_valid_to IS NULL OR cp.cp_valid_to >= o.so_placed_date)
         LEFT JOIN price_list pl ON pl.pl_item_sk = s.sl_item_sk AND pl.pl_channel = o.so_channel
              AND pl.pl_valid_from <= o.so_placed_date AND (pl.pl_valid_to IS NULL OR pl.pl_valid_to >= o.so_placed_date)
        GROUP BY o.so_order_number"
expect "the open orders are the latest under the cap (no such released order is newer than the oldest open one's day)" \
  "$(q "SELECT count(*) FROM sales_order r JOIN ($LISTV) lv ON lv.so_order_number = r.so_order_number
         WHERE r.so_state = 'released' AND lv.v <= $cap
           AND r.so_placed_date > (SELECT min(so_placed_date) FROM sales_order WHERE so_state = 'placed')")" -eq 0
expect "some recent orders were passed over for the cap (the cap is live)" \
  "$(q "SELECT count(*) FROM sales_order r JOIN ($LISTV) lv ON lv.so_order_number = r.so_order_number
         WHERE r.so_state = 'released' AND lv.v > $cap
           AND r.so_placed_date >= (SELECT min(so_placed_date) FROM sales_order WHERE so_state = 'placed')")" -gt 0
expect "no open order is delivered" "$(q "SELECT count(*) FROM sales_order WHERE so_state = 'placed' AND so_delivered_date IS NOT NULL")" -eq 0
expect "every open order stays under the cap ($cap)" "$(q "SELECT count(*) FROM sales_order WHERE so_state = 'placed' AND so_value > $cap")" -eq 0
expect "17 §3 shortfall finds no open order short (none planted yet)" "$(probe_shortfall "$S" "$A" | wc -l | tr -d ' ')" -eq 0
expect "17 §3 price_differences finds no open line off its price" "$(probe_price "$S" 0.01 | wc -l | tr -d ' ')" -eq 0
expect "17 §3 overdue finds no open order's customer overdue" "$(probe_overdue "$S" "$A" | wc -l | tr -d ' ')" -eq 0
expect "some open lines are priced from an individual price (the customer_price path is live)" "$(q "SELECT count(*) FROM sales_line s
    JOIN sales_order o ON o.so_order_number = s.sl_order_number AND o.so_state = 'placed'
    JOIN customer_price cp ON cp.cp_item_sk = s.sl_item_sk AND cp.cp_customer_sk = o.so_customer_sk AND cp.cp_price = s.sl_unit_price")" -gt 0

# ── price_list / customer_price ─────────────────────────────────────────────────────────────────────────────
expect "one open-ended list price from $ty-01-01 per (item, channel) sold" "$(q "SELECT count(*) FROM price_list WHERE pl_valid_to IS NULL AND pl_valid_from = DATE '$ty-01-01'")" -eq \
  "$(q "SELECT count(*) FROM (SELECT DISTINCT sl_item_sk, sl_channel FROM sales_line) z")"
expect "the year before is a closed window at 97 %" "$(q "SELECT count(*) FROM price_list c JOIN price_list o ON o.pl_item_sk = c.pl_item_sk AND o.pl_channel = c.pl_channel AND o.pl_valid_to IS NULL
    WHERE c.pl_valid_from = DATE '$((ty - 1))-01-01' AND c.pl_valid_to = DATE '$((ty - 1))-12-31' AND c.pl_price = round(o.pl_price * 0.97, 2)")" -eq \
  "$(q "SELECT count(*) FROM price_list WHERE pl_valid_to IS NULL")"
expect "no list price is zero or missing" "$(q "SELECT count(*) FROM price_list WHERE pl_price IS NULL OR pl_price <= 0")" -eq 0
expect_between "individual prices on ~2 % of the (customer, item) pairs with lines (%)" \
  "$(q "SELECT round(100.0 * (SELECT count(*) FROM customer_price) / count(*), 2) FROM (SELECT DISTINCT sl_customer_sk, sl_item_sk FROM sales_line) p")" 1 3
expect "every individual price is below the item's lowest list price" "$(q "SELECT count(*) FROM customer_price cp
    WHERE cp.cp_price >= (SELECT min(pl_price) FROM price_list WHERE pl_item_sk = cp.cp_item_sk AND pl_valid_to IS NULL)")" -eq 0

# ── invoices ────────────────────────────────────────────────────────────────────────────────────────────────
expect "one invoice per released order, none for an open one" "$(q "SELECT count(*) FROM invoice")" -eq "$(q "SELECT count(*) FROM sales_order WHERE so_state = 'released'")"
expect "no invoice for an open order" "$(q "SELECT count(*) FROM invoice i JOIN sales_order o ON o.so_order_number = i.inv_order_number WHERE o.so_state <> 'released'")" -eq 0
expect "invoice = the order's value, its customer, issued at delivery (else placement), due +$(conf payment_days), paid" "$(q "SELECT count(*) FROM invoice i JOIN sales_order o ON o.so_order_number = i.inv_order_number
    WHERE i.inv_amount <> o.so_value OR i.inv_customer_sk <> o.so_customer_sk OR i.inv_issued <> coalesce(o.so_delivered_date, o.so_placed_date)
       OR i.inv_due <> i.inv_issued + $(conf payment_days) OR i.inv_paid <> i.inv_amount OR i.inv_status <> 'paid'")" -eq 0

# ── outages, centers, calendar ──────────────────────────────────────────────────────────────────────────────
n=$(conf outages_per_center)
expect "$n outage windows per warehouse, all in $ty, 1–3 days" "$(q "SELECT count(*) FROM warehouse_outage WHERE extract(year FROM wo_from_date) = $ty AND extract(year FROM wo_to_date) = $ty AND wo_to_date - wo_from_date BETWEEN 0 AND 2")" -eq \
  "$(q "SELECT $n * count(*) FROM warehouse")"
expect "no outage over as_of (S1.2 plants that one)" "$(q "SELECT count(*) FROM warehouse_outage WHERE DATE '$A' BETWEEN wo_from_date AND wo_to_date")" -eq 0
expect "a warehouse's windows do not overlap" "$(q "SELECT count(*) FROM warehouse_outage a JOIN warehouse_outage b ON a.wo_warehouse_sk = b.wo_warehouse_sk AND a.wo_from_date < b.wo_from_date AND b.wo_from_date <= a.wo_to_date")" -eq 0
expect "a customer's center = the modal warehouse of their lines (ties: the lower sk)" "$(q "SELECT count(*) FROM customer c LEFT JOIN (
      SELECT DISTINCT ON (sl_customer_sk) sl_customer_sk, sl_warehouse_sk FROM sales_line
       GROUP BY sl_customer_sk, sl_warehouse_sk ORDER BY sl_customer_sk, count(*) DESC, sl_warehouse_sk) m ON m.sl_customer_sk = c.c_customer_sk
    WHERE c.c_center_sk IS DISTINCT FROM m.sl_warehouse_sk")" -eq 0
expect "customers who never ordered have no center" "$(q "SELECT count(*) FROM customer WHERE c_center_sk IS NULL")" -gt 0
expect "d_working_day = not a holiday and not a weekend, every day" "$(q "SELECT count(*) FROM date_dim WHERE d_working_day IS DISTINCT FROM (d_holiday = 'N' AND d_weekend = 'N')")" -eq 0
expect "a Saturday is not a working day, a plain Tuesday is" "$(q "SELECT bool_or(d_working_day) FILTER (WHERE extract(isodow FROM d_date) = 6)::text || bool_and(d_working_day) FILTER (WHERE extract(isodow FROM d_date) = 2 AND d_holiday = 'N')::text FROM date_dim")" = falsetrue

drop_scratch "$S"
finish
