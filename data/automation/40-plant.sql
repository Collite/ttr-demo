-- AU-hartland P1 · S1.2 — the H-1, H-3 and H-5 plants (contracts §5; README.md "The plants"); H-2's are planted
-- where the returns are built (30-returns.sql). Every plant is a row of _automation_plan with the route the recipe
-- must take; 45-verify.sql replays the recipes over the result and fails the build if one disagrees.
ALTER TABLE _au_param ADD COLUMN cover_weeks integer, ADD COLUMN threshold numeric;
UPDATE _au_param SET cover_weeks = :p_reorder_cover_weeks, threshold = :confirmation_threshold;

-- ── H-3 first — the stock the shop keeps ─────────────────────────────────────────────────────────────────────────
-- H-3 proposes a reorder for every (item, center) pair whose latest stock covers less than :p_reorder_cover_weeks
-- weeks of the last :p_reorder_period_weeks weeks' demand. TPC-DS stock (uniform 0–1000, NULLs) leaves thousands
-- of pairs under that, and the demo's list is the 25 planted below: so every pair with demand first gets 4–6 weeks
-- of it, where it has less than the 3 (journaled, pg_temp.au_stock). Only ever raised: the plants then lower.
CREATE TEMP TABLE _au_demand ON COMMIT DROP AS
SELECT sl_item_sk AS item, sl_warehouse_sk AS wh, sum(sl_quantity)::numeric / :p_reorder_period_weeks AS weekly
  FROM sales_line
 WHERE sl_sold_date > :'as_of'::date - 7 * :p_reorder_period_weeks AND sl_sold_date <= :'as_of'::date
 GROUP BY 1, 2;
ALTER TABLE _au_demand ADD PRIMARY KEY (item, wh);
SELECT count(*) AS stock_calls FROM (
  SELECT pg_temp.au_stock(item, wh, ceil(:p_reorder_cover_weeks * weekly)::int,
                          ceil(weekly * (4 + abs(hashtext('cover:' || item || ':' || wh)) % 3))::int)
    FROM _au_demand ORDER BY item, wh) z \gset au_

-- ── H-1 · the open orders (contracts §5) ────────────────────────────────────────────────────────────────────────
-- What a pick needs to know of each open order, and its place in the pick order (a hash of the number).
CREATE TEMP TABLE _au_cand ON COMMIT DROP AS
SELECT o.so_order_number AS order_number, o.so_customer_sk AS customer, abs(hashtext('plant:' || o.so_order_number)) AS h,
       (SELECT count(*) FROM sales_order x WHERE x.so_customer_sk = o.so_customer_sk AND x.so_state IN ('placed', 'held')) AS customer_open,
       EXISTS (SELECT 1 FROM invoice i WHERE i.inv_customer_sk = o.so_customer_sk) AS has_invoice,
       s.sl_item_sk AS item1, s.sl_warehouse_sk AS wh1, s.sl_quantity AS qty1, s.sl_unit_price AS price1,
       (SELECT max(sl_unit_price) FROM sales_line x WHERE x.sl_order_number = o.so_order_number) AS max_price,
       (SELECT count(*) FROM sales_line x JOIN sales_order xo ON xo.so_order_number = x.sl_order_number AND xo.so_state IN ('placed', 'held')
         WHERE x.sl_item_sk = s.sl_item_sk AND x.sl_warehouse_sk = s.sl_warehouse_sk) AS pair_lines,
       coalesce(d.weekly, 0) AS weekly1,
       EXISTS (SELECT 1 FROM _au_h2stock k WHERE k.item = s.sl_item_sk AND k.wh = s.sl_warehouse_sk) AS h2_pair,
       EXISTS (SELECT 1 FROM sales_line x WHERE x.sl_order_number = o.so_order_number
                  AND x.sl_warehouse_sk = (SELECT outage_center FROM _au_demo)) AS at_outage,
       EXISTS (SELECT 1 FROM customer_price cp WHERE cp.cp_item_sk = s.sl_item_sk AND cp.cp_customer_sk = o.so_customer_sk) AS has_cp
  FROM sales_order o
  JOIN sales_line s ON s.sl_order_number = o.so_order_number AND s.sl_line_no = 1
  LEFT JOIN _au_demand d ON d.item = s.sl_item_sk AND d.wh = s.sl_warehouse_sk
 WHERE o.so_state IN ('placed', 'held');

