#!/usr/bin/env bash
# AU-hartland P1·S1.2 T1 — the demo day's planted cases (contracts §5): every plant kind has its stated count in
# `_automation_plan`, and — the real check — the recipes THEMSELVES, replayed in SQL over the built world
# (tests/lib-test.sh `probe_*`: 17 §3 and §4.1 end to end, H-3's cover rule), route every key exactly as the plan
# says, and nothing else: a key the plan does not name is a key the generator did not mean.
# Works on a throwaway copy of <db>:   test-plants.sh <ctx> <db> [pod]
set -uo pipefail
CTX="${1:?usage: test-plants.sh <ctx> <db> [pod]}"; SRC="${2:?db}"; POD="${3:-hartland-pg-1}"; NS="${EXTEND_NS:-data}"
source "$(dirname "$0")/lib-test.sh"
S="${SRC}_au_plants"
q() { pgq "$S" "$1"; }
n_kind() { q "SELECT count(*) FROM _automation_plan WHERE kind = '$1'"; }

echo "== plants, on a scratch copy of $SRC ($S)"
scratch_copy "$SRC" "$S"
run_automation "$S"; rc=$?
expect "the build exits 0 (it verifies its own plants: 45-verify.sql)" "$rc" -eq 0
A=$(as_of_of "$S"); k=$(scale_of "$S")
T=$(q "SELECT $(param confirmation_threshold) * $k")

# ── contracts §5, row by row (fixed counts exact) ──────────────────────────────────────────────────────────────
while read -r kind want route; do
  expect "$kind: $want planted" "$(n_kind "$kind")" -eq "$want"
  [ "$route" = - ] || expect "$kind: every one expects $route" "$(q "SELECT count(*) FROM _automation_plan WHERE kind = '$kind' AND expected_route IS DISTINCT FROM '$route'")" -eq 0
done <<'EOF'
release:short 8 hold_sales
release:outage 2 hold_sales
release:price_above_list 6 hold_sales
release:individual_price 3 release
release:overdue 5 hold_ar
release:both 2 hold_ar,hold_sales
release:confirm 2 release_confirmed
release:held_yesterday 3 hold_sales
decide:not_ours 4 reject_not_ours
decide:late 4 reject_late
decide:abuse 3 reject_abuse
decide:care 4 to_customer_care
decide:refund_no_return 6 refund_no_return
decide:replacement_no_return 6 replacement_no_return
decide:exchange 5 exchange
decide:refund_after_return 8 refund_after_return
request:multi_line 3 -
inbound:none 4 none
inbound:remind 4 remind
inbound:expired 4 expired
inbound:complete 3 complete
inbound:damaged 2 damaged
settle:paid 3 closed,credit_note_issued,money_received
settle:unpaid 3 credit_note_issued,money_overdue
settle:shipped 2 closed,goods_shipped
settle:missing 2 goods_overdue
reorder:propose 25 propose
winback:mailed 10 none
EOF
expect "every open order is planned: $(conf placed_orders) placed + $(conf held_orders) held" "$(q "SELECT count(*) FILTER (WHERE so_state = 'placed') || '+' || count(*) FILTER (WHERE so_state = 'held') FROM sales_order")" = "$(conf placed_orders)+$(conf held_orders)"
expect "the rest of the open orders are clean releases" "$(n_kind release:clean)" -eq $(( $(conf placed_orders) + $(conf held_orders) - 31 ))
expect "a key is in one release_order kind only" "$(q "SELECT count(*) FROM (SELECT key FROM _automation_plan WHERE kind LIKE 'release:%' GROUP BY key HAVING count(*) > 1) z")" -eq 0
expect "a line is in one H-2 kind only (decide · inbound · settle)" "$(q "SELECT count(*) FROM (SELECT key FROM _automation_plan WHERE kind ~ '^(decide|inbound|settle):' GROUP BY key HAVING count(*) > 1) z")" -eq 0

