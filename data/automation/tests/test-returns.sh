#!/usr/bin/env bash
# AU-hartland P1·S1.2 T1 — the return-request flow (D-84, README.md "Returns"): requests and lines from the
# *_returns facts, mostly single-line; every document points at an existing line; history is settled (terminal
# states, a full document set per way, every date on or before as_of); the view derives the request's state.
# Works on a throwaway copy of <db>:   test-returns.sh <ctx> <db> [pod]
set -uo pipefail
CTX="${1:?usage: test-returns.sh <ctx> <db> [pod]}"; SRC="${2:?db}"; POD="${3:-hartland-pg-1}"; NS="${EXTEND_NS:-data}"
source "$(dirname "$0")/lib-test.sh"
S="${SRC}_au_returns"
q() { pgq "$S" "$1"; }

echo "== returns, on a scratch copy of $SRC ($S)"
scratch_copy "$SRC" "$S"
run_automation "$S"; rc=$?
expect "the build exits 0" "$rc" -eq 0
A=$(as_of_of "$S"); off=$(conf web_order_offset)

# ── requests and lines ──────────────────────────────────────────────────────────────────────────────────────────
expect "some requests" "$(q "SELECT count(*) FROM return_request_hdr")" -gt 0
expect "every request has a line" "$(q "SELECT count(*) FROM return_request_hdr h WHERE NOT EXISTS (SELECT 1 FROM return_request_line WHERE rl_request_number = h.rr_request_number)")" -eq 0
expect_between "single-line requests (%)" "$(q "SELECT round(100.0 * count(*) FILTER (WHERE n = 1) / count(*), 1) FROM (SELECT count(*) n FROM return_request_line GROUP BY rl_request_number) z")" 90 100
# A line comes from a return fact — a dated web / marketplace return of an item on a kept, DELIVERED order, requested
# on the later of its return date and the delivery, on or before as_of — unless the plan added it (a multi-line
# request's extra lines, the abuse customers' closed history: kind request:added_line).
RET="SELECT wr_order_number + $off o, wr_item_sk i, d.d_date r FROM web_returns JOIN date_dim d ON d.d_date_sk = wr_returned_date_sk
     UNION ALL SELECT cr_order_number, cr_item_sk, d.d_date FROM catalog_returns JOIN date_dim d ON d.d_date_sk = cr_returned_date_sk"
added=$(q "SELECT count(*) FROM _automation_plan WHERE kind = 'request:added_line'")
expect "lines = the returns of sold, delivered order lines + the lines the plan added ($added)" "$(q "SELECT count(*) FROM return_request_line")" -eq \
  "$(( $(q "SELECT count(*) FROM ($RET) r JOIN sales_line s ON s.sl_order_number = r.o AND s.sl_item_sk = r.i
             JOIN sales_order o ON o.so_order_number = r.o WHERE greatest(r.r, o.so_delivered_date) <= DATE '$A'") + added ))"
expect "some lines were added by the plan" "$added" -gt 0
expect "a line carries its request's customer" "$(q "SELECT count(*) FROM return_request_line l JOIN return_request_hdr h ON h.rr_request_number = l.rl_request_number WHERE l.rl_customer_sk <> h.rr_customer_sk")" -eq 0
expect "a request's customer is its order's (but the planted not-ours)" "$(q "SELECT count(*) FROM return_request_hdr h JOIN sales_order o ON o.so_order_number = h.rr_order_number
    WHERE h.rr_customer_sk <> o.so_customer_sk AND h.rr_request_number NOT IN (SELECT rl_request_number FROM return_request_line l JOIN _automation_plan p ON p.key::int = l.rl_line_id AND p.kind = 'decide:not_ours')")" -eq 0
expect "a line is priced as it was sold" "$(q "SELECT count(*) FROM return_request_line l JOIN return_request_hdr h ON h.rr_request_number = l.rl_request_number
    JOIN sales_line s ON s.sl_order_number = h.rr_order_number AND s.sl_item_sk = l.rl_item_sk WHERE s.sl_unit_price <> l.rl_unit_price")" -eq 0
expect "line numbers run 1..n per request" "$(q "SELECT count(*) FROM (SELECT rl_line_no, row_number() OVER (PARTITION BY rl_request_number ORDER BY rl_line_no) rn FROM return_request_line) z WHERE rl_line_no <> rn")" -eq 0
expect "reasons, resolutions, states are the contract's codes" "$(q "SELECT count(*) FROM return_request_line WHERE rl_reason NOT IN ('damaged', 'did_not_arrive', 'wrong_size', 'other')
    OR rl_requested_resolution NOT IN ('refund', 'exchange', 'replacement')
    OR rl_state NOT IN ('received', 'rejected', 'settling', 'awaiting_goods', 'goods_received', 'not_returned', 'closed')")" -eq 0
expect "a variant is another item of the same class, named only for an exchange" "$(q "SELECT count(*) FROM return_request_line l LEFT JOIN item a ON a.i_item_sk = l.rl_item_sk LEFT JOIN item b ON b.i_item_sk = l.rl_requested_variant_sk
    WHERE l.rl_requested_variant_sk IS NOT NULL AND (l.rl_requested_resolution <> 'exchange' OR b.i_item_sk = a.i_item_sk OR btrim(b.i_class) <> btrim(a.i_class))")" -eq 0
expect "every reason code occurs" "$(q "SELECT count(DISTINCT rl_reason) FROM return_request_line")" -eq 4
expect_between "refund is requested for ~60 % of the lines (%)" "$(q "SELECT round(100.0 * count(*) FILTER (WHERE rl_requested_resolution = 'refund') / count(*), 1) FROM return_request_line")" 50 70