CREATE TEMP TABLE _au_h1 (order_number integer PRIMARY KEY, kind text NOT NULL, pick integer NOT NULL) ON COMMIT DROP;

-- au_pick_order(kind, n, condition): n times, the next open order in hash order (no line at the outage center,
-- not yet planted) meeting the condition (SQL over `c`, the order, and `p`). Too few is an error.
CREATE FUNCTION pg_temp.au_pick_order(p_kind text, p_n int, p_where text) RETURNS int LANGUAGE plpgsql AS $$
DECLARE i int; got int;
BEGIN
  FOR i IN 1..p_n LOOP
    EXECUTE format($q$INSERT INTO _au_h1 (order_number, kind, pick)
                      SELECT c.order_number, %L, %s FROM _au_cand c CROSS JOIN _au_param p
                       WHERE NOT c.at_outage AND c.order_number NOT IN (SELECT order_number FROM _au_h1) AND (%s)
                       ORDER BY c.h, c.order_number LIMIT 1$q$, p_kind, i, p_where);
    GET DIAGNOSTICS got = ROW_COUNT;
    IF got = 0 THEN
      RAISE EXCEPTION 'automation_plant: % of % open orders found for % (%)', i - 1, p_n, p_kind, p_where;
    END IF;
  END LOOP;
  RETURN p_n;
END $$;

-- The outage orders: the two open orders with a line at the outage center (21-pricing.sql opened exactly two).
INSERT INTO _au_h1 (order_number, kind, pick)
SELECT order_number, 'release:outage', row_number() OVER (ORDER BY h, order_number) FROM _au_cand WHERE at_outage;
-- SHORT-SAFE: a stock plant lowers the first line's pair to one short of the line — so the pair must be that line's
-- alone among the open lines (no other order goes short), keep :p_reorder_cover_weeks weeks of cover at one short
-- (no reorder proposal nobody planted), and be none decide_return reads.
\set short_safe 'c.pair_lines = 1 AND c.qty1 - 1 >= p.cover_weeks * c.weekly1 AND NOT c.h2_pair'
-- OVERDUE-SAFE: the customer's only open order (every open order of an overdue customer is held for AR), and an invoice to re-open.
\set overdue_safe 'c.customer_open = 1 AND c.has_invoice'
SELECT pg_temp.au_pick_order('release:both', 2, :'overdue_safe' || ' AND ' || :'short_safe') AS picked \gset au_
SELECT pg_temp.au_pick_order('release:overdue', 5, :'overdue_safe') AS picked \gset au_
SELECT pg_temp.au_pick_order('release:short', 8, :'short_safe') AS picked \gset au_
SELECT pg_temp.au_pick_order('release:held_yesterday', 3, :'short_safe') AS picked \gset au_
-- a price 7 % up is beyond the tolerance (to the cent) only on a price of a unit or more
SELECT pg_temp.au_pick_order('release:price_above_list', 6, 'c.price1 >= 1') AS picked \gset au_
-- an individual price: a pair with none yet, a customer with no other open order (it would price their other lines too)
SELECT pg_temp.au_pick_order('release:individual_price', 3, 'NOT c.has_cp AND c.customer_open = 1 AND c.price1 >= 1') AS picked \gset au_
-- above the threshold: the dearest line's quantity carries the order there — a dear enough line keeps it believable
SELECT pg_temp.au_pick_order('release:confirm', 2, 'c.max_price >= p.threshold / 1000') AS picked \gset au_
INSERT INTO _au_h1 (order_number, kind, pick)
SELECT order_number, 'release:clean', row_number() OVER (ORDER BY h, order_number)
  FROM _au_cand WHERE order_number NOT IN (SELECT order_number FROM _au_h1);

