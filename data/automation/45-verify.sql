-- AU-hartland P1 · S1.2 — the build checks its own plants before it commits: the recipes, replayed over the world
-- just built, must route every key exactly as _automation_plan says — and route no key the plan does not name.
-- A real world differs from the test fixture in a thousand ways the picks cannot all foresee; a disagreement here
-- fails the build (the transaction rolls back) instead of leaving a demo day that says something else.
--   release_order (17 §3, every candidate) · decide_return (17 §4.1, every received line) · H-3's cover rule.
-- monitor_inbound and settle read obligations, which exist from P4 on; their plants are checked by the suite.
CREATE TEMP TABLE _au_verify (recipe text, key text, planned text, replayed text) ON COMMIT DROP;

-- 17 §3, end to end
INSERT INTO _au_verify
WITH o AS (SELECT so_order_number, so_customer_sk, so_channel, so_placed_date, so_value FROM sales_order WHERE so_state IN ('placed', 'held')),
     lt AS (SELECT l.item, l.wh, i.inv_quantity_on_hand AS q FROM _au_inv_latest l
              JOIN inventory i ON i.inv_date_sk = l.date_sk AND i.inv_item_sk = l.item AND i.inv_warehouse_sk = l.wh),
     out_ AS (SELECT DISTINCT wo_warehouse_sk FROM warehouse_outage WHERE wo_from_date <= :'as_of'::date AND wo_to_date >= :'as_of'::date),
     short AS (SELECT s.sl_order_number k, count(*) n FROM o JOIN sales_line s ON s.sl_order_number = o.so_order_number
                 LEFT JOIN lt ON lt.item = s.sl_item_sk AND lt.wh = s.sl_warehouse_sk
                 LEFT JOIN out_ ON out_.wo_warehouse_sk = s.sl_warehouse_sk
                WHERE out_.wo_warehouse_sk IS NOT NULL OR coalesce(lt.q, 0) < s.sl_quantity GROUP BY 1),
     price AS (SELECT s.sl_order_number k, count(*) n FROM o JOIN sales_line s ON s.sl_order_number = o.so_order_number
                 LEFT JOIN customer_price cp ON cp.cp_item_sk = s.sl_item_sk AND cp.cp_customer_sk = o.so_customer_sk
                      AND cp.cp_valid_from <= o.so_placed_date AND (cp.cp_valid_to IS NULL OR cp.cp_valid_to >= o.so_placed_date)
                 LEFT JOIN price_list pl ON pl.pl_item_sk = s.sl_item_sk AND pl.pl_channel = o.so_channel
                      AND pl.pl_valid_from <= o.so_placed_date AND (pl.pl_valid_to IS NULL OR pl.pl_valid_to >= o.so_placed_date)
                WHERE coalesce(cp.cp_price, pl.pl_price) IS NULL OR abs(s.sl_unit_price - coalesce(cp.cp_price, pl.pl_price)) > :p_tolerance
                GROUP BY 1),
     due AS (SELECT o.so_order_number k, count(*) n FROM o JOIN invoice i ON i.inv_customer_sk = o.so_customer_sk
              WHERE i.inv_status = 'open' AND i.inv_due < :'as_of'::date GROUP BY 1),
     r AS (SELECT o.so_order_number::text AS key, array_to_string(array_remove(ARRAY[
             CASE WHEN coalesce(d.n, 0) > 0 THEN 'hold_ar' END,
             CASE WHEN coalesce(sh.n, 0) + coalesce(pr.n, 0) > 0 THEN 'hold_sales' END,
             CASE WHEN coalesce(sh.n, 0) + coalesce(pr.n, 0) + coalesce(d.n, 0) = 0 AND o.so_value <= :confirmation_threshold THEN 'release' END,
             CASE WHEN coalesce(sh.n, 0) + coalesce(pr.n, 0) + coalesce(d.n, 0) = 0 AND o.so_value > :confirmation_threshold THEN 'release_confirmed' END], NULL), ',') AS route
             FROM o LEFT JOIN short sh ON sh.k = o.so_order_number LEFT JOIN price pr ON pr.k = o.so_order_number
             LEFT JOIN due d ON d.k = o.so_order_number),
     pl AS (SELECT key, expected_route AS route FROM _automation_plan WHERE kind LIKE 'release:%')
SELECT 'release_order', coalesce(pl.key, r.key), pl.route, r.route
  FROM pl FULL JOIN r ON r.key = pl.key WHERE pl.route IS DISTINCT FROM r.route;

