-- AU-hartland P1 · S1.1 — a handful of outages per distribution center (README.md "Outages"): :outages_per_center
-- windows of 1–3 days in the template year, one in each equal part of it (so a center's windows never
-- overlap), a hashed reason code. None lies over the demo day: S1.2 plants that one (`hold_sales` × 2).
INSERT INTO warehouse_outage (wo_warehouse_sk, wo_from_date, wo_to_date, wo_reason)
SELECT w.w_warehouse_sk, f.from_date,
       f.from_date + abs(hashtext(w.w_warehouse_sk || ':outage-days:' || n)) % 3,
       (ARRAY['power_failure', 'system_outage', 'stock_count'])[1 + abs(hashtext(w.w_warehouse_sk || ':outage-why:' || n)) % 3]
  FROM warehouse w
 CROSS JOIN generate_series(1, :outages_per_center) n
 CROSS JOIN LATERAL (
   SELECT make_date(:template_year, 1, 1) + (n - 1) * (365 / :outages_per_center)
          + abs(hashtext(w.w_warehouse_sk || ':outage:' || n)) % (365 / :outages_per_center - 3) AS from_date) f
 ORDER BY 1, 2;

INSERT INTO _automation_meta (step, as_of, rows) SELECT '23-outages', :'as_of', count(*) FROM warehouse_outage;
