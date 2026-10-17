-- AU-hartland P1 · S1.2 — the return-request flow (D-84; README.md "Returns"): requests and lines from the
-- *_returns facts, the history decided by decide_return's own rules and settled, and the demo day's H-2 plants
-- (contracts §5) — 40 received lines over the eight decide_return routes, 17 awaiting the goods, 10 settling.
-- Every line carries the dates of its documents here; 31-receipts.sql and 32-settlement.sql write them.

-- ── the returns: a dated web / marketplace return of an item on a kept, DELIVERED order ──────────────────────
-- Requested on the later of the return date and the delivery (an ERP takes no request for goods it has not
-- delivered — an order still on its way has none), on or before as_of; priced as sold; at most the quantity sold.
-- The customer is the ORDER's (TPC-DS draws a return's customer at random; a request is the buyer's).
CREATE TEMP TABLE _au_ret ON COMMIT DROP AS
SELECT r.channel, r.order_number, r.item, o.so_customer_sk AS customer,
       greatest(r.returned, o.so_delivered_date) AS requested_date,
       greatest(1, least(coalesce(r.rqty, 1), s.sl_quantity)) AS quantity,
       s.sl_quantity AS sold_quantity, s.sl_unit_price AS unit_price, o.so_delivered_date AS delivered,
       CASE WHEN r.reason_sk = ANY (:'reasons_damaged'::int[]) THEN 'damaged'
            WHEN r.reason_sk = ANY (:'reasons_did_not_arrive'::int[]) THEN 'did_not_arrive'
            WHEN r.reason_sk = ANY (:'reasons_wrong_size'::int[]) THEN 'wrong_size'
            ELSE 'other' END AS reason
  FROM (SELECT 'web'::text AS channel, wr_order_number + :web_order_offset AS order_number, wr_item_sk AS item,
               d.d_date AS returned, wr_return_quantity AS rqty, wr_reason_sk AS reason_sk
          FROM web_returns JOIN date_dim d ON d.d_date_sk = wr_returned_date_sk
        UNION ALL
        SELECT 'marketplace', cr_order_number, cr_item_sk, d.d_date, cr_return_quantity, cr_reason_sk
          FROM catalog_returns JOIN date_dim d ON d.d_date_sk = cr_returned_date_sk) r
  JOIN sales_order o ON o.so_order_number = r.order_number AND o.so_delivered_date IS NOT NULL
  JOIN sales_line s ON s.sl_order_number = r.order_number AND s.sl_item_sk = r.item
 WHERE greatest(r.returned, o.so_delivered_date) <= :'as_of'::date;

-- One request per (customer, order, requested date), numbered by date from 1; lines numbered world-wide from
-- :line_id_base in the same order, and 1..n within their request by item.
CREATE TEMP TABLE _au_rr ON COMMIT DROP AS
SELECT row_number() OVER (ORDER BY requested_date, order_number, customer)::int AS request_number,
       customer, order_number, min(channel) AS channel, requested_date
  FROM _au_ret GROUP BY customer, order_number, requested_date;
ALTER TABLE _au_rr ADD PRIMARY KEY (request_number);

-- An exchange names a variant: another item of the line's class, by a hash of the line.
CREATE TEMP TABLE _au_class ON COMMIT DROP AS
SELECT i.i_item_sk AS item, c.items
  FROM item i JOIN (SELECT btrim(i_class) AS class, array_agg(i_item_sk ORDER BY i_item_sk) AS items
                      FROM item WHERE i_class IS NOT NULL GROUP BY 1) c ON c.class = btrim(i.i_class);
CREATE FUNCTION pg_temp.au_variant(p_item int, p_line int) RETURNS int LANGUAGE sql STABLE AS $$
  SELECT CASE WHEN cardinality(array_remove(items, p_item)) > 0
              THEN (array_remove(items, p_item))[1 + abs(hashtext('variant:' || p_line)) % cardinality(array_remove(items, p_item))] END
    FROM _au_class WHERE item = p_item
$$;

CREATE TEMP TABLE _au_rl ON COMMIT DROP AS
SELECT x.*,
       CASE WHEN abs(hashtext('resolution:' || x.line_id)) % 10 < :refund_in_10 THEN 'refund'
            WHEN abs(hashtext('resolution:' || x.line_id)) % 10 < :refund_in_10 + :exchange_in_10 THEN 'exchange'
            ELSE 'replacement' END AS resolution,
       NULL::int AS variant, NULL::text AS state, NULL::text AS way, NULL::date AS decided,
       NULL::date AS rc_date, NULL::int AS rc_ok, NULL::int AS rc_bad, NULL::text AS rc_bad_condition,
       NULL::date AS cn_date, NULL::text AS cn_status, NULL::date AS rp_date, NULL::date AS rs_date, NULL::int AS rs_item,
       NULL::text AS added
  FROM (SELECT (:line_id_base + row_number() OVER (ORDER BY t.requested_date, t.order_number, t.item))::int AS line_id,
               rr.request_number,
               row_number() OVER (PARTITION BY rr.request_number ORDER BY t.item)::int AS line_no,
               count(*) OVER (PARTITION BY rr.request_number) AS request_lines,
               t.*
          FROM _au_ret t JOIN _au_rr rr ON rr.customer = t.customer AND rr.order_number = t.order_number
                                       AND rr.requested_date = t.requested_date) x;