-- 17 §4.1, end to end
INSERT INTO _au_verify
WITH q AS (SELECT l.rl_line_id line_id, l.rl_request_number request_number, l.rl_item_sk item, l.rl_quantity quantity,
                  l.rl_quantity * l.rl_unit_price line_value, l.rl_reason reason, l.rl_requested_resolution resolution,
                  l.rl_requested_variant_sk variant, r.rr_customer_sk customer, r.rr_order_number order_number
             FROM return_request_line l JOIN return_request_hdr r ON r.rr_request_number = l.rl_request_number
            WHERE l.rl_state = 'received'),
     b AS (SELECT q.line_id, o.so_delivered_date delivered,
                  CASE WHEN o.so_delivered_date >= :'as_of'::date - :p_return_window THEN 1 ELSE 0 END in_window,
                  CASE WHEN s.sl_item_sk IS NULL THEN 0 ELSE 1 END on_order
             FROM q LEFT JOIN sales_order o ON o.so_order_number = q.order_number AND o.so_customer_sk = q.customer
             LEFT JOIN sales_line s ON s.sl_order_number = q.order_number AND s.sl_item_sk = q.item),
     sh AS (SELECT q.line_id,
                   coalesce((SELECT sum(rl.rl_quantity * rl.rl_unit_price) FROM return_request_line rl
                               JOIN return_request_hdr rr ON rr.rr_request_number = rl.rl_request_number
                              WHERE rr.rr_customer_sk = q.customer AND rr.rr_requested_date >= :'as_of'::date - 365 AND rl.rl_state <> 'rejected'), 0)
                   / nullif((SELECT sum(s.sl_ext_sales_price) FROM sales_line s
                              WHERE s.sl_customer_sk = q.customer AND s.sl_sold_date >= :'as_of'::date - 365), 0) AS share
              FROM q),
     rv AS (SELECT rl_request_number request_number, sum(rl_quantity * rl_unit_price) request_value FROM return_request_line GROUP BY 1),
     st AS (SELECT q.line_id, pg_temp.au_stock_of(q.item, c.c_center_sk) item_on_hand,
                   CASE WHEN q.variant IS NULL THEN 0 ELSE pg_temp.au_stock_of(q.variant, c.c_center_sk) END variant_on_hand
              FROM q JOIN customer c ON c.c_customer_sk = q.customer),
     r AS (SELECT q.line_id::text AS key, CASE
             WHEN b.delivered IS NULL OR b.on_order = 0 THEN 'reject_not_ours'
             WHEN b.in_window = 0 THEN 'reject_late'
             WHEN sh.share > :p_abuse_share THEN 'reject_abuse'
             WHEN rv.request_value > :care_threshold THEN 'to_customer_care'
             WHEN q.line_value < :small_value AND q.reason IN ('damaged', 'did_not_arrive') THEN 'refund_no_return'
             WHEN q.reason IN ('damaged', 'did_not_arrive') AND st.item_on_hand >= q.quantity THEN 'replacement_no_return'
             WHEN q.resolution = 'exchange' AND st.variant_on_hand >= q.quantity THEN 'exchange'
             ELSE 'refund_after_return' END AS route
             FROM q JOIN b USING (line_id) JOIN sh USING (line_id) JOIN st USING (line_id) JOIN rv ON rv.request_number = q.request_number),
     pl AS (SELECT key, expected_route AS route FROM _automation_plan WHERE kind LIKE 'decide:%')
SELECT 'decide_return', coalesce(pl.key, r.key), pl.route, r.route
  FROM pl FULL JOIN r ON r.key = pl.key WHERE pl.route IS DISTINCT FROM r.route;

-- H-3's cover rule
INSERT INTO _au_verify
WITH r AS (SELECT d.item || ':' || d.wh AS key FROM _au_demand d
            WHERE pg_temp.au_stock_of(d.item, d.wh) < :p_reorder_cover_weeks * d.weekly),
     pl AS (SELECT key FROM _automation_plan WHERE kind = 'reorder:propose')
SELECT 'reorder_proposals', coalesce(pl.key, r.key), CASE WHEN pl.key IS NOT NULL THEN 'propose' END, CASE WHEN r.key IS NOT NULL THEN 'propose' END
  FROM pl FULL JOIN r ON r.key = pl.key WHERE pl.key IS NULL OR r.key IS NULL;

DO $$
DECLARE n int; sample text;
BEGIN
  SELECT count(*), string_agg(format('%s %s: planned %s, replayed %s', recipe, key, coalesce(planned, '(nothing)'), coalesce(replayed, '(nothing)')), '; ')
    INTO n, sample FROM (SELECT * FROM _au_verify ORDER BY recipe, key LIMIT 10) v;
  IF n > 0 THEN
    RAISE EXCEPTION 'automation_verify: % key(s) replay differently from the plan (first ten: %)', (SELECT count(*) FROM _au_verify), sample;
  END IF;
END $$;

INSERT INTO _automation_meta (step, as_of, rows)
SELECT '45-verify', :'as_of', count(*) FROM _automation_plan WHERE kind ~ '^(release|decide|reorder):';
