-- AU-hartland P1 · S1.1 — the extension's tables (contracts §1), the two column adds, the internals.
-- Piped by run-automation.sh into one transaction after automation.conf; the foreign keys come at the end of
-- the build (80-keys.sql), once the data is in.
--
-- Everything is created AS THE OWNER OF THE FACTS (the role owning web_sales — `hartland` on every cluster),
-- as views/channel_sales.sql runs: the owner may alter `customer` and `date_dim`, and its default privileges
-- give the world's `<db>_readonly` role SELECT on what it creates (granted below as well, as channel_sales does).
SET client_min_messages = warning;
SELECT tableowner AS au_owner FROM pg_tables WHERE schemaname = 'public' AND tablename = 'web_sales' \gset
SET ROLE :"au_owner";

-- ── the guard ─────────────────────────────────────────────────────────────────────────────────────────────────
-- One row per build step (rows written) and one `build` row at the end. run-automation.sh reads it first; this
-- is the backstop inside the transaction.
CREATE TABLE IF NOT EXISTS _automation_meta (
  step    text PRIMARY KEY,
  run_at  timestamptz NOT NULL DEFAULT now(),
  as_of   date NOT NULL,
  rows    bigint
);
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM _automation_meta WHERE step = 'build') THEN
    RAISE EXCEPTION 'automation_already_built: this world is built (as of %) — reset first',
      (SELECT as_of FROM _automation_meta WHERE step = 'build');
  END IF;
END $$;

-- ── H-1: orders, prices, invoices, outages ────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sales_order (
  so_order_number   integer PRIMARY KEY,
  so_channel        text NOT NULL,             -- web · marketplace
  so_customer_sk    integer NOT NULL,
  so_placed_date    date NOT NULL,
  so_delivered_date date,                      -- NULL until delivered
  so_warehouse_sk   integer NOT NULL,          -- the fulfilling distribution center
  so_value          numeric(12,2) NOT NULL,
  so_state          text NOT NULL,             -- placed · held · released · cancelled
  so_held_for       text,                      -- Sales · AR · both — NULL unless held
  so_placed_by      text NOT NULL
);
CREATE TABLE IF NOT EXISTS sales_line (
  sl_order_number    integer NOT NULL,
  sl_line_no         integer NOT NULL,
  sl_item_sk         integer NOT NULL,
  sl_quantity        integer NOT NULL,
  sl_unit_price      numeric(12,2) NOT NULL,
  sl_ext_sales_price numeric(12,2) NOT NULL,
  sl_warehouse_sk    integer NOT NULL,
  sl_sold_date       date NOT NULL,
  sl_customer_sk     integer NOT NULL,
  sl_channel         text NOT NULL,
  PRIMARY KEY (sl_order_number, sl_line_no)
);
CREATE TABLE IF NOT EXISTS price_list (
  pl_item_sk    integer NOT NULL,
  pl_channel    text NOT NULL,
  pl_valid_from date NOT NULL,
  pl_price      numeric(12,2) NOT NULL,
  pl_valid_to   date,                          -- NULL = open-ended
  PRIMARY KEY (pl_item_sk, pl_channel, pl_valid_from)
);
CREATE TABLE IF NOT EXISTS customer_price (
  cp_item_sk     integer NOT NULL,
  cp_customer_sk integer NOT NULL,
  cp_valid_from  date NOT NULL,
  cp_price       numeric(12,2) NOT NULL,
  cp_valid_to    date,
  PRIMARY KEY (cp_item_sk, cp_customer_sk, cp_valid_from)
);
CREATE TABLE IF NOT EXISTS invoice (
  inv_invoice_id   integer PRIMARY KEY,
  inv_customer_sk  integer NOT NULL,
  inv_order_number integer NOT NULL,
  inv_issued       date NOT NULL,
  inv_due          date NOT NULL,
  inv_amount       numeric(12,2) NOT NULL,
  inv_paid         numeric(12,2) NOT NULL,
  inv_status       text NOT NULL               -- open · paid
);
CREATE TABLE IF NOT EXISTS warehouse_outage (
  wo_warehouse_sk integer NOT NULL,
  wo_from_date    date NOT NULL,
  wo_to_date      date NOT NULL,               -- inclusive
  wo_reason       text NOT NULL,
  PRIMARY KEY (wo_warehouse_sk, wo_from_date)
);