ALTER TABLE _au_rl ADD PRIMARY KEY (line_id);
CREATE INDEX ON _au_rl (requested_date);
CREATE INDEX ON _au_rl (order_number, item);
CREATE INDEX ON _au_rl (customer);
CREATE INDEX ON _au_rl (request_number);
ALTER TABLE _au_class ADD PRIMARY KEY (item);
ANALYZE _au_rl, _au_rr, _au_class;
UPDATE _au_rl SET variant = pg_temp.au_variant(item, line_id) WHERE resolution = 'exchange';

-- ── history: decided the day after the request by decide_return's rules, then settled ───────────────────────
-- The rules (17 §4.1) without the two run-time contexts (the 12-month share and the stock: history is not
-- replayed against them): delivered more than :p_return_window days before the decision → rejected; a request
-- above the care threshold → customer care, who settled it as a refund after return; a small damaged / undelivered
-- line → refund, no return; damaged / undelivered → replacement, no return; an exchange with a variant → exchange;
-- else refund after return. A rejected line has no way (the recipe sets none). Settled documents follow the
-- decision by a few hashed days, never after as_of.
UPDATE _au_rl SET decided = least(requested_date + 1, :'as_of'::date);
UPDATE _au_rl l
   SET way = CASE
         WHEN l.delivered < l.decided - :p_return_window THEN NULL
         WHEN v.request_value > :care_threshold THEN 'refund_after_return'
         WHEN l.quantity * l.unit_price < :small_value AND l.reason IN ('damaged', 'did_not_arrive') THEN 'refund_no_return'
         WHEN l.reason IN ('damaged', 'did_not_arrive') THEN 'replacement_no_return'
         WHEN l.resolution = 'exchange' AND l.variant IS NOT NULL THEN 'exchange'
         ELSE 'refund_after_return' END,
       state = CASE WHEN l.delivered < l.decided - :p_return_window THEN 'rejected' ELSE 'closed' END
  FROM (SELECT request_number, sum(quantity * unit_price) AS request_value FROM _au_rl GROUP BY 1) v
 WHERE v.request_number = l.request_number;

CREATE TEMP TABLE _au_asof ON COMMIT DROP AS SELECT :'as_of'::date AS as_of;
CREATE FUNCTION pg_temp.au_settle_history() RETURNS void LANGUAGE sql AS $$
  UPDATE _au_rl SET
    rc_date = CASE WHEN way IN ('exchange', 'refund_after_return')
                   THEN least(decided + 3 + abs(hashtext('docs:' || line_id)) % 8, (SELECT as_of FROM _au_asof)) END,
    rc_ok   = CASE WHEN way IN ('exchange', 'refund_after_return') THEN quantity END,
    rc_bad  = CASE WHEN way IN ('exchange', 'refund_after_return') THEN 0 END
  WHERE state = 'closed' AND rc_date IS NULL;
  UPDATE _au_rl SET
    cn_date = CASE way WHEN 'refund_no_return' THEN least(decided + 1 + abs(hashtext('docs:' || line_id)) % 2, (SELECT as_of FROM _au_asof))
                       WHEN 'refund_after_return' THEN least(rc_date + 1 + abs(hashtext('docs:' || line_id)) % 2, (SELECT as_of FROM _au_asof)) END,
    rs_date = CASE way WHEN 'replacement_no_return' THEN least(decided + 1 + abs(hashtext('docs:' || line_id)) % 2, (SELECT as_of FROM _au_asof))
                       WHEN 'exchange' THEN least(rc_date + 1 + abs(hashtext('docs:' || line_id)) % 2, (SELECT as_of FROM _au_asof)) END,
    rs_item = CASE way WHEN 'replacement_no_return' THEN item WHEN 'exchange' THEN variant END
  WHERE state = 'closed' AND cn_date IS NULL AND rs_date IS NULL;
  UPDATE _au_rl SET cn_status = 'paid', rp_date = least(cn_date + 1 + abs(hashtext('docs:' || line_id)) % 4, (SELECT as_of FROM _au_asof))
  WHERE state = 'closed' AND cn_date IS NOT NULL AND rp_date IS NULL;
$$;
SELECT count(*) FROM (SELECT pg_temp.au_settle_history()) z \gset au_

