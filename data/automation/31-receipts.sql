-- AU-hartland P1 · S1.2 — the returned goods received (README.md "Returns"): one receipt per condition per line,
-- from the dates and quantities 30-returns.sql set — every closed line whose way expects the goods back (in full,
-- in good condition), the settle plants that were returned, and today's five (complete; damaged; short).
INSERT INTO return_receipt (rc_receipt_id, rc_line_id, rc_received_date, rc_item_sk, rc_quantity, rc_condition)
SELECT row_number() OVER (ORDER BY r.line_id, r.condition), r.line_id, r.rc_date, r.item, r.quantity, r.condition
  FROM (SELECT line_id, rc_date, item, rc_ok AS quantity, 'ok' AS condition FROM _au_rl WHERE rc_date IS NOT NULL AND rc_ok > 0
        UNION ALL
        SELECT line_id, rc_date, item, rc_bad, rc_bad_condition FROM _au_rl WHERE rc_date IS NOT NULL AND rc_bad > 0) r
 ORDER BY r.line_id, r.condition;

CREATE INDEX IF NOT EXISTS ix_return_receipt_line ON return_receipt (rc_line_id);   -- 17 §4.2 `receipts`

INSERT INTO _automation_meta (step, as_of, rows) SELECT '31-receipts', :'as_of', count(*) FROM return_receipt;
