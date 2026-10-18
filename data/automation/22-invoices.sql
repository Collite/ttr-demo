-- AU-hartland P1 · S1.1 — one invoice per released order (README.md "Invoices"): issued when the order was
-- delivered (when it was placed, for one still on its way), due :payment_days later, its value, paid in full.
-- An open order has no invoice yet. S1.2 re-opens the planted customers' latest invoices (overdue, `hold_ar`).
INSERT INTO invoice (inv_invoice_id, inv_customer_sk, inv_order_number, inv_issued, inv_due, inv_amount, inv_paid, inv_status)
SELECT row_number() OVER (ORDER BY so_order_number), so_customer_sk, so_order_number,
       coalesce(so_delivered_date, so_placed_date), coalesce(so_delivered_date, so_placed_date) + :payment_days,
       so_value, so_value, 'paid'
  FROM sales_order
 WHERE so_state = 'released'
 ORDER BY so_order_number;

CREATE INDEX IF NOT EXISTS ix_invoice_customer ON invoice (inv_customer_sk);   -- 17 §3 `overdue`: a customer's invoices
ANALYZE invoice;

INSERT INTO _automation_meta (step, as_of, rows) SELECT '22-invoices', :'as_of', count(*) FROM invoice;