-- ════════════════════════════════════════════════════════════════════════════════════════════════════════════════
-- THE H-2 PLANTS (contracts §5). Each is picked among the lines of single-line requests, newest first, with a
-- customer and an order no other plant uses (so no plant moves another's share, window or stock), and is then
-- given exactly the fields its route needs. 45-verify.sql replays decide_return over the result.
-- ════════════════════════════════════════════════════════════════════════════════════════════════════════════════
CREATE TEMP TABLE _au_param ON COMMIT DROP AS
SELECT :'as_of'::date AS as_of, :p_return_window AS return_window, :p_abuse_share::numeric AS abuse_share,
       :care_threshold::numeric AS care, :small_value::numeric AS small, :p_settlement AS settlement;

CREATE TEMP TABLE _au_h2 (
  line_id integer PRIMARY KEY,
  kind    text NOT NULL,
  route   text,
  way     text,                                      -- the way the line is given (decided plants)
  pick    integer NOT NULL,                          -- 1.. within the kind, in pick order
  note    text
) ON COMMIT DROP;

-- Each recent customer's 12 months: purchases, and the returns that count against them (not rejected) — the two
-- sides of decide_return's share, as they stand before the plants.
CREATE TEMP TABLE _au_cust ON COMMIT DROP AS
SELECT c.customer,
       coalesce((SELECT sum(sl_ext_sales_price) FROM sales_line WHERE sl_customer_sk = c.customer AND sl_sold_date >= :'as_of'::date - 365), 0) AS bought,
       coalesce((SELECT sum(quantity * unit_price) FROM _au_rl WHERE customer = c.customer AND requested_date >= :'as_of'::date - 365 AND state <> 'rejected'), 0) AS returned
  FROM (SELECT DISTINCT customer FROM _au_rl WHERE requested_date >= :'as_of'::date - 60) c;
ALTER TABLE _au_cust ADD PRIMARY KEY (customer);
ANALYZE _au_cust;

-- The free lines: the last 60 days' single-line requests whose customer and order no plant has taken yet.
CREATE TEMP TABLE _au_taken_customer (customer integer PRIMARY KEY) ON COMMIT DROP;
CREATE TEMP TABLE _au_taken_order (order_number integer PRIMARY KEY) ON COMMIT DROP;
CREATE TEMP VIEW _au_free AS
SELECT l.*, cu.c_center_sk AS center, c.bought, c.returned
  FROM _au_rl l JOIN customer cu ON cu.c_customer_sk = l.customer JOIN _au_cust c ON c.customer = l.customer
 WHERE l.requested_date >= (SELECT as_of FROM _au_param) - 60 AND l.request_lines = 1 AND l.added IS NULL
   AND NOT EXISTS (SELECT 1 FROM _au_taken_customer t WHERE t.customer = l.customer)
   AND NOT EXISTS (SELECT 1 FROM _au_taken_order t WHERE t.order_number = l.order_number);

-- au_pick(kind, route, way, n, condition): n times, the newest free line meeting the condition (SQL over `f`, the
-- free line, and `p`, the parameters) joins the plan. Too few such lines is an error, never a quiet shortfall.
CREATE FUNCTION pg_temp.au_pick(p_kind text, p_route text, p_way text, p_n int, p_where text) RETURNS int LANGUAGE plpgsql AS $$
DECLARE i int; got int; base int;
BEGIN
  SELECT count(*) INTO base FROM _au_h2 WHERE kind = p_kind;
  FOR i IN 1..p_n LOOP
    got := NULL;
    EXECUTE format($q$SELECT f.line_id FROM _au_free f CROSS JOIN _au_param p
                       WHERE %s ORDER BY f.requested_date DESC, f.line_id DESC LIMIT 1$q$, p_where) INTO got;
    IF got IS NULL THEN
      RAISE EXCEPTION 'automation_plant: % of % lines found for % (%)', i - 1, p_n, p_kind, p_where;
    END IF;
    INSERT INTO _au_h2 (line_id, kind, route, way, pick) VALUES (got, p_kind, p_route, p_way, base + i);
    INSERT INTO _au_taken_customer SELECT customer FROM _au_rl WHERE line_id = got ON CONFLICT DO NOTHING;
    INSERT INTO _au_taken_order SELECT order_number FROM _au_rl WHERE line_id = got ON CONFLICT DO NOTHING;
  END LOOP;
  RETURN p_n;
END $$;

-- Another sales line of the line's order, not returned, priced at most `max`, the n-th by item (with a variant, if asked).
CREATE FUNCTION pg_temp.au_other_item(p_line int, p_max numeric, p_n int, p_variant boolean) RETURNS int LANGUAGE sql STABLE AS $$
  SELECT s.sl_item_sk FROM _au_rl l JOIN sales_line s ON s.sl_order_number = l.order_number
   WHERE l.line_id = p_line AND s.sl_item_sk <> l.item AND s.sl_unit_price <= p_max AND s.sl_unit_price > 0
     AND NOT EXISTS (SELECT 1 FROM _au_rl r WHERE r.order_number = s.sl_order_number AND r.item = s.sl_item_sk)
     AND (NOT p_variant OR pg_temp.au_variant(s.sl_item_sk, p_line) IS NOT NULL)
   ORDER BY s.sl_item_sk OFFSET p_n - 1 LIMIT 1
$$;

-- ── decide_return · the 40 received lines (36 requests; 3 of them get more lines: the multi-line requests) ───────
-- DECIDABLE (every route after the two rejections): delivered well inside the window, and a 12-month share well
-- under the limit even with this line (and its request's extra lines) returned.
\set decidable 'f.delivered >= p.as_of - p.return_window + 2 AND f.bought > 0'
\set recent 'f.requested_date >= p.as_of - 21'
-- One statement per pick, so the picks run in this order (`\gset` swallows the one-row result).
-- The rarest first: small value — refund, no return. The first also gets a second line (refunded after return).
SELECT pg_temp.au_pick('decide:refund_no_return', 'refund_no_return', 'refund_no_return', 1,
         :'recent' || ' AND ' || :'decidable' || ' AND f.unit_price > 0 AND f.unit_price < p.small
           AND (f.returned + f.unit_price + p.care / 3) / f.bought <= 0.30
           AND pg_temp.au_other_item(f.line_id, p.care / 3, 1, false) IS NOT NULL') AS picked \gset au_
SELECT pg_temp.au_pick('decide:refund_no_return', 'refund_no_return', 'refund_no_return', 5,
         :'recent' || ' AND ' || :'decidable' || ' AND f.unit_price > 0 AND f.unit_price < p.small
           AND (f.returned + f.unit_price) / f.bought <= 0.30') AS picked \gset au_
-- Customer care: requests above the threshold as they stand. The first gets a second line (one task for both).
SELECT pg_temp.au_pick('decide:care', 'to_customer_care', NULL, 1,
         :'recent' || ' AND ' || :'decidable' || ' AND f.quantity * f.unit_price > p.care * 1.2
           AND (f.returned + f.quantity * f.unit_price + p.care) / f.bought <= 0.30
           AND pg_temp.au_other_item(f.line_id, p.care, 1, false) IS NOT NULL') AS picked \gset au_
SELECT pg_temp.au_pick('decide:care', 'to_customer_care', NULL, 2,
         :'recent' || ' AND ' || :'decidable' || ' AND f.quantity * f.unit_price > p.care * 1.2
           AND (f.returned + f.quantity * f.unit_price) / f.bought <= 0.30') AS picked \gset au_
-- Abuse: customers whose other 12-month orders (delivered, not yet returned) carry their share past the limit
-- once returned — the closed requests added below return them.
SELECT pg_temp.au_pick('decide:abuse', 'reject_abuse', NULL, 3,
         :'recent' || ' AND ' || :'decidable' || ' AND f.returned + (
             SELECT coalesce(sum(o.so_value), 0) FROM sales_order o
              WHERE o.so_customer_sk = f.customer AND o.so_order_number <> f.order_number AND o.so_state = ''released''
                AND o.so_delivered_date BETWEEN p.as_of - 355 AND p.as_of - 5
                AND NOT EXISTS (SELECT 1 FROM _au_rl r WHERE r.order_number = o.so_order_number)) > 0.6 * f.bought') AS picked \gset au_
-- Refund after return: the first gets two more lines (an exchange, a refund) — three lines, under care.
SELECT pg_temp.au_pick('decide:refund_after_return', 'refund_after_return', 'refund_after_return', 1,
         :'recent' || ' AND ' || :'decidable' || ' AND f.unit_price > 0 AND f.unit_price <= p.care / 3 AND f.center IS NOT NULL
           AND (f.returned + p.care) / f.bought <= 0.30
           AND pg_temp.au_other_item(f.line_id, p.care / 3, 1, true) IS NOT NULL
           AND pg_temp.au_other_item(f.line_id, p.care / 3, 2, false) IS NOT NULL') AS picked \gset au_
-- Exchange: a variant of the item's class, on stock at the customer's center (raised below).
SELECT pg_temp.au_pick('decide:exchange', 'exchange', 'exchange', 4,
         :'recent' || ' AND ' || :'decidable' || ' AND f.unit_price >= p.small AND f.unit_price <= p.care / 3 AND f.center IS NOT NULL
           AND (f.returned + f.unit_price) / f.bought <= 0.30 AND pg_temp.au_variant(f.item, f.line_id) IS NOT NULL') AS picked \gset au_
-- Replacement, no return: damaged, not small, the item on stock at the customer's center (raised below).
SELECT pg_temp.au_pick('decide:replacement_no_return', 'replacement_no_return', 'replacement_no_return', 6,
         :'recent' || ' AND ' || :'decidable' || ' AND f.unit_price >= p.small AND f.unit_price <= p.care / 3 AND f.center IS NOT NULL
           AND (f.returned + f.unit_price) / f.bought <= 0.30') AS picked \gset au_
SELECT pg_temp.au_pick('decide:refund_after_return', 'refund_after_return', 'refund_after_return', 5,
         :'recent' || ' AND ' || :'decidable' || ' AND f.unit_price > 0 AND f.unit_price <= p.care / 3
           AND (f.returned + f.unit_price) / f.bought <= 0.30') AS picked \gset au_
-- The two rejections need no margin: not ours (its request will name another customer's order), late.
SELECT pg_temp.au_pick('decide:not_ours', 'reject_not_ours', NULL, 4, :'recent') AS picked \gset au_
SELECT pg_temp.au_pick('decide:late', 'reject_late', NULL, 4,
         :'recent' || ' AND f.delivered < p.as_of - p.return_window - 2') AS picked \gset au_

-- ── monitor_inbound · 17 lines awaiting the goods (decided 35 / 20 / 10 days ago; 5 whose goods arrive today) ──
-- Half exchanges (a variant), half refunds after return; requested in the 12 days before their decision.
\set before_ 'f.requested_date BETWEEN p.as_of - '
\set variant_ ' AND pg_temp.au_variant(f.item, f.line_id) IS NOT NULL'
SELECT pg_temp.au_pick('inbound:expired', 'expired', 'exchange', 2, :'before_' || '47 AND p.as_of - 36' || :'variant_') AS picked \gset au_
SELECT pg_temp.au_pick('inbound:expired', 'expired', 'refund_after_return', 2, :'before_' || '47 AND p.as_of - 36') AS picked \gset au_
SELECT pg_temp.au_pick('inbound:remind', 'remind', 'exchange', 2, :'before_' || '32 AND p.as_of - 21' || :'variant_') AS picked \gset au_
SELECT pg_temp.au_pick('inbound:remind', 'remind', 'refund_after_return', 2, :'before_' || '32 AND p.as_of - 21') AS picked \gset au_
SELECT pg_temp.au_pick('inbound:none', 'none', 'exchange', 2, :'before_' || '22 AND p.as_of - 11' || :'variant_') AS picked \gset au_
SELECT pg_temp.au_pick('inbound:none', 'none', 'refund_after_return', 2, :'before_' || '22 AND p.as_of - 11') AS picked \gset au_
SELECT pg_temp.au_pick('inbound:complete', 'complete', 'exchange', 1, :'before_' || '19 AND p.as_of - 8' || :'variant_') AS picked \gset au_
SELECT pg_temp.au_pick('inbound:complete', 'complete', 'refund_after_return', 2, :'before_' || '19 AND p.as_of - 8') AS picked \gset au_
-- damaged: one comes back damaged, one comes back short (so it was more than one piece)
SELECT pg_temp.au_pick('inbound:damaged', 'damaged', 'refund_after_return', 2, :'before_' || '19 AND p.as_of - 8 AND f.sold_quantity >= 2') AS picked \gset au_

-- ── settle · 10 lines settling (credit notes: 3 paid today, 3 unpaid for 7 working days; shipments: 2 shipped
--    today, 2 missing for 1 working day) ─────────────────────────────────────────────────────────────────────────
\set cheap_ ' AND f.unit_price > 0 AND f.unit_price < p.small'
SELECT pg_temp.au_pick('settle:paid', 'closed,credit_note_issued,money_received', 'refund_no_return', 2,
         :'before_' || '20 AND p.as_of - 9' || :'cheap_') AS picked \gset au_
SELECT pg_temp.au_pick('settle:paid', 'closed,credit_note_issued,money_received', 'refund_after_return', 1,
         :'before_' || '26 AND p.as_of - 15') AS picked \gset au_
SELECT pg_temp.au_pick('settle:unpaid', 'credit_note_issued,money_overdue', 'refund_no_return', 1,
         'f.requested_date BETWEEN pg_temp.au_wd_before(p.as_of, p.settlement + 7) - 12 AND pg_temp.au_wd_before(p.as_of, p.settlement + 7) - 2' || :'cheap_') AS picked \gset au_
SELECT pg_temp.au_pick('settle:unpaid', 'credit_note_issued,money_overdue', 'refund_after_return', 2,
         'f.requested_date BETWEEN pg_temp.au_wd_before(p.as_of, p.settlement + 7) - 19 AND pg_temp.au_wd_before(p.as_of, p.settlement + 7) - 9') AS picked \gset au_
SELECT pg_temp.au_pick('settle:shipped', 'closed,goods_shipped', 'replacement_no_return', 1, :'before_' || '18 AND p.as_of - 7') AS picked \gset au_
SELECT pg_temp.au_pick('settle:shipped', 'closed,goods_shipped', 'exchange', 1, :'before_' || '26 AND p.as_of - 15' || :'variant_') AS picked \gset au_
SELECT pg_temp.au_pick('settle:missing', 'goods_overdue', 'replacement_no_return', 1,
         'f.requested_date BETWEEN pg_temp.au_wd_before(p.as_of, p.settlement + 1) - 12 AND pg_temp.au_wd_before(p.as_of, p.settlement + 1) - 1') AS picked \gset au_
SELECT pg_temp.au_pick('settle:missing', 'goods_overdue', 'exchange', 1,
         'f.requested_date BETWEEN pg_temp.au_wd_before(p.as_of, p.settlement + 1) - 19 AND pg_temp.au_wd_before(p.as_of, p.settlement + 1) - 8' || :'variant_') AS picked \gset au_

-- ── the planted lines' fields: what their route needs, and nothing of the history's documents ────────────────
-- A line's reason, resolution and variant agree with its way: refund/replacement no return = damaged (or
-- undelivered); exchange = wrong size, a variant; refund after return = wrong size or other. Decided lines keep
-- what was returned; received ones are one piece (care keeps its value: that is its route).
UPDATE _au_rl l SET
  quantity   = CASE WHEN h.kind IN ('decide:care', 'decide:not_ours', 'decide:late', 'decide:abuse') THEN l.quantity
                    WHEN h.kind LIKE 'decide:%' OR h.way = 'refund_no_return' THEN 1
                    WHEN h.kind = 'inbound:damaged' AND h.pick = 2 THEN 2
                    ELSE l.quantity END,
  reason     = CASE WHEN h.way IN ('refund_no_return', 'replacement_no_return')
                    THEN CASE WHEN l.reason = 'did_not_arrive' THEN 'did_not_arrive' ELSE 'damaged' END
                    WHEN h.way = 'exchange' THEN 'wrong_size'
                    WHEN h.way = 'refund_after_return' THEN CASE WHEN l.reason IN ('wrong_size', 'other') THEN l.reason ELSE 'other' END
                    ELSE l.reason END,
  resolution = CASE h.way WHEN 'refund_no_return' THEN 'refund' WHEN 'refund_after_return' THEN 'refund'
                          WHEN 'replacement_no_return' THEN 'replacement' WHEN 'exchange' THEN 'exchange' ELSE l.resolution END,
  variant    = CASE WHEN h.way = 'exchange' THEN pg_temp.au_variant(l.item, l.line_id) WHEN h.way IS NOT NULL THEN NULL ELSE l.variant END,
  state      = CASE WHEN h.kind LIKE 'decide:%' THEN 'received' WHEN h.kind LIKE 'inbound:%' THEN 'awaiting_goods'
                    WHEN h.way IN ('refund_no_return', 'replacement_no_return') THEN 'settling' ELSE 'goods_received' END,
  way        = CASE WHEN h.kind LIKE 'decide:%' THEN NULL ELSE h.way END,
  decided = NULL, rc_date = NULL, rc_ok = NULL, rc_bad = NULL, rc_bad_condition = NULL,
  cn_date = NULL, cn_status = NULL, rp_date = NULL, rs_date = NULL, rs_item = NULL
  FROM _au_h2 h WHERE h.line_id = l.line_id;

-- The decided plants' dates (the obligations P4 seeds hang on them; plan notes below record them).
UPDATE _au_rl l SET decided = CASE h.kind
    WHEN 'inbound:expired' THEN :'as_of'::date - 35 WHEN 'inbound:remind' THEN :'as_of'::date - 20
    WHEN 'inbound:none' THEN :'as_of'::date - 10 WHEN 'inbound:complete' THEN :'as_of'::date - 7 WHEN 'inbound:damaged' THEN :'as_of'::date - 7
    ELSE CASE h.kind || '/' || h.way
      WHEN 'settle:paid/refund_no_return'        THEN :'as_of'::date - 8
      WHEN 'settle:paid/refund_after_return'     THEN :'as_of'::date - 14
      WHEN 'settle:unpaid/refund_no_return'      THEN pg_temp.au_wd_before(:'as_of'::date, :p_settlement + 7) - 1
      WHEN 'settle:unpaid/refund_after_return'   THEN pg_temp.au_wd_before(:'as_of'::date, :p_settlement + 7) - 7
      WHEN 'settle:shipped/replacement_no_return' THEN :'as_of'::date - 6
      WHEN 'settle:shipped/exchange'             THEN :'as_of'::date - 14
      WHEN 'settle:missing/replacement_no_return' THEN pg_temp.au_wd_before(:'as_of'::date, :p_settlement + 1)
      WHEN 'settle:missing/exchange'             THEN pg_temp.au_wd_before(:'as_of'::date, :p_settlement + 1) - 7 END END
  FROM _au_h2 h WHERE h.line_id = l.line_id AND h.kind !~ '^decide:';

-- Receipts: today for the five whose goods arrive (complete; damaged; short), and before settling for the
-- settle lines that were returned (refund after return, exchange).
UPDATE _au_rl l SET
  rc_date = CASE WHEN h.kind IN ('inbound:complete', 'inbound:damaged') THEN :'as_of'::date
                 WHEN h.kind || '/' || h.way = 'settle:paid/refund_after_return'   THEN :'as_of'::date - 7
                 WHEN h.kind || '/' || h.way = 'settle:unpaid/refund_after_return' THEN pg_temp.au_wd_before(:'as_of'::date, :p_settlement + 7) - 1
                 WHEN h.kind || '/' || h.way = 'settle:shipped/exchange'           THEN :'as_of'::date - 6
                 WHEN h.kind || '/' || h.way = 'settle:missing/exchange'           THEN pg_temp.au_wd_before(:'as_of'::date, :p_settlement + 1) END,
  rc_ok   = CASE WHEN h.kind = 'inbound:damaged' THEN h.pick - 1 ELSE l.quantity END,          -- damaged: 0 ok · short: 1 of 2 ok
  rc_bad  = CASE WHEN h.kind = 'inbound:damaged' THEN CASE h.pick WHEN 1 THEN l.quantity ELSE 1 END ELSE 0 END,
  rc_bad_condition = CASE WHEN h.kind = 'inbound:damaged' THEN CASE h.pick WHEN 1 THEN 'damaged' ELSE 'missing' END END
  FROM _au_h2 h
 WHERE h.line_id = l.line_id
   AND (h.kind IN ('inbound:complete', 'inbound:damaged') OR (h.kind LIKE 'settle:%' AND h.way IN ('refund_after_return', 'exchange')));

-- Credit notes (paid today / unpaid since 12 working days: 5 to settle, 7 late) and shipments (today; or none).
UPDATE _au_rl l SET
  cn_date   = CASE h.kind || '/' || h.way
                WHEN 'settle:paid/refund_no_return'      THEN l.decided + 1
                WHEN 'settle:paid/refund_after_return'   THEN :'as_of'::date - 5
                WHEN 'settle:unpaid/refund_no_return'    THEN pg_temp.au_wd_before(:'as_of'::date, :p_settlement + 7)
                WHEN 'settle:unpaid/refund_after_return' THEN pg_temp.au_wd_before(:'as_of'::date, :p_settlement + 7) END,
  cn_status = CASE h.kind WHEN 'settle:paid' THEN 'paid' WHEN 'settle:unpaid' THEN 'issued' END,
  rp_date   = CASE h.kind WHEN 'settle:paid' THEN :'as_of'::date END,
  rs_date   = CASE h.kind WHEN 'settle:shipped' THEN :'as_of'::date END,
  rs_item   = CASE WHEN h.kind = 'settle:shipped' THEN CASE h.way WHEN 'exchange' THEN l.variant ELSE l.item END END
  FROM _au_h2 h WHERE h.line_id = l.line_id AND h.kind LIKE 'settle:%';

-- ── the multi-line requests: three received requests get their order's other items as lines ──────────────────
-- care + 1 (a second line: one customer-care task for the request, D-100) · refund after return + an exchange
-- + a refund (three lines, together under the care threshold) · refund no return + a refund after return.
CREATE FUNCTION pg_temp.au_add_line(p_anchor int, p_item int, p_kind text, p_route text, p_reason text, p_resolution text,
                                    p_variant boolean, p_added text) RETURNS int LANGUAGE plpgsql AS $$
DECLARE nid int;
BEGIN
  SELECT max(line_id) + 1 INTO nid FROM _au_rl;
  INSERT INTO _au_rl (line_id, request_number, line_no, request_lines, channel, order_number, item, customer, requested_date,
                      quantity, sold_quantity, unit_price, delivered, reason, resolution, variant, state, added)
  SELECT nid, a.request_number, (SELECT max(line_no) + 1 FROM _au_rl WHERE request_number = a.request_number), a.request_lines,
         a.channel, a.order_number, p_item, a.customer, a.requested_date, 1, s.sl_quantity, s.sl_unit_price, a.delivered,
         p_reason, p_resolution, CASE WHEN p_variant THEN pg_temp.au_variant(p_item, nid) END, 'received', p_added
    FROM _au_rl a JOIN sales_line s ON s.sl_order_number = a.order_number AND s.sl_item_sk = p_item
   WHERE a.line_id = p_anchor;
  IF p_kind IS NOT NULL THEN
    INSERT INTO _au_h2 (line_id, kind, route, pick) SELECT nid, p_kind, p_route, count(*) + 1 FROM _au_h2 WHERE kind = p_kind;
  END IF;
  RETURN nid;
END $$;
CREATE TEMP TABLE _au_multi ON COMMIT DROP AS
SELECT line_id AS anchor, kind FROM _au_h2 WHERE pick = 1 AND kind IN ('decide:care', 'decide:refund_after_return', 'decide:refund_no_return');
SELECT pg_temp.au_add_line(anchor, pg_temp.au_other_item(anchor, :care_threshold, 1, false), 'decide:care', 'to_customer_care', 'other', 'refund', false, 'multi_line') AS added
  FROM _au_multi WHERE kind = 'decide:care' \gset au_
SELECT pg_temp.au_add_line(anchor, pg_temp.au_other_item(anchor, :care_threshold / 3, 1, true), 'decide:exchange', 'exchange', 'wrong_size', 'exchange', true, 'multi_line') AS added
  FROM _au_multi WHERE kind = 'decide:refund_after_return' \gset au_
SELECT pg_temp.au_add_line(anchor, pg_temp.au_other_item(anchor, :care_threshold / 3, 1, false), 'decide:refund_after_return', 'refund_after_return', 'other', 'refund', false, 'multi_line') AS added
  FROM _au_multi WHERE kind = 'decide:refund_after_return' \gset au_
SELECT pg_temp.au_add_line(anchor, pg_temp.au_other_item(anchor, :care_threshold / 3, 1, false), 'decide:refund_after_return', 'refund_after_return', 'other', 'refund', false, 'multi_line') AS added
  FROM _au_multi WHERE kind = 'decide:refund_no_return' \gset au_

-- ── abuse: return whole earlier orders of the three customers (closed, refunded) until the 12-month share they
--    are judged on passes half of their purchases ───────────────────────────────────────────────────────────────
CREATE TEMP TABLE _au_abuse ON COMMIT DROP AS
WITH c AS (
  SELECT l.customer, l.order_number AS planted_order, cu.bought,
         coalesce((SELECT sum(quantity * unit_price) FROM _au_rl r WHERE r.customer = l.customer
                    AND r.requested_date >= :'as_of'::date - 365 AND r.state <> 'rejected'), 0) AS returned
    FROM _au_h2 h JOIN _au_rl l ON l.line_id = h.line_id JOIN _au_cust cu ON cu.customer = l.customer
   WHERE h.kind = 'decide:abuse'
), o AS (
  SELECT c.customer, c.bought, c.returned, o.so_order_number AS order_number, o.so_channel AS channel, o.so_delivered_date AS delivered,
         sum(o.so_value) OVER (PARTITION BY c.customer ORDER BY o.so_delivered_date DESC, o.so_order_number) AS cum, o.so_value
    FROM c JOIN sales_order o ON o.so_customer_sk = c.customer AND o.so_order_number <> c.planted_order AND o.so_state = 'released'
   WHERE o.so_delivered_date BETWEEN :'as_of'::date - 355 AND :'as_of'::date - 5
     AND NOT EXISTS (SELECT 1 FROM _au_rl r WHERE r.order_number = o.so_order_number)
)
SELECT customer, order_number, channel, delivered + 2 AS requested_date,
       (SELECT max(request_number) FROM _au_rr) + row_number() OVER (ORDER BY customer, delivered DESC, order_number) AS request_number
  FROM o WHERE cum - so_value < 0.5 * bought - returned;   -- every order until the one that crosses half

INSERT INTO _au_rr (request_number, customer, order_number, channel, requested_date)
SELECT request_number, customer, order_number, channel, requested_date FROM _au_abuse ORDER BY request_number;
INSERT INTO _au_rl (line_id, request_number, line_no, request_lines, channel, order_number, item, customer, requested_date,
                    quantity, sold_quantity, unit_price, delivered, reason, resolution, state, way, decided, added)
SELECT (SELECT max(line_id) FROM _au_rl) + row_number() OVER (ORDER BY a.request_number, s.sl_item_sk),
       a.request_number, row_number() OVER (PARTITION BY a.request_number ORDER BY s.sl_item_sk),
       count(*) OVER (PARTITION BY a.request_number), a.channel, a.order_number, s.sl_item_sk, a.customer, a.requested_date,
       s.sl_quantity, s.sl_quantity, s.sl_unit_price, o.so_delivered_date, 'other', 'refund', 'closed', 'refund_after_return',
       a.requested_date + 1, 'abuse_history'
  FROM _au_abuse a JOIN sales_line s ON s.sl_order_number = a.order_number JOIN sales_order o ON o.so_order_number = a.order_number;
SELECT count(*) FROM (SELECT pg_temp.au_settle_history()) z \gset au_

-- ── not ours: the request names an order of another customer (released; its channel) ─────────────────────────
UPDATE _au_rr r SET order_number = x.order_number, channel = x.channel
  FROM (SELECT l.request_number,
               (SELECT so_order_number FROM sales_order WHERE so_state = 'released' AND so_customer_sk <> l.customer
                 ORDER BY abs(hashtext('not_ours:' || l.line_id || ':' || so_order_number)), so_order_number LIMIT 1) AS order_number
          FROM _au_h2 h JOIN _au_rl l ON l.line_id = h.line_id WHERE h.kind = 'decide:not_ours') n
  JOIN LATERAL (SELECT n.order_number, so_channel AS channel FROM sales_order WHERE so_order_number = n.order_number) x ON true
 WHERE r.request_number = n.request_number;

-- ── the stock decide_return reads for the received lines: the item (replacement) / the variant (exchange) at the
--    customer's center covers the line (journaled, pg_temp.au_stock). Every received line's pairs are noted, so
--    40-plant.sql lowers none of them. ─────────────────────────────────────────────────────────────────────────
CREATE TEMP TABLE _au_h2stock ON COMMIT DROP AS
SELECT DISTINCT p.item, c.c_center_sk AS wh
  FROM _au_rl l JOIN customer c ON c.c_customer_sk = l.customer
 CROSS JOIN LATERAL (VALUES (l.item), (l.variant)) p(item)
 WHERE l.state = 'received' AND p.item IS NOT NULL AND c.c_center_sk IS NOT NULL;
SELECT count(*) AS stock_calls FROM (
  SELECT pg_temp.au_stock(CASE h.kind WHEN 'decide:exchange' THEN l.variant ELSE l.item END, c.c_center_sk, l.quantity,
                          l.quantity + 3 + abs(hashtext('h2stock:' || l.line_id)) % 20)
    FROM _au_h2 h JOIN _au_rl l ON l.line_id = h.line_id JOIN customer c ON c.c_customer_sk = l.customer
   WHERE h.kind IN ('decide:replacement_no_return', 'decide:exchange') ORDER BY l.line_id) z \gset au_

-- ── write ──────────────────────────────────────────────────────────────────────────────────────────────────────
INSERT INTO return_request_hdr (rr_request_number, rr_customer_sk, rr_order_number, rr_channel, rr_requested_date)
SELECT request_number, customer, order_number, channel, requested_date FROM _au_rr ORDER BY request_number;
INSERT INTO return_request_line (rl_line_id, rl_request_number, rl_line_no, rl_item_sk, rl_quantity, rl_unit_price, rl_reason,
                                 rl_requested_resolution, rl_requested_variant_sk, rl_state, rl_way, rl_customer_sk)
SELECT line_id, request_number, line_no, item, quantity, unit_price, reason, resolution, variant, state, way, customer
  FROM _au_rl ORDER BY line_id;
-- 17 §4.1's `return_share` sums a customer's request lines; `request_value` a request's
CREATE INDEX IF NOT EXISTS ix_return_request_hdr_customer ON return_request_hdr (rr_customer_sk, rr_requested_date);
CREATE INDEX IF NOT EXISTS ix_return_request_line_request ON return_request_line (rl_request_number);
ANALYZE return_request_hdr, return_request_line;

-- ── the plan (contracts §5): every H-2 plant, the route the recipe must take, and what it hangs on ──────────────
INSERT INTO _automation_plan (kind, key, note, expected_route)
SELECT h.kind, h.line_id::text,
       CASE h.kind
         WHEN 'decide:late' THEN 'delivered ' || l.delivered || '; return_window ' || :p_return_window
         WHEN 'decide:abuse' THEN 'abuse_share ' || :p_abuse_share
         WHEN 'decide:care' THEN 'care_threshold ' || :care_threshold
         WHEN 'decide:refund_no_return' THEN 'small_value ' || :small_value
         WHEN 'decide:not_ours' THEN 'order ' || r.order_number || ' is not the customer''s'
         ELSE concat_ws('; ', CASE WHEN l.decided IS NOT NULL THEN 'decided ' || l.decided END,
                        CASE WHEN h.kind LIKE 'inbound:%' THEN 'inbound due ' || (l.decided + :p_inbound_reminder) END,
                        CASE WHEN l.cn_date IS NOT NULL THEN 'credit note ' || l.cn_date END,
                        CASE WHEN h.kind = 'settle:unpaid' THEN 'payment due ' || pg_temp.au_wd_before(:'as_of'::date, 7) END,
                        CASE WHEN h.kind = 'settle:missing' THEN 'replacement due ' || pg_temp.au_wd_before(:'as_of'::date, 1) END)
       END,
       h.route
  FROM _au_h2 h JOIN _au_rl l ON l.line_id = h.line_id JOIN _au_rr r ON r.request_number = l.request_number
 ORDER BY h.kind, h.pick;
INSERT INTO _automation_plan (kind, key, note, expected_route)
SELECT 'request:multi_line', l.request_number::text, 'lines ' || string_agg(l.line_id::text, ',' ORDER BY l.line_id), NULL
  FROM _au_rl l WHERE l.request_number IN (SELECT request_number FROM _au_rl WHERE added = 'multi_line') GROUP BY l.request_number;
INSERT INTO _automation_plan (kind, key, note, expected_route)
SELECT 'request:added_line', line_id::text, added, NULL FROM _au_rl WHERE added IS NOT NULL ORDER BY line_id;
INSERT INTO _automation_plan (kind, key, note, expected_route)
SELECT 'request:abuse_history', request_number::text, 'customer ' || customer || ' returns order ' || order_number, NULL
  FROM _au_abuse ORDER BY request_number;

INSERT INTO _automation_base (fact, last_date, row_count)
SELECT 'web_returns', max(d.d_date), count(*) FROM web_returns LEFT JOIN date_dim d ON d.d_date_sk = wr_returned_date_sk
UNION ALL
SELECT 'catalog_returns', max(d.d_date), count(*) FROM catalog_returns LEFT JOIN date_dim d ON d.d_date_sk = cr_returned_date_sk;

INSERT INTO _automation_meta (step, as_of, rows) SELECT '30-returns', :'as_of', count(*) FROM return_request_line;
