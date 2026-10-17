-- AU-hartland P1 — undo the automation extension of a world (run-reset.sh, ONE transaction; README.md "Reset").
--   1. every base row the build changed comes back from _automation_undo (an updated value is restored, an
--      inserted row deleted) — a base row carries no "copy" marker, so the journal is the only way back;
--   2. the extension's views, tables and internals are dropped, with fk_c_center;
--   3. the two added columns stay, emptied: the model maps them, and a served model must not lose a column.
-- A world that was never built resets to itself.
SET client_min_messages = warning;
SELECT tableowner AS au_owner FROM pg_tables WHERE schemaname = 'public' AND tablename = 'web_sales' \gset
SET ROLE :"au_owner";

DO $$
BEGIN
  IF to_regclass('public._automation_undo') IS NOT NULL THEN
    UPDATE inventory i SET inv_quantity_on_hand = u.old_value::integer
      FROM _automation_undo u
     WHERE u.tbl = 'inventory' AND u.col = 'inv_quantity_on_hand' AND NOT u.inserted
       AND i.inv_date_sk = u.pk[1] AND i.inv_item_sk = u.pk[2] AND i.inv_warehouse_sk = u.pk[3];
    DELETE FROM inventory i
     USING _automation_undo u
     WHERE u.tbl = 'inventory' AND u.inserted
       AND i.inv_date_sk = u.pk[1] AND i.inv_item_sk = u.pk[2] AND i.inv_warehouse_sk = u.pk[3];
    IF EXISTS (SELECT 1 FROM _automation_undo WHERE tbl <> 'inventory') THEN
      RAISE EXCEPTION 'automation_reset: _automation_undo journals a table this reset does not restore: %',
        (SELECT string_agg(DISTINCT tbl, ', ') FROM _automation_undo WHERE tbl <> 'inventory');
    END IF;
  END IF;
END $$;

ALTER TABLE customer DROP CONSTRAINT IF EXISTS fk_c_center;
DROP VIEW IF EXISTS document_flow, return_request;
DROP TABLE IF EXISTS refund_payment, credit_note, replacement_shipment, return_receipt, return_request_line,
                     return_request_hdr, invoice, sales_line, sales_order, price_list, customer_price,
                     warehouse_outage, reorder_proposal, winback_mail;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'customer' AND column_name = 'c_center_sk') THEN
    UPDATE customer SET c_center_sk = NULL WHERE c_center_sk IS NOT NULL;
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'date_dim' AND column_name = 'd_working_day') THEN
    UPDATE date_dim SET d_working_day = NULL WHERE d_working_day IS NOT NULL;
  END IF;
END $$;

DROP TABLE IF EXISTS _automation_expected, _automation_plan, _automation_events, _automation_undo, _automation_base, _automation_meta;
RESET ROLE;
