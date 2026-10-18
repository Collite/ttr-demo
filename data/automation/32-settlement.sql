-- AU-hartland P1 · S1.2 — the settlement documents (README.md "Returns"), from the dates 30-returns.sql set: a
-- credit note for the line's value per refunded line (paid, or — the plants — issued and unpaid), its payment, and a
-- replacement shipment (the variant, for an exchange) per replaced line. The plants' gaps are documents NOT written.
INSERT INTO credit_note (cn_credit_note_id, cn_line_id, cn_customer_sk, cn_issued_date, cn_amount, cn_status)
SELECT row_number() OVER (ORDER BY line_id), line_id, customer, cn_date, round(quantity * unit_price, 2), cn_status
  FROM _au_rl WHERE cn_date IS NOT NULL ORDER BY line_id;

INSERT INTO refund_payment (rp_payment_id, rp_credit_note_id, rp_paid_date, rp_amount)
SELECT row_number() OVER (ORDER BY c.cn_credit_note_id), c.cn_credit_note_id, l.rp_date, c.cn_amount
  FROM credit_note c JOIN _au_rl l ON l.line_id = c.cn_line_id
 WHERE l.rp_date IS NOT NULL ORDER BY c.cn_credit_note_id;

INSERT INTO replacement_shipment (rs_shipment_id, rs_line_id, rs_item_sk, rs_quantity, rs_shipped_date)
SELECT row_number() OVER (ORDER BY line_id), line_id, rs_item, quantity, rs_date
  FROM _au_rl WHERE rs_date IS NOT NULL ORDER BY line_id;

-- 17 §4.3 `documents`: a line's credit note, its payment, its shipment
CREATE INDEX IF NOT EXISTS ix_credit_note_line ON credit_note (cn_line_id);
CREATE INDEX IF NOT EXISTS ix_refund_payment_credit_note ON refund_payment (rp_credit_note_id);
CREATE INDEX IF NOT EXISTS ix_replacement_shipment_line ON replacement_shipment (rs_line_id);

INSERT INTO _automation_meta (step, as_of, rows)
SELECT '32-settlement', :'as_of', (SELECT count(*) FROM credit_note) + (SELECT count(*) FROM refund_payment) + (SELECT count(*) FROM replacement_shipment);