# ── H-1: 17 §3 replayed over every candidate ───────────────────────────────────────────────────────────────────
expect "17 §3 routes every candidate exactly as planned (both directions)" \
  "$(probe_release "$S" "$A" "$(param tolerance)" "$T" | sort | digest)" = "$(plan_of "$S" 'release:%' | sort | digest)"
expect "the planted orders were placed on or before as_of" "$(q "SELECT count(*) FROM _automation_plan p JOIN sales_order o ON o.so_order_number = CASE WHEN p.key ~ '^[0-9]+$' THEN p.key::int END
    WHERE p.kind LIKE 'release:%' AND (o.so_placed_date > DATE '$A' OR o.so_state NOT IN ('placed', 'held'))")" -eq 0
expect "held yesterday = state held, held for Sales; nothing else is held" "$(q "SELECT count(*) FROM sales_order o LEFT JOIN _automation_plan p ON CASE WHEN p.key ~ '^[0-9]+$' THEN p.key::int END = o.so_order_number AND p.kind = 'release:held_yesterday'
    WHERE (o.so_state = 'held') IS DISTINCT FROM (p.key IS NOT NULL) OR (o.so_state = 'held' AND o.so_held_for IS DISTINCT FROM 'Sales')")" -eq 0
expect "the release_confirmed orders are above the threshold ($T)" "$(q "SELECT count(*) FROM _automation_plan p JOIN sales_order o ON o.so_order_number = CASE WHEN p.key ~ '^[0-9]+$' THEN p.key::int END
    WHERE p.kind = 'release:confirm' AND o.so_value > $T")" -eq 2
expect "one outage over as_of, at one center" "$(q "SELECT count(DISTINCT wo_warehouse_sk) || ':' || count(*) FROM warehouse_outage WHERE DATE '$A' BETWEEN wo_from_date AND wo_to_date")" = 1:1
expect "an order's value is still the sum of its lines" "$(q "SELECT count(*) FROM sales_order o JOIN (SELECT sl_order_number, sum(sl_ext_sales_price) v FROM sales_line GROUP BY 1) l
    ON l.sl_order_number = o.so_order_number WHERE l.v <> o.so_value")" -eq 0

# ── H-2: 17 §4.1 replayed over every received line ─────────────────────────────────────────────────────────────
expect "40 received lines, all planned" "$(q "SELECT count(*) FROM return_request_line WHERE rl_state = 'received'")" -eq 40
expect "17 §4.1 routes every received line exactly as planned" \
  "$(probe_decide "$S" "$A" "$(param return_window)" "$(param abuse_share)" "$(q "SELECT $(param care_threshold) * $k")" "$(q "SELECT $(param small_value) * $k")" | sort | digest)" = \
  "$(plan_of "$S" 'decide:%' | sort | digest)"
expect "the multi-line requests hold 2–3 received lines each" "$(q "SELECT count(*) FROM _automation_plan p JOIN return_request_line l ON l.rl_request_number = CASE WHEN p.key ~ '^[0-9]+$' THEN p.key::int END AND l.rl_state = 'received'
    WHERE p.kind = 'request:multi_line' GROUP BY p.key HAVING count(*) NOT BETWEEN 2 AND 3")" = ""
expect "one care request is one task: a multi-line request whose lines all go to care" "$(q "SELECT count(*) FROM _automation_plan m
    WHERE m.kind = 'request:multi_line' AND NOT EXISTS (SELECT 1 FROM return_request_line l LEFT JOIN _automation_plan d ON CASE WHEN d.key ~ '^[0-9]+$' THEN d.key::int END = l.rl_line_id AND d.kind = 'decide:care'
                                                         WHERE l.rl_request_number = CASE WHEN m.key ~ '^[0-9]+$' THEN m.key::int END AND d.key IS NULL)")" -eq 1
expect "the abuse customers' 12-month return share was pushed over $(param abuse_share) by closed requests" "$(q "SELECT count(DISTINCT r.rr_customer_sk) FROM _automation_plan p
    JOIN return_request_hdr r ON r.rr_request_number = CASE WHEN p.key ~ '^[0-9]+$' THEN p.key::int END WHERE p.kind = 'request:abuse_history'")" -eq 3

