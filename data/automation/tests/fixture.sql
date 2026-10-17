-- The data/automation test fixture — a small TPC-DS-shaped world: only the tables and columns the generator
-- reads, with the TPC-DS kit's keys, owned by `hartland` as the real worlds are. Deterministic (every value is a
-- hash of a stable key), so two loads are byte-identical. run-all.sh loads it into `au_fixture` (US) and copies
-- that into `au_fixture_cz` with the CZK marker.
--
-- The real worlds' shapes it reproduces ON PURPOSE, because the generator has to survive them:
--   * web and marketplace order numbers OVERLAP — TPC-DS numbers each channel from 1 (orders 1..3000 exist in both);
--   * NULLs in the nullable fact columns (~2–4 %: warehouse, sold date, bill customer, quantity + amount);
--   * one sold date and one bill customer per order, a per-line warehouse that is mostly the order's;
--   * dense weekly inventory (every item × warehouse every week) with NULL and zero quantities;
--   * returns that trail their sale, some with a NULL return date;
--   * `_extend_meta` / `_extend_base` — the runner refuses a world that was never extended.
-- And the demo day's material: a quarter of the orders in the 60 days before 2026-10-26 (the default as_of, the
-- Monday that ends the last extended week) — enough open orders and recent returns for every plant — and
-- "sleepers" (customers 361–390) who ordered only between 2025-05 and 2026-03: the win-back population of H-5.
-- Customers 391–400 never order. Household demographics carry the income band H-5's offer splits on.
\set ON_ERROR_STOP on
SET client_min_messages = warning;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'hartland') THEN CREATE ROLE hartland NOLOGIN; END IF;
END $$;
GRANT CREATE ON SCHEMA public TO hartland;    -- Postgres 15+: `public` is not writable by default
SET ROLE hartland;

CREATE FUNCTION pg_temp.h(text) RETURNS int LANGUAGE sql IMMUTABLE AS 'SELECT abs(hashtext($1))';

-- ── dimensions ─────────────────────────────────────────────────────────────────────────────────────────────
-- d_date_sk is a day number and d_week_seq a 7-day block from Tuesday 1900-01-02, as in TPC-DS.
CREATE TABLE date_dim (
  d_date_sk   integer PRIMARY KEY,
  d_date_id   char(16) NOT NULL,
  d_date      date,
  d_week_seq  integer,
  d_year      integer,
  d_day_name  char(9),
  d_holiday   char(1),
  d_weekend   char(1)
);
INSERT INTO date_dim
SELECT (d - DATE '1900-01-02') + 2415022, 'AAAAAAAA' || ((d - DATE '1900-01-02') + 2415022), d,
       (d - DATE '1900-01-02') / 7 + 1, extract(year FROM d)::int, to_char(d, 'FMDay'),
       CASE WHEN to_char(d, 'MM-DD') IN ('01-01', '07-04', '12-25') THEN 'Y' ELSE 'N' END,
       CASE WHEN extract(isodow FROM d) >= 6 THEN 'Y' ELSE 'N' END
FROM generate_series(DATE '2022-01-01', DATE '2027-12-31', interval '1 day') g(t), LATERAL (SELECT t::date AS d) x;

CREATE TABLE warehouse (
  w_warehouse_sk   integer PRIMARY KEY,
  w_warehouse_id   char(16) NOT NULL,
  w_warehouse_name varchar(20)
);
INSERT INTO warehouse SELECT n, 'WH' || n, 'Center ' || n FROM generate_series(1, 5) n;

-- 60 classes of 10 items: an exchange's variant is "another item of the same class" (S1.2). One item in six is
-- cheap (under 13), as plenty of TPC-DS prices are: the small-value refunds need some.
CREATE TABLE item (
  i_item_sk       integer PRIMARY KEY,
  i_item_id       char(16) NOT NULL,
  i_current_price numeric(7,2),
  i_class         char(50),
  i_category      char(50)
);
INSERT INTO item
SELECT n, 'ITEM' || n, CASE WHEN n % 6 = 0 THEN 2 + pg_temp.h('price:' || n) % 10 ELSE 5 + pg_temp.h('price:' || n) % 200 END + 0.99,  -- 1 in 6 cheap
       'class-' || lpad(((n - 1) / 10 + 1)::text, 2, '0'), 'category-' || ((n - 1) / 150 + 1)
FROM generate_series(1, 600) n;

CREATE TABLE income_band (
  ib_income_band_sk integer PRIMARY KEY,
  ib_lower_bound    integer,
  ib_upper_bound    integer
);
INSERT INTO income_band SELECT n, (n - 1) * 10000 + 1, n * 10000 FROM generate_series(1, 20) n;

CREATE TABLE household_demographics (
  hd_demo_sk        integer PRIMARY KEY,
  hd_income_band_sk integer
);
INSERT INTO household_demographics SELECT n, 1 + (n - 1) % 20 FROM generate_series(1, 200) n;

