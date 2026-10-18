-- document_flow — which document followed which in a return (AU H-2; one view, both worlds): order → request,
-- request → receipt, request → credit note, credit note → refund payment, request → replacement shipment.
-- Kinds are the entity names. Nothing stores the flow — every edge is a foreign key already in the documents —
-- so it is a view over them, read by the entity `document_flow` (model/db/returns-flow.ttrm, whose
-- `definitionSql` this is, verbatim — change both or neither).
--
-- Idempotent (CREATE OR REPLACE; the GRANT is a no-op when already held). data/automation/run-automation.sh
-- runs it inside the build as the owner of the tables; by hand, as that owner (`hartland`):
--     psql -d hartland_us -f data/views/document_flow.sql
-- Column order is load-bearing: CREATE OR REPLACE VIEW may only APPEND a column.
CREATE OR REPLACE VIEW public.document_flow AS
        SELECT 'order'::text AS df_pred_kind, rr_order_number AS df_pred_id,
               'return_request'::text AS df_succ_kind, rr_request_number AS df_succ_id
          FROM return_request_hdr
        UNION ALL
        SELECT 'return_request', l.rl_request_number, 'return_receipt', rc.rc_receipt_id
          FROM return_receipt rc JOIN return_request_line l ON l.rl_line_id = rc.rc_line_id
        UNION ALL
        SELECT 'return_request', l.rl_request_number, 'credit_note', cn.cn_credit_note_id
          FROM credit_note cn JOIN return_request_line l ON l.rl_line_id = cn.cn_line_id
        UNION ALL
        SELECT 'credit_note', rp_credit_note_id, 'refund_payment', rp_payment_id
          FROM refund_payment
        UNION ALL
        SELECT 'return_request', l.rl_request_number, 'replacement_shipment', rs.rs_shipment_id
          FROM replacement_shipment rs JOIN return_request_line l ON l.rl_line_id = rs.rs_line_id;

COMMENT ON VIEW public.document_flow IS
  'The document flow of a return (order → request → receipt / credit note → payment / replacement) — model: er.entity.document_flow. Source: hartland data/views/document_flow.sql';

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = current_database() || '_readonly') THEN
        EXECUTE format('GRANT SELECT ON public.document_flow TO %I', current_database() || '_readonly');
    END IF;
END $$;
