#!/usr/bin/env bash
# AU-hartland P1·S1.3 T1 — the golden seeds (contracts §5, §7): the build writes expected/<world>/<recipe>.csv — one
# row per planted key and route (`key,route,verdict_reason_template,detail_count`), the template = 17's `because:`
# with its {fills} left in, the detail count = the rows each detail context carries — and the files say what the
# plan says.   test-expected.sh <ctx> <db> [pod]
set -uo pipefail
CTX="${1:?usage: test-expected.sh <ctx> <db> [pod]}"; SRC="${2:?db}"; POD="${3:-hartland-pg-1}"; NS="${EXTEND_NS:-data}"
source "$(dirname "$0")/lib-test.sh"
S="${SRC}_au_expected"
q() { pgq "$S" "$1"; }

echo "== expected verdicts, on a scratch copy of $SRC ($S)"
scratch_copy "$SRC" "$S"
run_automation "$S"; rc=$?
expect "the build exits 0" "$rc" -eq 0
E="$(out_of "$S")/expected/us"
csv() { tail -n +2 "$E/$1.csv"; }                     # the rows, no header
route_n() { csv "$1" | awk -F, -v r="$2" '$2 == r' | wc -l | tr -d ' '; }
row_of() { csv "$1" | awk -F, -v k="$2" -v r="$3" '$1 == k && $2 == r'; }

for r in release_order decide_return monitor_inbound settle reorder_proposals winback; do
  expect "$r.csv exists, with the seed header" "$(head -1 "$E/$r.csv" 2>/dev/null)" = "key,route,verdict_reason_template,detail_count"
done
expect "release_order: a row per open order and route (both holds = two rows)" "$(csv release_order | wc -l | tr -d ' ')" -eq \
  "$(( $(conf placed_orders) + $(conf held_orders) + 2 ))"
while read -r recipe route want; do
  expect "$recipe: $want × $route" "$(route_n "$recipe" "$route")" -eq "$want"
done <<'ROUTES'
release_order hold_ar 7
release_order release_confirmed 2
decide_return reject_not_ours 4
decide_return reject_late 4
decide_return reject_abuse 3
decide_return to_customer_care 4
decide_return refund_no_return 6
decide_return replacement_no_return 6
decide_return exchange 5
decide_return refund_after_return 8
monitor_inbound none 4
monitor_inbound remind 4
monitor_inbound expired 4
monitor_inbound complete 3
monitor_inbound damaged 2
settle credit_note_issued 6
settle money_received 3
settle money_overdue 3
settle goods_shipped 2
settle goods_overdue 2
settle closed 5
reorder_proposals propose 25
winback none 10
ROUTES
expect "release_order: 21 holds for Sales (short 8, outage 2, price 6, held 3, both 2)" "$(route_n release_order hold_sales)" -eq 21
expect "release_order: the rest release (122 clean + 3 individual prices)" "$(route_n release_order release)" -eq $(( $(conf placed_orders) + $(conf held_orders) - 28 ))

# 17's because: strings, {fills} intact
tpl() { csv "$1" | awk -F, -v r="$2" '$2 == r {print $3; exit}'; }
expect "hold_sales says why" "$(tpl release_order hold_sales)" = "stock shortfall or price difference"
expect "release_confirmed says why" "$(tpl release_order release_confirmed)" = "all checks passed; above the confirmation threshold"
expect "late keeps its {fill}" "$(tpl decide_return reject_late)" = "delivered more than {return_window} days ago"
expect "abuse keeps its {fill}" "$(tpl decide_return reject_abuse)" = "return share {share} above the limit"
expect "remind keeps its {fill}" "$(tpl monitor_inbound remind)" = "nothing returned after {inbound_reminder} days"
expect "money_overdue keeps its {fill}" "$(tpl settle money_overdue)" = "refund {max_late} working days late"
expect "a none row has no reason (no verdict row is written)" "$(tpl monitor_inbound none)" = ""

# detail counts: the rows each detail context of the route carries, `context:n` space-separated
k=$(q "SELECT key FROM _automation_plan WHERE kind = 'release:short' ORDER BY key LIMIT 1")
expect "a short order: one shortfall line, no price difference" "$(row_of release_order "$k" hold_sales | cut -d, -f4)" = "shortfall:1 price_differences:0"
k=$(q "SELECT key FROM _automation_plan WHERE kind = 'release:price_above_list' ORDER BY key LIMIT 1")
expect "a price plant: one price difference" "$(row_of release_order "$k" hold_sales | cut -d, -f4)" = "shortfall:0 price_differences:1"
k=$(q "SELECT key FROM _automation_plan WHERE kind = 'release:both' ORDER BY key LIMIT 1")
expect "both: one overdue invoice under hold_ar" "$(row_of release_order "$k" hold_ar | cut -d, -f4)" = "overdue:1"
k=$(q "SELECT key FROM _automation_plan WHERE kind = 'release:outage' ORDER BY key LIMIT 1")
expect "an outage order: every line at the out center is a shortfall line" "$(row_of release_order "$k" hold_sales | cut -d, -f4)" = \
  "shortfall:$(q "SELECT count(*) FROM sales_line s JOIN warehouse_outage w ON w.wo_warehouse_sk = s.sl_warehouse_sk AND DATE '$(as_of_of "$S")' BETWEEN w.wo_from_date AND w.wo_to_date WHERE s.sl_order_number = $k") price_differences:0"
k=$(q "SELECT rc_line_id FROM return_receipt WHERE rc_line_id::text IN (SELECT key FROM _automation_plan WHERE kind = 'inbound:damaged') GROUP BY 1 HAVING count(*) = 2")
expect "a short return: two receipt rows (one ok, one missing)" "$(row_of monitor_inbound "$k" damaged | cut -d, -f4)" = "receipts:2"
k=$(q "SELECT key FROM _automation_plan WHERE kind = 'settle:unpaid' ORDER BY key LIMIT 1")
expect "an unpaid refund: one open obligation (the payment, from P4)" "$(row_of settle "$k" money_overdue | cut -d, -f4)" = "open_obligations:1"
expect "a release row has no detail" "$(csv release_order | awk -F, '$2 == "release" {print $4; exit}')" = ""

total=$(for r in release_order decide_return monitor_inbound settle reorder_proposals winback; do csv $r; done | wc -l | tr -d ' ')
expect "the files are _automation_expected, row for row" "$total" -eq "$(q "SELECT count(*) FROM _automation_expected")"
expect "every planted route of every recipe is in a file" "$(q "SELECT count(*) FROM _automation_plan p CROSS JOIN LATERAL string_to_table(p.expected_route, ',') r
    WHERE p.kind ~ '^(release|decide|inbound|settle|reorder|winback):'")" -eq "$total"

drop_scratch "$S"
finish
