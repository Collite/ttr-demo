-- AU-hartland P1 · S1.3 — the golden seeds (contracts §5, §7): one row per planted key and route of every recipe,
-- with 17's `because:` (its {fills} left in: the seed compares after filling) and the rows each detail context
-- carries. run-automation.sh writes them to expected/<world>/<recipe>.csv after the build; P2 seeds the
-- `tests/*.yaml` of each recipe from them (no `pinned_from`: a seed), P3 pins goldens from debug runs.
--   A `none` route (monitor_inbound inside its window; a win-back customer mailed inside the mail window) is a row
--   too: the seed asserts the key gets NO verdict row.
INSERT INTO _automation_expected (recipe, key, route, verdict_reason_template, detail_count)
SELECT CASE split_part(p.kind, ':', 1)
         WHEN 'release' THEN 'release_order' WHEN 'decide' THEN 'decide_return' WHEN 'inbound' THEN 'monitor_inbound'
         WHEN 'settle' THEN 'settle' WHEN 'reorder' THEN 'reorder_proposals' WHEN 'winback' THEN 'winback' END,
       p.key, r.route,
       -- 17 §3–§4's because: strings (H-3 and H-5 have none yet: their recipes are P2's)
       coalesce(CASE r.route
         WHEN 'hold_sales' THEN 'stock shortfall or price difference'
         WHEN 'hold_ar' THEN 'overdue invoices'
         WHEN 'release_confirmed' THEN 'all checks passed; above the confirmation threshold'
         WHEN 'release' THEN 'all checks passed'
         WHEN 'reject_not_ours' THEN 'not bought here'
         WHEN 'reject_late' THEN 'delivered more than {return_window} days ago'
         WHEN 'reject_abuse' THEN 'return share {share} above the limit'
         WHEN 'to_customer_care' THEN 'request above the care threshold'
         WHEN 'refund_no_return' THEN 'small value, {reason}'
         WHEN 'replacement_no_return' THEN '{reason}, replacement on stock'
         WHEN 'exchange' THEN 'requested variant on stock'
         WHEN 'refund_after_return' THEN 'goods back, then the money'
         WHEN 'complete' THEN 'returned in full'
         WHEN 'damaged' THEN 'incomplete or damaged return'
         WHEN 'expired' THEN 'nothing returned after {inbound_close} days'
         WHEN 'remind' THEN 'nothing returned after {inbound_reminder} days'
         WHEN 'credit_note_issued' THEN 'credit note {credit_note_id} issued'
         WHEN 'money_received' THEN 'refund paid on {paid_date}'
         WHEN 'goods_shipped' THEN 'replacement shipped on {shipped_date}'
         WHEN 'money_overdue' THEN 'refund {max_late} working days late'
         WHEN 'goods_overdue' THEN 'replacement {max_late} working days late'
         WHEN 'closed' THEN 'settled' END, NULL),
       -- the route's detail contexts (17: `detail:`), `context:rows`
       coalesce(CASE
         WHEN r.route = 'hold_sales' THEN 'shortfall:' || x.n_short || ' price_differences:' || x.n_price
         WHEN r.route = 'hold_ar' THEN 'overdue:' || x.n_due
         WHEN r.route IN ('complete', 'damaged') THEN 'receipts:' || (SELECT count(*) FROM return_receipt WHERE rc_line_id::text = p.key)
         WHEN r.route IN ('money_overdue', 'goods_overdue') THEN 'open_obligations:1'   -- the obligation P4 seeds
       END, NULL)
  FROM _automation_plan p
 CROSS JOIN LATERAL string_to_table(p.expected_route, ',') r(route)
  LEFT JOIN _au_release_replay x ON x.key = p.key AND p.kind LIKE 'release:%'
 WHERE p.kind ~ '^(release|decide|inbound|settle|reorder|winback):';

INSERT INTO _automation_meta (step, as_of, rows) SELECT '50-expected', :'as_of', count(*) FROM _automation_expected;
