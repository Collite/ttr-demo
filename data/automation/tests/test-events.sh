#!/usr/bin/env bash
# AU-hartland P1·S1.3 T1 — the demo day's event timeline (contracts §6): `_automation_events` is monotone (seq in
# time order), every key exists in the world as its kind says (an open order placed; a received line; a receipt /
# a credit note, payment or shipment of a planted line on that day), nothing is after the demo day, a demo-speed
# subset is flagged, and events/<world>.csv is the table.   test-events.sh <ctx> <db> [pod]
set -uo pipefail
CTX="${1:?usage: test-events.sh <ctx> <db> [pod]}"; SRC="${2:?db}"; POD="${3:-hartland-pg-1}"; NS="${EXTEND_NS:-data}"
source "$(dirname "$0")/lib-test.sh"
S="${SRC}_au_events"
q() { pgq "$S" "$1"; }

echo "== events, on a scratch copy of $SRC ($S)"
scratch_copy "$SRC" "$S"
run_automation "$S"; rc=$?
expect "the build exits 0" "$rc" -eq 0
A=$(as_of_of "$S")
local_day() { echo "(($1) AT TIME ZONE 'Europe/Prague')::date"; }

expect "seq runs 1..n" "$(q "SELECT count(*) = max(seq) AND min(seq) = 1 FROM _automation_events")" = t
expect "seq follows time (then kind, then key)" "$(q "SELECT count(*) FROM (SELECT seq, at, lag(at) OVER (ORDER BY seq) prev FROM _automation_events) z WHERE at < prev")" -eq 0
expect "four kinds, no other" "$(q "SELECT string_agg(DISTINCT kind, ',' ORDER BY kind) FROM _automation_events")" = \
  "line_received,order_placed,receipt_posted,settlement_posted"
expect "nothing after the demo day" "$(q "SELECT count(*) FROM _automation_events WHERE $(local_day at) > DATE '$A'")" -eq 0

expect "order_placed: every open order, once, on its placement day" "$(q "SELECT count(*) FROM _automation_events e
    JOIN sales_order o ON o.so_order_number = (e.payload->>'order_number')::int AND o.so_state IN ('placed', 'held') AND $(local_day e.at) = o.so_placed_date
   WHERE e.kind = 'order_placed'")" -eq "$(q "SELECT count(*) FROM sales_order WHERE so_state IN ('placed', 'held')")"
expect "order_placed: no other" "$(q "SELECT count(*) FROM _automation_events WHERE kind = 'order_placed'")" -eq "$(q "SELECT count(*) FROM sales_order WHERE so_state IN ('placed', 'held')")"
expect "line_received: every received line, once, on its request day" "$(q "SELECT count(DISTINCT l.rl_line_id) FROM _automation_events e
    JOIN return_request_line l ON l.rl_line_id = (e.payload->>'line_id')::int AND l.rl_state = 'received'
    JOIN return_request_hdr h ON h.rr_request_number = l.rl_request_number AND h.rr_requested_date = $(local_day e.at)
   WHERE e.kind = 'line_received'")" -eq 40
expect "line_received: no other" "$(q "SELECT count(*) FROM _automation_events WHERE kind = 'line_received'")" -eq 40
expect "receipt_posted: a receipt of that line on that day" "$(q "SELECT count(*) FROM _automation_events e WHERE e.kind = 'receipt_posted'
    AND NOT EXISTS (SELECT 1 FROM return_receipt r WHERE r.rc_line_id = (e.payload->>'line_id')::int AND r.rc_received_date = $(local_day e.at))")" -eq 0
expect "settlement_posted: a credit note, payment or shipment of that line on that day" "$(q "SELECT count(*) FROM _automation_events e WHERE e.kind = 'settlement_posted'
    AND NOT EXISTS (SELECT 1 FROM credit_note c WHERE c.cn_line_id = (e.payload->>'line_id')::int AND c.cn_issued_date = $(local_day e.at))
    AND NOT EXISTS (SELECT 1 FROM credit_note c JOIN refund_payment p ON p.rp_credit_note_id = c.cn_credit_note_id
                     WHERE c.cn_line_id = (e.payload->>'line_id')::int AND p.rp_paid_date = $(local_day e.at))
    AND NOT EXISTS (SELECT 1 FROM replacement_shipment s WHERE s.rs_line_id = (e.payload->>'line_id')::int AND s.rs_shipped_date = $(local_day e.at))")" -eq 0
expect "documents are posted for the in-flight (planted) lines only" "$(q "SELECT count(*) FROM _automation_events e WHERE e.kind IN ('receipt_posted', 'settlement_posted')
    AND (e.payload->>'line_id') NOT IN (SELECT key FROM _automation_plan WHERE kind ~ '^(inbound|settle):')")" -eq 0
expect "every planted document is posted (receipts: today's five + the settle lines')" "$(q "SELECT count(*) FROM _automation_events WHERE kind = 'receipt_posted'")" -eq \
  "$(q "SELECT count(*) FROM (SELECT DISTINCT rc_line_id, rc_received_date FROM return_receipt WHERE rc_line_id::text IN (SELECT key FROM _automation_plan WHERE kind ~ '^(inbound|settle):')) z")"
expect "a payload names its key, nothing else" "$(q "SELECT count(*) FROM _automation_events WHERE
    NOT (kind = 'order_placed' AND payload ?& ARRAY['order_number'] AND (SELECT count(*) FROM jsonb_object_keys(payload)) = 1)
    AND NOT (kind <> 'order_placed' AND payload ?& ARRAY['line_id'] AND (SELECT count(*) FROM jsonb_object_keys(payload)) = 1)")" -eq 0
expect "the demo-speed subset: $(conf events_demo) events, all on the demo day" "$(q "SELECT count(*) || ':' || count(*) FILTER (WHERE $(local_day at) = DATE '$A') FROM _automation_events WHERE demo")" = \
  "$(conf events_demo):$(conf events_demo)"
expect "the demo subset posts documents (the moments the runbook replays)" "$(q "SELECT count(*) FROM _automation_events WHERE demo AND kind IN ('receipt_posted', 'settlement_posted')")" -gt 0

F="$(out_of "$S")/events/us.csv"
expect "events/us.csv: the seed header" "$(head -1 "$F" 2>/dev/null)" = "seq,kind,at,payload,demo"
expect "events/us.csv: a row per event" "$(( $(wc -l < "$F") - 1 ))" -eq "$(q "SELECT count(*) FROM _automation_events")"

drop_scratch "$S"
finish