-- the outage: the center is out of service from the day before the demo day to the day after
INSERT INTO warehouse_outage (wo_warehouse_sk, wo_from_date, wo_to_date, wo_reason)
SELECT outage_center, :'as_of'::date - 1, :'as_of'::date + 1, 'system_outage' FROM _au_demo;

-- short · both · held yesterday: the first line's stock, one short
SELECT count(*) AS stock_calls FROM (
  SELECT pg_temp.au_stock(c.item1, c.wh1, NULL, c.qty1 - 1)
    FROM _au_h1 h JOIN _au_cand c USING (order_number)
   WHERE h.kind IN ('release:short', 'release:both', 'release:held_yesterday') ORDER BY h.order_number) z \gset au_
UPDATE sales_order SET so_state = 'held', so_held_for = 'Sales'
 WHERE so_order_number IN (SELECT order_number FROM _au_h1 WHERE kind = 'release:held_yesterday');

-- overdue · both: the customer's latest invoice re-opened, nothing paid, due 10 days before the demo day
UPDATE invoice i
   SET inv_status = 'open', inv_paid = 0, inv_due = :'as_of'::date - 10, inv_issued = :'as_of'::date - 10 - :payment_days
  FROM (SELECT DISTINCT ON (x.inv_customer_sk) x.inv_invoice_id
          FROM invoice x JOIN _au_cand c ON c.customer = x.inv_customer_sk JOIN _au_h1 h USING (order_number)
         WHERE h.kind IN ('release:overdue', 'release:both')
         ORDER BY x.inv_customer_sk, x.inv_issued DESC, x.inv_invoice_id DESC) z
 WHERE i.inv_invoice_id = z.inv_invoice_id;

-- price above list: the first line 7 % over the price it was given
UPDATE sales_line s
   SET sl_unit_price = round(s.sl_unit_price * 1.07, 2), sl_ext_sales_price = round(round(s.sl_unit_price * 1.07, 2) * s.sl_quantity, 2)
  FROM _au_h1 h
 WHERE h.kind = 'release:price_above_list' AND s.sl_order_number = h.order_number AND s.sl_line_no = 1;

-- individual price honoured: the customer's own price for the first line, 8 % under the list, valid for 90 days —
-- and the line priced at it (the negative control: no hold)
INSERT INTO customer_price (cp_item_sk, cp_customer_sk, cp_valid_from, cp_price, cp_valid_to)
SELECT c.item1, c.customer, :'as_of'::date - 90, round(c.price1 * 0.92, 2), NULL
  FROM _au_h1 h JOIN _au_cand c USING (order_number) WHERE h.kind = 'release:individual_price' ORDER BY 1, 2;
UPDATE sales_line s
   SET sl_unit_price = round(c.price1 * 0.92, 2), sl_ext_sales_price = round(round(c.price1 * 0.92, 2) * s.sl_quantity, 2)
  FROM _au_h1 h JOIN _au_cand c USING (order_number)
 WHERE h.kind = 'release:individual_price' AND s.sl_order_number = h.order_number AND s.sl_line_no = 1;

-- above the threshold, all green: the dearest line's quantity carries the order to 1.2 × the threshold; its stock
-- covers the line and 3 weeks of the demand it adds
CREATE TEMP TABLE _au_confirm ON COMMIT DROP AS
SELECT h.order_number, s.sl_line_no AS line_no, s.sl_item_sk AS item, s.sl_warehouse_sk AS wh, s.sl_unit_price AS price,
       s.sl_quantity AS old_qty, s.sl_quantity + ceil((1.2 * :confirmation_threshold - o.so_value) / s.sl_unit_price)::int AS qty
  FROM _au_h1 h JOIN sales_order o ON o.so_order_number = h.order_number
  JOIN LATERAL (SELECT * FROM sales_line WHERE sl_order_number = h.order_number ORDER BY sl_unit_price DESC, sl_line_no LIMIT 1) s ON true
 WHERE h.kind = 'release:confirm';