# ── H-2: the lines decide_return already decided — states, ways, documents (monitor_inbound / settle) ──────────
expect "inbound plants are awaiting_goods with a return-expected way" "$(q "SELECT count(*) FROM _automation_plan p JOIN return_request_line l ON l.rl_line_id = CASE WHEN p.key ~ '^[0-9]+$' THEN p.key::int END
    WHERE p.kind LIKE 'inbound:%' AND l.rl_state = 'awaiting_goods' AND l.rl_way IN ('exchange', 'refund_after_return')")" -eq 17
expect "nothing arrived for the silent / remind / expired ones" "$(q "SELECT count(*) FROM _automation_plan p JOIN return_receipt r ON r.rc_line_id = CASE WHEN p.key ~ '^[0-9]+$' THEN p.key::int END
    WHERE p.kind IN ('inbound:none', 'inbound:remind', 'inbound:expired')")" -eq 0
expect "complete = received in full, in good condition" "$(q "SELECT count(*) FROM _automation_plan p JOIN return_request_line l ON l.rl_line_id = CASE WHEN p.key ~ '^[0-9]+$' THEN p.key::int END
    WHERE p.kind = 'inbound:complete' AND (SELECT coalesce(sum(rc_quantity) FILTER (WHERE rc_condition = 'ok'), 0) FROM return_receipt WHERE rc_line_id = l.rl_line_id) >= l.rl_quantity
      AND NOT EXISTS (SELECT 1 FROM return_receipt WHERE rc_line_id = l.rl_line_id AND rc_condition <> 'ok')")" -eq 3
expect "damaged = something bad or short" "$(q "SELECT count(*) FROM _automation_plan p JOIN return_request_line l ON l.rl_line_id = CASE WHEN p.key ~ '^[0-9]+$' THEN p.key::int END
    CROSS JOIN LATERAL (SELECT coalesce(sum(rc_quantity) FILTER (WHERE rc_condition = 'ok'), 0) ok, coalesce(sum(rc_quantity) FILTER (WHERE rc_condition <> 'ok'), 0) bad
                          FROM return_receipt WHERE rc_line_id = l.rl_line_id) r
    WHERE p.kind = 'inbound:damaged' AND (r.bad > 0 OR (r.ok > 0 AND r.ok < l.rl_quantity))")" -eq 2
expect "settle plants are settling / goods_received" "$(q "SELECT count(*) FROM _automation_plan p JOIN return_request_line l ON l.rl_line_id = CASE WHEN p.key ~ '^[0-9]+$' THEN p.key::int END
    WHERE p.kind LIKE 'settle:%' AND l.rl_state IN ('settling', 'goods_received')")" -eq 10
expect "paid: a credit note and its payment, refund ways" "$(q "SELECT count(*) FROM _automation_plan p JOIN return_request_line l ON l.rl_line_id = CASE WHEN p.key ~ '^[0-9]+$' THEN p.key::int END
    JOIN credit_note c ON c.cn_line_id = l.rl_line_id JOIN refund_payment r ON r.rp_credit_note_id = c.cn_credit_note_id
    WHERE p.kind = 'settle:paid' AND l.rl_way IN ('refund_no_return', 'refund_after_return')")" -eq 3
expect "unpaid: a credit note, no payment, issued $(( $(param settlement) + 7 )) working days ago (7 late)" "$(q "SELECT count(*) FROM _automation_plan p JOIN return_request_line l ON l.rl_line_id = CASE WHEN p.key ~ '^[0-9]+$' THEN p.key::int END
    JOIN credit_note c ON c.cn_line_id = l.rl_line_id
    WHERE p.kind = 'settle:unpaid' AND l.rl_way IN ('refund_no_return', 'refund_after_return')
      AND NOT EXISTS (SELECT 1 FROM refund_payment WHERE rp_credit_note_id = c.cn_credit_note_id)
      AND (SELECT count(*) FROM date_dim WHERE d_working_day AND d_date > c.cn_issued_date AND d_date <= DATE '$A') = $(( $(param settlement) + 7 ))")" -eq 3