CREATE TABLE customer (
  c_customer_sk       integer PRIMARY KEY,
  c_customer_id       char(16) NOT NULL,
  c_current_hdemo_sk  integer,
  c_first_name        char(20),
  c_last_name         char(30)
);
INSERT INTO customer SELECT n, 'CUST' || n, 1 + pg_temp.h('hd:' || n) % 200, 'First' || n, 'Last' || n
FROM generate_series(1, 400) n;  -- 391–400 never order

CREATE TABLE reason (
  r_reason_sk   integer PRIMARY KEY,
  r_reason_id   char(16) NOT NULL,
  r_reason_desc char(100)
);
INSERT INTO reason SELECT n, 'REASON' || n, 'reason ' || n FROM generate_series(1, 35) n;

-- ── the orders (one sold date, one bill customer, one main warehouse per order) ───────────────────────────
CREATE TEMP TABLE fx_order AS
SELECT ch, n, sleeper,
       CASE WHEN sleeper THEN DATE '2025-05-01' + pg_temp.h(ch || ':d:' || n) % 330
            WHEN pg_temp.h(ch || ':r:' || n) % 4 = 0 THEN DATE '2026-10-26' - pg_temp.h(ch || ':d:' || n) % 60
            ELSE DATE '2024-01-01' + pg_temp.h(ch || ':d:' || n) % (DATE '2026-10-19' - DATE '2024-01-01' + 1)
       END AS sold,
       CASE WHEN sleeper THEN 361 + pg_temp.h(ch || ':c:' || n) % 30 ELSE 1 + pg_temp.h(ch || ':c:' || n) % 360 END AS cust,
       1 + pg_temp.h(ch || ':w:' || n) % 5 AS wh,
       1 + pg_temp.h(ch || ':l:' || n) % 6 AS nlines
FROM (SELECT 'web' AS ch, n FROM generate_series(1, 3000) n
      UNION ALL SELECT 'marketplace', n FROM generate_series(1, 3500) n) o,
     LATERAL (SELECT pg_temp.h(ch || ':s:' || n) % 20 = 0 AS sleeper) s;

CREATE TEMP TABLE fx_line AS
SELECT o.ch, o.n, j, o.sold, o.cust, o.wh,
       1 + (pg_temp.h(o.ch || ':i:' || o.n) + j * 37) % 600 AS item,    -- 37 ⟂ 600: distinct items in an order
       k.k
FROM fx_order o, generate_series(0, o.nlines - 1) j, LATERAL (SELECT o.ch || ':' || o.n || ':' || j AS k) k;

CREATE TEMP TABLE fx_sale AS
SELECT l.*,
       CASE WHEN pg_temp.h('nd:' || k) % 35 = 0 THEN NULL ELSE (l.sold - DATE '1900-01-02') + 2415022 END AS date_sk,
       CASE WHEN pg_temp.h('nc:' || k) % 50 = 0 THEN NULL ELSE l.cust END AS bill_customer,
       CASE WHEN pg_temp.h('nw:' || k) % 40 = 0 THEN NULL
            WHEN pg_temp.h('lw:' || k) % 10 < 8 THEN l.wh ELSE 1 + pg_temp.h('ow:' || k) % 5 END AS line_wh,
       CASE WHEN pg_temp.h('nq:' || k) % 90 = 0 THEN NULL ELSE 1 + pg_temp.h('q:' || k) % 100 END AS qty,
       round(i.i_current_price * (0.60 + pg_temp.h('p:' || k) % 41 / 100.0), 2) AS price
FROM fx_line l JOIN item i ON i.i_item_sk = l.item;

CREATE TABLE web_sales (
  ws_sold_date_sk     integer,
  ws_item_sk          integer NOT NULL,
  ws_bill_customer_sk integer,
  ws_warehouse_sk     integer,
  ws_order_number     integer NOT NULL,
  ws_quantity         integer,
  ws_sales_price      numeric(7,2),
  ws_ext_sales_price  numeric(7,2),
  PRIMARY KEY (ws_item_sk, ws_order_number)
);
INSERT INTO web_sales
SELECT date_sk, item, bill_customer, line_wh, n, qty, CASE WHEN qty IS NOT NULL THEN price END,
       CASE WHEN qty IS NOT NULL THEN round(price * qty, 2) END
FROM fx_sale WHERE ch = 'web' ORDER BY n, item;

CREATE TABLE catalog_sales (
  cs_sold_date_sk     integer,
  cs_item_sk          integer NOT NULL,
  cs_bill_customer_sk integer,
  cs_warehouse_sk     integer,
  cs_order_number     integer NOT NULL,
  cs_quantity         integer,
  cs_sales_price      numeric(7,2),
  cs_ext_sales_price  numeric(7,2),
  PRIMARY KEY (cs_item_sk, cs_order_number)
);
INSERT INTO catalog_sales
SELECT date_sk, item, bill_customer, line_wh, n, qty, CASE WHEN qty IS NOT NULL THEN price END,
       CASE WHEN qty IS NOT NULL THEN round(price * qty, 2) END
