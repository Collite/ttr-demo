-- AU-hartland P1 · S1.1 — the open orders' stock (README.md "Stock"). 17 §3's `shortfall` flags an open line
-- whose (item, warehouse) LATEST inventory snapshot holds less than the line's quantity (no snapshot: 0).
-- TPC-DS stock is uniform 0–1000 with NULLs, so a random order of a dozen lines would be short more often
-- than not; the shop takes the orders it can ship. So the latest snapshot of every pair an open line needs is
-- raised to cover the largest such line, plus a hashed 10–99 of slack — and a pair with no snapshot at all
-- gets one, at the latest snapshot date. Every row changed or added is journaled in _automation_undo FIRST
-- (reset.sql gives it back). S1.2 then plants the short orders on top.
CREATE TEMP TABLE _au_need ON COMMIT DROP AS
SELECT s.sl_item_sk AS item, s.sl_warehouse_sk AS warehouse, max(s.sl_quantity) AS quantity
  FROM sales_order o JOIN sales_line s ON s.sl_order_number = o.so_order_number
 WHERE o.so_state IN ('placed', 'held')
 GROUP BY 1, 2;

-- One pass over inventory (its key leads with the date, so a per-pair "latest" lookup would walk the index).
CREATE TEMP TABLE _au_latest ON COMMIT DROP AS
SELECT n.item, n.warehouse, n.quantity, l.date_sk,
       n.quantity + 10 + abs(hashtext(n.item || ':' || n.warehouse || ':stock')) % 90 AS stock
  FROM _au_need n
  LEFT JOIN (SELECT i.inv_item_sk, i.inv_warehouse_sk, max(i.inv_date_sk) AS date_sk
               FROM inventory i JOIN _au_need n2 ON n2.item = i.inv_item_sk AND n2.warehouse = i.inv_warehouse_sk
              GROUP BY 1, 2) l ON l.inv_item_sk = n.item AND l.inv_warehouse_sk = n.warehouse;

INSERT INTO _automation_undo (tbl, pk, col, old_value)
SELECT 'inventory', ARRAY[i.inv_date_sk, i.inv_item_sk, i.inv_warehouse_sk], 'inv_quantity_on_hand', i.inv_quantity_on_hand::text
  FROM _au_latest l
  JOIN inventory i ON i.inv_date_sk = l.date_sk AND i.inv_item_sk = l.item AND i.inv_warehouse_sk = l.warehouse
 WHERE coalesce(i.inv_quantity_on_hand, 0) < l.quantity
ON CONFLICT DO NOTHING;

UPDATE inventory i
   SET inv_quantity_on_hand = l.stock
  FROM _au_latest l
 WHERE i.inv_date_sk = l.date_sk AND i.inv_item_sk = l.item AND i.inv_warehouse_sk = l.warehouse
   AND coalesce(i.inv_quantity_on_hand, 0) < l.quantity;

INSERT INTO _automation_undo (tbl, pk, col, old_value, inserted)
SELECT 'inventory', ARRAY[(SELECT max(inv_date_sk) FROM inventory), item, warehouse], '*', NULL, true
  FROM _au_latest WHERE date_sk IS NULL
ON CONFLICT DO NOTHING;

INSERT INTO inventory (inv_date_sk, inv_item_sk, inv_warehouse_sk, inv_quantity_on_hand)
SELECT (SELECT max(inv_date_sk) FROM inventory), item, warehouse, stock
  FROM _au_latest WHERE date_sk IS NULL
 ORDER BY 2, 3;

INSERT INTO _automation_base (fact, last_date, row_count)
SELECT 'inventory', (SELECT d_date FROM date_dim WHERE d_date_sk = (SELECT max(inv_date_sk) FROM inventory)), count(*) FROM inventory;

INSERT INTO _automation_meta (step, as_of, rows) SELECT '26-stock', :'as_of', count(*) FROM _automation_undo WHERE tbl = 'inventory';
