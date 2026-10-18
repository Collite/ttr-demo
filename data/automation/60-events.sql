-- AU-hartland P1 · S1.3 — the demo day's event timeline (contracts §6): what happens up to and on the demo day, as
-- the webhooks scripts/automation-events.py posts to the Server's HTTP connector. On the Prague clock:
--   order_placed       every open order, on its placement day (8–18 h) — H-1's release_on_placement opens on it;
--   line_received      every received return line, on its request day (9–17 h) — decide_on_request;
--   receipt_posted     every receipt of a line in flight (the planted inbound / settle lines), on its day (10–16 h);
--   settlement_posted  every credit note, payment and shipment of such a line, on its day (11–17 h).
-- History's documents are not events: those lines were settled before the platform ran. `seq` orders the timeline
-- by (time, kind, key); `demo` flags the ~15 events of the demo day the runbook replays live — its documents first.
INSERT INTO _automation_events (seq, kind, at, payload)
WITH planted AS (SELECT key FROM _automation_plan WHERE kind ~ '^(inbound|settle):'),
e AS (
  SELECT 'order_placed'::text AS kind, so_order_number AS k,
         (so_placed_date + time '08:00' + make_interval(mins => abs(hashtext('ev:order:' || so_order_number)) % 600)) AT TIME ZONE 'Europe/Prague' AS at,
         jsonb_build_object('order_number', so_order_number) AS payload
    FROM sales_order WHERE so_state IN ('placed', 'held')
  UNION ALL
  SELECT 'line_received', l.rl_line_id,
         (h.rr_requested_date + time '09:00' + make_interval(mins => abs(hashtext('ev:line:' || l.rl_line_id)) % 480)) AT TIME ZONE 'Europe/Prague',
         jsonb_build_object('line_id', l.rl_line_id)
    FROM return_request_line l JOIN return_request_hdr h ON h.rr_request_number = l.rl_request_number
   WHERE l.rl_state = 'received'
  UNION ALL
  SELECT 'receipt_posted', r.rc_line_id,
         (r.rc_received_date + time '10:00' + make_interval(mins => abs(hashtext('ev:receipt:' || r.rc_line_id)) % 360)) AT TIME ZONE 'Europe/Prague',
         jsonb_build_object('line_id', r.rc_line_id)
    FROM (SELECT DISTINCT rc_line_id, rc_received_date FROM return_receipt WHERE rc_line_id::text IN (SELECT key FROM planted)) r
  UNION ALL
  SELECT 'settlement_posted', d.line_id,
         (d.day + time '11:00' + make_interval(mins => abs(hashtext('ev:' || d.doc || ':' || d.line_id)) % 360)) AT TIME ZONE 'Europe/Prague',
         jsonb_build_object('line_id', d.line_id)
    FROM (SELECT cn_line_id AS line_id, cn_issued_date AS day, 'credit_note' AS doc FROM credit_note
          UNION ALL SELECT c.cn_line_id, p.rp_paid_date, 'payment' FROM refund_payment p JOIN credit_note c ON c.cn_credit_note_id = p.rp_credit_note_id
          UNION ALL SELECT rs_line_id, rs_shipped_date, 'shipment' FROM replacement_shipment) d
   WHERE d.line_id::text IN (SELECT key FROM planted)
)
SELECT row_number() OVER (ORDER BY at, kind, k), kind, at, payload FROM e;

UPDATE _automation_events SET demo = true
 WHERE seq IN (SELECT seq FROM _automation_events
                WHERE (at AT TIME ZONE 'Europe/Prague')::date = :'as_of'::date
                ORDER BY kind IN ('receipt_posted', 'settlement_posted') DESC, at DESC, seq DESC
                LIMIT :events_demo);

INSERT INTO _automation_meta (step, as_of, rows) SELECT '60-events', :'as_of', count(*) FROM _automation_events;