FROM fx_sale WHERE ch = 'marketplace' ORDER BY n, item;

-- ── returns: 1 line in 8 sold before 2026-10-21, 2–51 days after the sale, a few with no return date ──────
CREATE TEMP TABLE fx_return AS
SELECT s.ch, s.n, s.item, s.cust, s.line_wh,
       CASE WHEN pg_temp.h('rn:' || s.k) % 30 = 0 THEN NULL
            ELSE (s.sold + 2 + pg_temp.h('rd:' || s.k) % 50 - DATE '1900-01-02') + 2415022 END AS date_sk,
       1 + pg_temp.h('rq:' || s.k) % coalesce(s.qty, 1) AS rqty,
       1 + pg_temp.h('rr:' || s.k) % 35 AS reason,
       s.price
FROM fx_sale s
WHERE s.sold <= DATE '2026-10-20' AND pg_temp.h('ret:' || s.k) % 8 = 0
  AND s.sold + 2 + pg_temp.h('rd:' || s.k) % 50 <= DATE '2026-10-26';

CREATE TABLE web_returns (
  wr_returned_date_sk      integer,
  wr_item_sk               integer NOT NULL,
  wr_returning_customer_sk integer,
  wr_reason_sk             integer,
  wr_order_number          integer NOT NULL,
  wr_return_quantity       integer,
  wr_return_amt            numeric(7,2),
  PRIMARY KEY (wr_item_sk, wr_order_number)
);
INSERT INTO web_returns
SELECT date_sk, item, cust, reason, n, rqty, round(price * rqty, 2) FROM fx_return WHERE ch = 'web' ORDER BY n, item;

CREATE TABLE catalog_returns (
  cr_returned_date_sk      integer,
  cr_item_sk               integer NOT NULL,
  cr_returning_customer_sk integer,
  cr_reason_sk             integer,
  cr_warehouse_sk          integer,
  cr_order_number          integer NOT NULL,
  cr_return_quantity       integer,
  cr_return_amount         numeric(7,2),
  PRIMARY KEY (cr_item_sk, cr_order_number)
);
INSERT INTO catalog_returns
SELECT date_sk, item, cust, reason, line_wh, n, rqty, round(price * rqty, 2) FROM fx_return WHERE ch = 'marketplace' ORDER BY n, item;

-- ── inventory: every Monday of the extended year, every item at every warehouse (NULL 1 in 25, zero 1 in 33) ─
CREATE TABLE inventory (
  inv_date_sk          integer NOT NULL,
  inv_item_sk          integer NOT NULL,
  inv_warehouse_sk     integer NOT NULL,
  inv_quantity_on_hand integer,
  PRIMARY KEY (inv_date_sk, inv_item_sk, inv_warehouse_sk)
);
INSERT INTO inventory
SELECT d.d_date_sk, i, w,
       CASE WHEN pg_temp.h('in:' || d.d_date_sk || ':' || i || ':' || w) % 25 = 0 THEN NULL
            WHEN pg_temp.h('iz:' || d.d_date_sk || ':' || i || ':' || w) % 33 = 0 THEN 0
            ELSE pg_temp.h('iq:' || d.d_date_sk || ':' || i || ':' || w) % 1000 END
FROM date_dim d, generate_series(1, 600) i, generate_series(1, 5) w
WHERE d.d_date BETWEEN DATE '2025-12-29' AND DATE '2026-10-26' AND extract(isodow FROM d.d_date) = 1
ORDER BY 1, 2, 3;

-- ── the extension's bookkeeping, as data/extend/extend.sql leaves it ─────────────────────────────────────
CREATE TABLE _extend_base (
  fact        text PRIMARY KEY,
  base_end    date NOT NULL,
  recorded_at timestamptz NOT NULL DEFAULT '2026-10-11 00:00+00'
);
INSERT INTO _extend_base (fact, base_end) VALUES
  ('store_sales', '2026-01-02'), ('web_sales', '2026-01-02'), ('catalog_sales', '2026-01-08'), ('inventory', '2025-12-26');

CREATE TABLE _extend_meta (
  target_week_seq   int PRIMARY KEY,
  template_week_seq int NOT NULL,
  k                 int NOT NULL,
  applied_at        timestamptz NOT NULL DEFAULT '2026-10-11 00:00+00',
  rows              jsonb NOT NULL
);
INSERT INTO _extend_meta (target_week_seq, template_week_seq, k, rows)
SELECT w, w - 104, 2, '{}'::jsonb
FROM generate_series((SELECT d_week_seq FROM date_dim WHERE d_date = '2026-01-06'),
                     (SELECT d_week_seq FROM date_dim WHERE d_date = '2026-10-26')) w;

RESET ROLE;
