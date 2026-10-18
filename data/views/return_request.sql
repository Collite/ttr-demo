-- return_request — the H-2 request header with its state DERIVED from its lines (AU, D-84; one view, both worlds).
--
-- Why a view: the key of the return flow is the LINE (D-84) — the recipes decide, settle and close lines, never
-- requests — so a stored header state would be a second copy of the truth that something has to keep in step.
-- The view says it once: `received` while any line is received (or none has arrived yet), `closed` when every
-- line is rejected, not_returned or closed, `decided` in between. The entity `return_request` reads it
-- (model/db/returns-flow.ttrm, whose `definitionSql` this is, verbatim — change both or neither).
--
-- Idempotent (CREATE OR REPLACE; the GRANT is a no-op when already held). data/automation/run-automation.sh
-- runs it inside the build as the owner of the tables; by hand, as that owner (`hartland`):
--     psql -d hartland_us -f data/views/return_request.sql
-- Column order is load-bearing: CREATE OR REPLACE VIEW may only APPEND a column.
CREATE OR REPLACE VIEW public.return_request AS
        SELECT h.rr_request_number, h.rr_customer_sk, h.rr_order_number, h.rr_channel, h.rr_requested_date,
               CASE WHEN COUNT(l.rl_line_id) = 0 OR BOOL_OR(l.rl_state = 'received') THEN 'received'
                    WHEN BOOL_AND(l.rl_state IN ('rejected', 'not_returned', 'closed')) THEN 'closed'
                    ELSE 'decided'
               END::text AS rr_state
          FROM return_request_hdr h
          LEFT JOIN return_request_line l ON l.rl_request_number = h.rr_request_number
         GROUP BY h.rr_request_number, h.rr_customer_sk, h.rr_order_number, h.rr_channel, h.rr_requested_date;

COMMENT ON VIEW public.return_request IS
  'Return requests with their state derived from the lines (received · decided · closed) — model: er.entity.return_request. Source: hartland data/views/return_request.sql';

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = current_database() || '_readonly') THEN
        EXECUTE format('GRANT SELECT ON public.return_request TO %I', current_database() || '_readonly');
    END IF;
END $$;