expect "shipped: a shipment, replacement ways" "$(q "SELECT count(*) FROM _automation_plan p JOIN return_request_line l ON l.rl_line_id = CASE WHEN p.key ~ '^[0-9]+$' THEN p.key::int END
    JOIN replacement_shipment s ON s.rs_line_id = l.rl_line_id WHERE p.kind = 'settle:shipped' AND l.rl_way IN ('replacement_no_return', 'exchange')")" -eq 2
expect "missing: no shipment, replacement ways" "$(q "SELECT count(*) FROM _automation_plan p JOIN return_request_line l ON l.rl_line_id = CASE WHEN p.key ~ '^[0-9]+$' THEN p.key::int END
    WHERE p.kind = 'settle:missing' AND l.rl_way IN ('replacement_no_return', 'exchange') AND NOT EXISTS (SELECT 1 FROM replacement_shipment WHERE rs_line_id = l.rl_line_id)")" -eq 2
expect "no other line is in flight (received / awaiting / settling / goods_received)" "$(q "SELECT count(*) FROM return_request_line l
    WHERE l.rl_state IN ('received', 'awaiting_goods', 'settling', 'goods_received')
      AND NOT EXISTS (SELECT 1 FROM _automation_plan p WHERE p.kind ~ '^(decide|inbound|settle):' AND CASE WHEN p.key ~ '^[0-9]+$' THEN p.key::int END = l.rl_line_id)")" -eq 0

# ── H-3, H-5 ───────────────────────────────────────────────────────────────────────────────────────────────────
expect "H-3's cover rule finds exactly the planted reorder pairs" "$(probe_reorder "$S" "$A" | digest)" = \
  "$(q "SELECT key FROM _automation_plan WHERE kind = 'reorder:propose' ORDER BY key" | digest)"
expect "win-back: the mailed customers were mailed $(param winback_mail_window) days or less before as_of" "$(q "SELECT count(*) FROM winback_mail w JOIN _automation_plan p ON CASE WHEN p.key ~ '^[0-9]+$' THEN p.key::int END = w.wm_customer_sk AND p.kind = 'winback:mailed'
    WHERE w.wm_mailed_at::date > DATE '$A' - $(param winback_mail_window)")" -eq 10
expect "win-back: the list = customers with >= 2 orders in months -18..-6 and none since, minus the mailed" "$(q "SELECT key FROM _automation_plan WHERE kind = 'winback:list' ORDER BY CASE WHEN key ~ '^[0-9]+$' THEN key::int END" | digest)" = \
  "$(q "SELECT so_customer_sk FROM sales_order GROUP BY 1
         HAVING count(*) FILTER (WHERE so_placed_date >= DATE '$A' - interval '18 months' AND so_placed_date < DATE '$A' - interval '6 months') >= 2
            AND count(*) FILTER (WHERE so_placed_date >= DATE '$A' - interval '6 months') = 0
         EXCEPT SELECT wm_customer_sk FROM winback_mail ORDER BY 1" | digest)"
expect "win-back: premium = the top two income bands" "$(q "SELECT count(*) FROM _automation_plan p JOIN customer c ON c.c_customer_sk = CASE WHEN p.key ~ '^[0-9]+$' THEN p.key::int END
    LEFT JOIN household_demographics hd ON hd.hd_demo_sk = c.c_current_hdemo_sk
    WHERE p.kind = 'winback:list' AND p.expected_route IS DISTINCT FROM
          CASE WHEN hd.hd_income_band_sk IN (SELECT ib_income_band_sk FROM income_band ORDER BY ib_lower_bound DESC LIMIT 2) THEN 'premium' ELSE 'standard' END")" -eq 0
expect "win-back: the list is not empty" "$(n_kind winback:list)" -gt 0

drop_scratch "$S"
finish
