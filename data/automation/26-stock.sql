-- AU-hartland P1 · S1.1 — the open orders' stock (README.md "Stock"). 17 §3's `shortfall` flags an open line
-- whose (item, warehouse) LATEST inventory snapshot holds less than the line's quantity (no snapshot: 0).
-- TPC-DS stock is uniform 0–1000 with NULLs, so a random order of a dozen lines would be short more often
-- than not; the shop takes the orders it can ship. So the latest snapshot of every pair an open line needs is
-- raised to cover the largest such line, plus a hashed 10–99 of slack (a pair with no snapshot gets one) —
-- through pg_temp.au_stock (10-ddl.sql), which journals every change in _automation_undo first. 40-plant.sql
-- then plants the short orders on top.
-- (`SELECT count(*) FROM (SELECT f(…) …) \gset` is how a script calls a function per row without printing a row per call.)
SELECT count(*) AS stock_calls FROM (
  SELECT pg_temp.au_stock(n.item, n.warehouse, n.quantity, n.quantity + 10 + abs(hashtext(n.item || ':' || n.warehouse || ':stock')) % 90)
    FROM (SELECT s.sl_item_sk AS item, s.sl_warehouse_sk AS warehouse, max(s.sl_quantity) AS quantity
            FROM sales_order o JOIN sales_line s ON s.sl_order_number = o.so_order_number
           WHERE o.so_state IN ('placed', 'held')
           GROUP BY 1, 2 ORDER BY 1, 2) n) z \gset au_

INSERT INTO _automation_base (fact, last_date, row_count)
SELECT 'inventory', (SELECT d_date FROM date_dim WHERE d_date_sk = (SELECT max(inv_date_sk) FROM inventory)), count(*) FROM inventory;

INSERT INTO _automation_meta (step, as_of, rows) SELECT '26-stock', :'as_of', count(*) FROM _automation_undo WHERE tbl = 'inventory';