# ── history is settled ──────────────────────────────────────────────────────────────────────────────────────────
expect "a rejected line has no way, a closed one has one" "$(q "SELECT count(*) FROM return_request_line WHERE (rl_state = 'rejected' AND rl_way IS NOT NULL) OR (rl_state = 'closed' AND rl_way IS NULL)")" -eq 0
expect "closed with a return-expected way: received in full, in good condition" "$(q "SELECT count(*) FROM return_request_line l WHERE l.rl_state = 'closed' AND l.rl_way IN ('exchange', 'refund_after_return')
    AND coalesce((SELECT sum(rc_quantity) FROM return_receipt WHERE rc_line_id = l.rl_line_id AND rc_condition = 'ok'), 0) < l.rl_quantity")" -eq 0
expect "closed with a refund way: a paid credit note for the line's value, and its payment" "$(q "SELECT count(*) FROM return_request_line l WHERE l.rl_state = 'closed' AND l.rl_way IN ('refund_no_return', 'refund_after_return')
    AND NOT EXISTS (SELECT 1 FROM credit_note c JOIN refund_payment p ON p.rp_credit_note_id = c.cn_credit_note_id
                     WHERE c.cn_line_id = l.rl_line_id AND c.cn_status = 'paid' AND c.cn_amount = round(l.rl_quantity * l.rl_unit_price, 2) AND p.rp_amount = c.cn_amount)")" -eq 0
expect "closed with a replacement way: a shipment (the variant for an exchange)" "$(q "SELECT count(*) FROM return_request_line l WHERE l.rl_state = 'closed' AND l.rl_way IN ('replacement_no_return', 'exchange')
    AND NOT EXISTS (SELECT 1 FROM replacement_shipment s WHERE s.rs_line_id = l.rl_line_id AND s.rs_quantity = l.rl_quantity
                     AND s.rs_item_sk = CASE l.rl_way WHEN 'exchange' THEN l.rl_requested_variant_sk ELSE l.rl_item_sk END)")" -eq 0
expect "no document for a rejected line" "$(q "SELECT count(*) FROM return_request_line l WHERE l.rl_state = 'rejected' AND (
    EXISTS (SELECT 1 FROM return_receipt WHERE rc_line_id = l.rl_line_id) OR EXISTS (SELECT 1 FROM credit_note WHERE cn_line_id = l.rl_line_id)
 OR EXISTS (SELECT 1 FROM replacement_shipment WHERE rs_line_id = l.rl_line_id))")" -eq 0
expect "documents follow the request, in order, and none is after as_of" "$(q "SELECT count(*) FROM return_request_line l JOIN return_request_hdr h ON h.rr_request_number = l.rl_request_number
    LEFT JOIN return_receipt rc ON rc.rc_line_id = l.rl_line_id LEFT JOIN credit_note cn ON cn.cn_line_id = l.rl_line_id
    LEFT JOIN refund_payment rp ON rp.rp_credit_note_id = cn.cn_credit_note_id LEFT JOIN replacement_shipment rs ON rs.rs_line_id = l.rl_line_id
    WHERE rc.rc_received_date < h.rr_requested_date OR cn.cn_issued_date < h.rr_requested_date OR rs.rs_shipped_date < h.rr_requested_date
       OR rp.rp_paid_date < cn.cn_issued_date OR cn.cn_issued_date < rc.rc_received_date AND l.rl_way = 'refund_after_return'
       OR greatest(rc.rc_received_date, cn.cn_issued_date, rp.rp_paid_date, rs.rs_shipped_date) > DATE '$A'
       OR h.rr_requested_date > DATE '$A'")" -eq 0
expect "a request's order was delivered before it was requested (but the planted not-ours)" "$(q "SELECT count(*) FROM return_request_hdr h JOIN sales_order o ON o.so_order_number = h.rr_order_number
    WHERE (o.so_delivered_date IS NULL OR o.so_delivered_date > h.rr_requested_date) AND o.so_customer_sk = h.rr_customer_sk")" -eq 0

# ── the derived request state (D-84), on three requests picked by their plan ───────────────────────────────────
pick() { q "SELECT l.rl_request_number FROM _automation_plan p JOIN return_request_line l ON l.rl_line_id = p.key::int WHERE p.kind = '$1' ORDER BY 1 LIMIT 1"; }
expect "a request with a received line is received" "$(q "SELECT rr_state FROM return_request WHERE rr_request_number = $(pick decide:refund_after_return)")" = received
expect "a request whose line awaits the goods is decided" "$(q "SELECT rr_state FROM return_request WHERE rr_request_number = $(pick inbound:none)")" = decided
expect "a settled request is closed" "$(q "SELECT rr_state FROM return_request WHERE rr_request_number = (SELECT min(rl_request_number) FROM return_request_line GROUP BY rl_request_number HAVING bool_and(rl_state = 'closed') ORDER BY 1 LIMIT 1)")" = closed
expect "the view has every request once" "$(q "SELECT count(*) FROM return_request")" -eq "$(q "SELECT count(*) FROM return_request_hdr")"
expect "document_flow: an edge per request, receipt, credit note, payment and shipment" "$(q "SELECT count(*) FROM document_flow")" -eq \
  "$(q "SELECT (SELECT count(*) FROM return_request_hdr) + (SELECT count(*) FROM return_receipt) + (SELECT count(*) FROM credit_note) + (SELECT count(*) FROM refund_payment) + (SELECT count(*) FROM replacement_shipment)")"

drop_scratch "$S"
finish