UPDATE sales_line s SET sl_quantity = c.qty, sl_ext_sales_price = round(c.price * c.qty, 2)
  FROM _au_confirm c WHERE s.sl_order_number = c.order_number AND s.sl_line_no = c.line_no;
SELECT count(*) AS stock_calls FROM (
  SELECT pg_temp.au_stock(c.item, c.wh, n.need, n.need + 10)
    FROM _au_confirm c LEFT JOIN _au_demand d ON d.item = c.item AND d.wh = c.wh
   CROSS JOIN LATERAL (SELECT greatest(c.qty, ceil(:p_reorder_cover_weeks * (coalesce(d.weekly, 0) + (c.qty - c.old_qty)::numeric / :p_reorder_period_weeks))::int + 1) AS need) n
   ORDER BY c.order_number) z \gset au_

-- the planted orders' values follow their lines
UPDATE sales_order o SET so_value = v.value
  FROM (SELECT sl_order_number, sum(sl_ext_sales_price) AS value FROM sales_line
         WHERE sl_order_number IN (SELECT order_number FROM _au_h1) GROUP BY 1) v
 WHERE o.so_order_number = v.sl_order_number AND o.so_value <> v.value;

INSERT INTO _automation_plan (kind, key, note, expected_route)
SELECT h.kind, h.order_number::text,
       CASE h.kind
         WHEN 'release:confirm' THEN 'value ' || o.so_value || ' > confirmation_threshold ' || :confirmation_threshold
         WHEN 'release:outage' THEN 'center ' || (SELECT outage_center FROM _au_demo) || ' out ' || (:'as_of'::date - 1) || ' .. ' || (:'as_of'::date + 1)
         WHEN 'release:price_above_list' THEN 'line 1 at 107 % of its price; tolerance ' || :p_tolerance
         WHEN 'release:individual_price' THEN 'line 1 at the customer''s own price, valid from ' || (:'as_of'::date - 90)
         WHEN 'release:overdue' THEN 'invoice due ' || (:'as_of'::date - 10)
         WHEN 'release:both' THEN 'item ' || c.item1 || ' at center ' || c.wh1 || ': ' || (c.qty1 - 1) || ' for ' || c.qty1 || '; invoice due ' || (:'as_of'::date - 10)
         WHEN 'release:clean' THEN 'value ' || o.so_value || ' <= confirmation_threshold ' || :confirmation_threshold
         ELSE 'item ' || c.item1 || ' at center ' || c.wh1 || ': ' || (c.qty1 - 1) || ' for ' || c.qty1 END,
       CASE h.kind WHEN 'release:clean' THEN 'release' WHEN 'release:individual_price' THEN 'release'
                   WHEN 'release:confirm' THEN 'release_confirmed' WHEN 'release:overdue' THEN 'hold_ar'
                   WHEN 'release:both' THEN 'hold_ar,hold_sales' ELSE 'hold_sales' END
  FROM _au_h1 h JOIN _au_cand c USING (order_number) JOIN sales_order o ON o.so_order_number = h.order_number
 ORDER BY h.kind, h.pick;

