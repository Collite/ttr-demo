-- AU-hartland P1 · S1.1 — `sales_line` and its `sales_order` headers from web_sales ∪ catalog_sales (D-81;
-- README.md "Orders"). Every order written here is history, state `released`; 21-pricing.sql opens the demo
-- day's orders once the price list exists.

-- Every web and marketplace line, the web order number moved past the marketplace ones (automation.conf
-- `web_order_offset`: TPC-DS numbers both channels from 1).
CREATE TEMP TABLE _au_fact ON COMMIT DROP AS
SELECT 'web'::text AS channel, ws_order_number + :web_order_offset AS order_number, ws_item_sk AS item_sk,
       ws_quantity AS quantity, ws_ext_sales_price AS ext_sales_price, ws_warehouse_sk AS warehouse_sk,
       d.d_date AS sold_date, ws_bill_customer_sk AS customer_sk,
       coalesce(ws_quantity > 0 AND ws_ext_sales_price IS NOT NULL AND ws_warehouse_sk IS NOT NULL, false) AS complete
  FROM web_sales LEFT JOIN date_dim d ON d.d_date_sk = ws_sold_date_sk
UNION ALL
SELECT 'marketplace', cs_order_number, cs_item_sk, cs_quantity, cs_ext_sales_price, cs_warehouse_sk,
       d.d_date, cs_bill_customer_sk,
       coalesce(cs_quantity > 0 AND cs_ext_sales_price IS NOT NULL AND cs_warehouse_sk IS NOT NULL, false)
  FROM catalog_sales LEFT JOIN date_dim d ON d.d_date_sk = cs_sold_date_sk;
ANALYZE _au_fact;

-- A line is COMPLETE when it can be priced and shipped: quantity, amount and warehouse known (TPC-DS leaves
-- ~4 % of every nullable column NULL, at random). An order is KEPT when it has a complete line, a bill
-- customer and a sold date on or before as_of — the extension is the ERP as of the demo day. TPC-DS gives
-- all lines of an order one sold date and one bill customer, so a line missing either takes the order's.
CREATE TEMP TABLE _au_order ON COMMIT DROP AS
SELECT order_number, min(channel) AS channel,
       mode() WITHIN GROUP (ORDER BY customer_sk) AS customer_sk,                         -- NULLs are ignored
       min(sold_date) AS placed_date,
       mode() WITHIN GROUP (ORDER BY warehouse_sk) FILTER (WHERE complete) AS warehouse_sk,  -- ties: the lower sk
       sum(ext_sales_price) FILTER (WHERE complete) AS value
  FROM _au_fact
 GROUP BY order_number
HAVING bool_or(complete)
   AND count(customer_sk) > 0
   AND min(sold_date) <= :'as_of'::date;
ANALYZE _au_order;

INSERT INTO sales_order (so_order_number, so_channel, so_customer_sk, so_placed_date, so_delivered_date,
                         so_warehouse_sk, so_value, so_state, so_held_for, so_placed_by)
SELECT order_number, channel, customer_sk, placed_date,
       CASE WHEN placed_date < :'as_of'::date - :delivered_after
            THEN placed_date + 3 + abs(hashtext(order_number::text)) % 5 END,
       warehouse_sk, value, 'released', NULL, 'shop'
  FROM _au_order
 ORDER BY order_number;

-- line_no: the order's lines by item (an item appears once per order — the facts' key).
INSERT INTO sales_line (sl_order_number, sl_line_no, sl_item_sk, sl_quantity, sl_unit_price, sl_ext_sales_price,
                        sl_warehouse_sk, sl_sold_date, sl_customer_sk, sl_channel)
SELECT f.order_number, row_number() OVER (PARTITION BY f.order_number ORDER BY f.item_sk), f.item_sk, f.quantity,
       round(f.ext_sales_price / f.quantity, 2), f.ext_sales_price, f.warehouse_sk,
       coalesce(f.sold_date, o.placed_date), o.customer_sk, f.channel
  FROM _au_fact f JOIN _au_order o USING (order_number)
 WHERE f.complete
 ORDER BY 1, 2;

-- The join paths the recipes take (17 §3: an order's lines, a customer's invoices; §4.1: a customer's 12 months of
-- lines; H-3: an item's demand at a center) — indexed once the rows are in, as the build itself takes them too.
CREATE INDEX IF NOT EXISTS ix_sales_order_customer ON sales_order (so_customer_sk);
CREATE INDEX IF NOT EXISTS ix_sales_line_customer ON sales_line (sl_customer_sk, sl_sold_date);
CREATE INDEX IF NOT EXISTS ix_sales_line_item_warehouse ON sales_line (sl_item_sk, sl_warehouse_sk);
ANALYZE sales_order, sales_line;

INSERT INTO _automation_base (fact, last_date, row_count)
SELECT CASE channel WHEN 'web' THEN 'web_sales' ELSE 'catalog_sales' END, max(sold_date), count(*)
  FROM _au_fact GROUP BY 1;

INSERT INTO _automation_meta (step, as_of, rows) SELECT '20-orders', :'as_of', count(*) FROM sales_line;