-- ── H-2: the return-request flow (filled at S1.2) ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS return_request_hdr (
  rr_request_number integer PRIMARY KEY,
  rr_customer_sk    integer NOT NULL,
  rr_order_number   integer NOT NULL,
  rr_channel        text NOT NULL,
  rr_requested_date date NOT NULL
);
CREATE TABLE IF NOT EXISTS return_request_line (
  rl_line_id              integer PRIMARY KEY,
  rl_request_number       integer NOT NULL,
  rl_line_no              integer NOT NULL,
  rl_item_sk              integer NOT NULL,
  rl_quantity             integer NOT NULL,
  rl_unit_price           numeric(12,2) NOT NULL,
  rl_reason               text NOT NULL,       -- damaged · did_not_arrive · wrong_size · other
  rl_requested_resolution text NOT NULL,       -- refund · exchange · replacement
  rl_requested_variant_sk integer,             -- NULL unless an exchange names a variant
  rl_state                text NOT NULL,       -- received · rejected · settling · awaiting_goods · goods_received · not_returned · closed
  rl_way                  text,                -- NULL until decided: the decide_return route taken
  rl_customer_sk          integer NOT NULL     -- the request's customer, denormalized (D-127)
);
CREATE TABLE IF NOT EXISTS return_receipt (
  rc_receipt_id    integer PRIMARY KEY,
  rc_line_id       integer NOT NULL,
  rc_received_date date NOT NULL,
  rc_item_sk       integer NOT NULL,
  rc_quantity      integer NOT NULL,
  rc_condition     text NOT NULL               -- ok · damaged · missing
);
CREATE TABLE IF NOT EXISTS credit_note (
  cn_credit_note_id integer PRIMARY KEY,
  cn_line_id        integer NOT NULL,
  cn_customer_sk    integer NOT NULL,
  cn_issued_date    date NOT NULL,
  cn_amount         numeric(12,2) NOT NULL,
  cn_status         text NOT NULL              -- issued · paid
);
CREATE TABLE IF NOT EXISTS refund_payment (
  rp_payment_id     integer PRIMARY KEY,
  rp_credit_note_id integer NOT NULL,
  rp_paid_date      date NOT NULL,
  rp_amount         numeric(12,2) NOT NULL
);
CREATE TABLE IF NOT EXISTS replacement_shipment (
  rs_shipment_id  integer PRIMARY KEY,
  rs_line_id      integer NOT NULL,
  rs_item_sk      integer NOT NULL,
  rs_quantity     integer NOT NULL,
  rs_shipped_date date NOT NULL
);

-- ── H-3 / H-5 write-back: empty at build, written by the recipes (`writable:`, D-79) ─────────────────────────
CREATE TABLE IF NOT EXISTS reorder_proposal (
  rp_proposal_id   bigserial PRIMARY KEY,
  rp_run           text NOT NULL,
  rp_item_sk       integer NOT NULL,
  rp_warehouse_sk  integer NOT NULL,
  rp_on_hand       integer,
  rp_weekly_demand numeric(12,2),
  rp_proposed_qty  integer NOT NULL,
  rp_state         text NOT NULL               -- proposed · approved · rejected · started
);
CREATE TABLE IF NOT EXISTS winback_mail (
  wm_customer_sk integer NOT NULL,
  wm_quarter     text NOT NULL,                -- e.g. 2026-Q4
  wm_offer       text NOT NULL,                -- premium · standard
  wm_run         text NOT NULL,
  wm_mailed_at   timestamptz NOT NULL,
  PRIMARY KEY (wm_customer_sk, wm_quarter)
);

-- ── the column adds (D-82, D-83): kept by a reset, only emptied — the model maps them ────────────────────────
ALTER TABLE customer ADD COLUMN IF NOT EXISTS c_center_sk integer;      -- 24-centers.sql
ALTER TABLE date_dim ADD COLUMN IF NOT EXISTS d_working_day boolean;    -- 25-calendar.sql

-- ── internals (never modelled) ────────────────────────────────────────────────────────────────────────────────
-- What the world looked like when it was built (per fact: last date, rows).
CREATE TABLE IF NOT EXISTS _automation_base (
  fact      text PRIMARY KEY,
  last_date date,
  row_count bigint NOT NULL
);
-- Every planted case (S1.2) and the route the recipe must take on it; 50-expected.sql renders it (S1.3).
CREATE TABLE IF NOT EXISTS _automation_plan (
  kind           text NOT NULL,
  key            text NOT NULL,
  note           text,
  expected_route text,
  PRIMARY KEY (kind, key)
);
-- The demo day's event timeline (S1.3, contracts §6).
CREATE TABLE IF NOT EXISTS _automation_events (
  seq     integer PRIMARY KEY,
  kind    text NOT NULL,
  at      timestamptz NOT NULL,
  payload jsonb NOT NULL,
  demo    boolean NOT NULL DEFAULT false
);
-- Every BASE row the build changes, journaled before it changes it (the first old value wins: ON CONFLICT DO
-- NOTHING), so reset.sql can give it back — a base row has no "copy" marker to find it by (the data/seed S2
-- lesson: an edit you cannot find again is not undoable). `pk` is the row's key columns in key order; an
-- inserted row is journaled with col '*' and inserted = true (the reset deletes it).
CREATE TABLE IF NOT EXISTS _automation_undo (
  tbl       text NOT NULL,
  pk        integer[] NOT NULL,
  col       text NOT NULL,
  old_value text,
  inserted  boolean NOT NULL DEFAULT false,
  PRIMARY KEY (tbl, pk, col)
);

-- The world's read-only role reads the extension (not the internals).
DO $$
DECLARE t text;
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = current_database() || '_readonly') THEN
    FOREACH t IN ARRAY ARRAY['sales_order', 'sales_line', 'price_list', 'customer_price', 'invoice', 'warehouse_outage',
                             'return_request_hdr', 'return_request_line', 'return_receipt', 'credit_note', 'refund_payment',
                             'replacement_shipment', 'reorder_proposal', 'winback_mail'] LOOP
      EXECUTE format('GRANT SELECT ON public.%I TO %I', t, current_database() || '_readonly');
    END LOOP;
  END IF;
END $$;

INSERT INTO _automation_meta (step, as_of, rows) VALUES ('10-ddl', :'as_of', 0);