-- ── H-3 · 25 (item, center) pairs under 3 weeks of cover ─────────────────────────────────────────────────────────
-- A hash pick among the pairs with a unit or more of weekly demand that nothing else reads: no open line (its
-- shortfall), no received return line (its replacement / exchange stock). Their stock: 1.5 weeks of demand.
CREATE TEMP TABLE _au_reorder ON COMMIT DROP AS
SELECT d.item, d.wh, d.weekly, floor(d.weekly * 1.5)::int AS on_hand
  FROM _au_demand d
 WHERE d.weekly >= 1
   AND NOT EXISTS (SELECT 1 FROM sales_line s JOIN sales_order o ON o.so_order_number = s.sl_order_number AND o.so_state IN ('placed', 'held')
                    WHERE s.sl_item_sk = d.item AND s.sl_warehouse_sk = d.wh)
   AND NOT EXISTS (SELECT 1 FROM _au_h2stock k WHERE k.item = d.item AND k.wh = d.wh)
 ORDER BY abs(hashtext('reorder:' || d.item || ':' || d.wh)), d.item, d.wh
 LIMIT :reorder_pairs;
SELECT count(*) AS stock_calls FROM (SELECT pg_temp.au_stock(item, wh, NULL, on_hand) FROM _au_reorder ORDER BY item, wh) z \gset au_
INSERT INTO _automation_plan (kind, key, note, expected_route)
SELECT 'reorder:propose', item || ':' || wh, 'on hand ' || on_hand || '; weekly demand ' || round(weekly, 2), 'propose'
  FROM _au_reorder ORDER BY 2;

-- ── H-5 · the win-back list ─────────────────────────────────────────────────────────────────────────────────────
-- 04 H-5 (D-129): customers with :p_winback_active_orders or more orders in the twelve months before the last
-- :p_winback_quiet_months and none since; the premium offer for the top two income bands. Ten of them were mailed a
-- month ago — inside the mail window, so they are off this list (route `none`: the seed asserts their absence).
CREATE TEMP TABLE _au_winback ON COMMIT DROP AS
SELECT o.so_customer_sk AS customer,
       CASE WHEN hd.hd_income_band_sk IN (SELECT ib_income_band_sk FROM income_band ORDER BY ib_lower_bound DESC LIMIT 2)
            THEN 'premium' ELSE 'standard' END AS offer
  FROM sales_order o JOIN customer c ON c.c_customer_sk = o.so_customer_sk
  LEFT JOIN household_demographics hd ON hd.hd_demo_sk = c.c_current_hdemo_sk
 GROUP BY o.so_customer_sk, hd.hd_income_band_sk
HAVING count(*) FILTER (WHERE o.so_placed_date >= :'as_of'::date - make_interval(months => :p_winback_quiet_months + 12)
                          AND o.so_placed_date <  :'as_of'::date - make_interval(months => :p_winback_quiet_months)) >= :p_winback_active_orders
   AND count(*) FILTER (WHERE o.so_placed_date >= :'as_of'::date - make_interval(months => :p_winback_quiet_months)) = 0;
INSERT INTO winback_mail (wm_customer_sk, wm_quarter, wm_offer, wm_run, wm_mailed_at)
SELECT customer, to_char(:'as_of'::date - 30, 'YYYY-"Q"Q'), offer, 'automation-data',
       ((:'as_of'::date - 30) + time '10:00') AT TIME ZONE 'Europe/Prague'
  FROM _au_winback ORDER BY abs(hashtext('winback:' || customer)), customer LIMIT :winback_mailed;
INSERT INTO _automation_plan (kind, key, note, expected_route)
SELECT 'winback:mailed', wm_customer_sk::text, 'mailed ' || (wm_mailed_at AT TIME ZONE 'Europe/Prague')::date || '; mail window ' || :p_winback_mail_window || ' days', 'none'
  FROM winback_mail ORDER BY wm_customer_sk;
INSERT INTO _automation_plan (kind, key, note, expected_route)
SELECT 'winback:list', customer::text, NULL, offer
  FROM _au_winback WHERE customer NOT IN (SELECT wm_customer_sk FROM winback_mail) ORDER BY customer;

INSERT INTO _automation_meta (step, as_of, rows) SELECT '40-plant', :'as_of', count(*) FROM _automation_plan;
