-- AU-hartland P1 · S1.1 — the price list, the individual prices, and the demo day's OPEN orders priced from
-- them (README.md "Prices" and "The open orders").

-- price_list: per (item, channel) the MEDIAN unit price of its template-year lines (of all its lines when it
-- sold nothing that year), open-ended from 1 January; and the year before as a closed window at 97 %, so "the
-- price valid at placed_date" is a real join. The median, not T5's mode: TPC-DS prices every line on its own
-- (wholesale cost × markup × discount, all random), so nearly every price is unique and the mode degenerates
-- to the lowest price of the year.
INSERT INTO price_list (pl_item_sk, pl_channel, pl_valid_from, pl_price, pl_valid_to)
WITH m AS (
  SELECT sl_item_sk AS item, sl_channel AS channel,
         coalesce(percentile_disc(0.5) WITHIN GROUP (ORDER BY sl_unit_price)
                    FILTER (WHERE sl_sold_date >= make_date(:template_year, 1, 1) AND sl_sold_date < make_date(:template_year + 1, 1, 1)),
                  percentile_disc(0.5) WITHIN GROUP (ORDER BY sl_unit_price)) AS price
    FROM sales_line
   WHERE sl_unit_price > 0
   GROUP BY 1, 2
)
SELECT item, channel, make_date(:template_year, 1, 1), price, NULL::date FROM m
UNION ALL
SELECT item, channel, make_date(:template_year - 1, 1, 1), round(price * 0.97, 2), make_date(:template_year - 1, 12, 31) FROM m
ORDER BY 1, 2, 3;

-- customer_price: ~2 % of the (customer, item) pairs with lines — a hash of the pair — get their own price,
-- 90–97 % of the item's lowest open list price, open-ended from the template year.
INSERT INTO customer_price (cp_item_sk, cp_customer_sk, cp_valid_from, cp_price, cp_valid_to)
SELECT p.item, p.customer, make_date(:template_year, 1, 1),
       round(l.price * (0.90 + (abs(hashtext(p.customer || ':' || p.item)) % 8) / 100.0), 2), NULL
  FROM (SELECT DISTINCT sl_customer_sk AS customer, sl_item_sk AS item FROM sales_line) p
  JOIN (SELECT pl_item_sk AS item, min(pl_price) AS price FROM price_list WHERE pl_valid_to IS NULL GROUP BY 1) l USING (item)
 WHERE abs(hashtext(p.customer || ':' || p.item)) % :customer_price_mod = 0
 ORDER BY 1, 2;

-- ── the open orders ──────────────────────────────────────────────────────────────────────────────────────────
-- 17 §3's candidates are the orders in state placed/held. On the demo day they are the latest
-- :placed_orders + :held_orders orders placed on or before as_of (newest first; a day's ties by a hash of the
-- number), among those whose value at the price list stays under the cap (automation.conf). Their lines are
-- RE-PRICED from the price list, as an ERP prices an order — the customer's price where one is valid on the
-- placement day, else the channel's: 17 §3 compares a line with its applicable price to the cent
-- (`ABS(unit_price - price) > :tolerance`), so an open line at its fact's own price would be a price difference
-- on almost every order. History (released) keeps the facts' prices.
--
-- THE OUTAGE CENTER. 40-plant.sql puts one center out of service over as_of, and 17 §3 then flags every open
-- line that ships from it — so exactly :outage_orders open orders may have a line there (the `outage` plants);
-- every other open order is picked among the orders with no line at it. The center is a hash pick.
CREATE TEMP TABLE _au_demo ON COMMIT DROP AS
SELECT (SELECT w_warehouse_sk FROM warehouse ORDER BY abs(hashtext('outage:' || w_warehouse_sk)), w_warehouse_sk LIMIT 1) AS outage_center;

CREATE TEMP TABLE _au_open_line ON COMMIT DROP AS
SELECT s.sl_order_number AS order_number, s.sl_line_no AS line_no, s.sl_quantity AS quantity,
       coalesce(cp.cp_price, pl.pl_price) AS price
  FROM sales_order o
  JOIN sales_line s ON s.sl_order_number = o.so_order_number
  LEFT JOIN customer_price cp ON cp.cp_item_sk = s.sl_item_sk AND cp.cp_customer_sk = o.so_customer_sk
       AND cp.cp_valid_from <= o.so_placed_date AND (cp.cp_valid_to IS NULL OR cp.cp_valid_to >= o.so_placed_date)
  LEFT JOIN price_list pl ON pl.pl_item_sk = s.sl_item_sk AND pl.pl_channel = o.so_channel
       AND pl.pl_valid_from <= o.so_placed_date AND (pl.pl_valid_to IS NULL OR pl.pl_valid_to >= o.so_placed_date)
 WHERE o.so_placed_date > :'as_of'::date - 28;      -- the last four weeks: many times the orders that open

CREATE TEMP TABLE _au_open ON COMMIT DROP AS
WITH v AS (
  SELECT o.so_order_number AS order_number, o.so_placed_date, v.value,
         EXISTS (SELECT 1 FROM sales_line s WHERE s.sl_order_number = o.so_order_number
                    AND s.sl_warehouse_sk = (SELECT outage_center FROM _au_demo)) AS at_outage
    FROM sales_order o
    JOIN (SELECT order_number, sum(round(price * quantity, 2)) AS value, bool_and(price IS NOT NULL) AS priced
            FROM _au_open_line GROUP BY 1) v ON v.order_number = o.so_order_number
   WHERE v.priced AND v.value <= :confirmation_threshold * :open_value_cap
), r AS (
  SELECT v.*, row_number() OVER (PARTITION BY at_outage ORDER BY so_placed_date DESC, abs(hashtext(order_number::text)), order_number) AS rn
    FROM v
)
SELECT order_number, value, at_outage FROM r
 WHERE (NOT at_outage AND rn <= :placed_orders + :held_orders - :outage_orders) OR (at_outage AND rn <= :outage_orders);

UPDATE sales_line s
   SET sl_unit_price = l.price, sl_ext_sales_price = round(l.price * l.quantity, 2)
  FROM _au_open_line l JOIN _au_open o USING (order_number)
 WHERE s.sl_order_number = l.order_number AND s.sl_line_no = l.line_no;

UPDATE sales_order s
   SET so_state = 'placed', so_value = o.value, so_delivered_date = NULL
  FROM _au_open o
 WHERE s.so_order_number = o.order_number;

INSERT INTO _automation_meta (step, as_of, rows)
SELECT '21-pricing', :'as_of', (SELECT count(*) FROM price_list) + (SELECT count(*) FROM customer_price) + (SELECT count(*) FROM _au_open);
