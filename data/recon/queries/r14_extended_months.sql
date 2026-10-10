-- r14 — the extended months (LR-P4, contracts C-8·8): channel × month for every month from
-- 2026-01 on — revenue, orders, lines, and the returns DATED in that month. January 2026 is
-- mixed (original data to 01-02 / 01-08, extended after); every later month is extended only.
-- Feeds data/recon/R1.md. Read-only.
WITH sales AS (
  SELECT 'store' AS channel, d.d_year, d.d_moy, count(*) AS line_items,
         count(DISTINCT ss_ticket_number) AS orders, sum(ss_ext_sales_price) AS revenue
  FROM store_sales JOIN date_dim d ON ss_sold_date_sk = d.d_date_sk
  WHERE d.d_date >= DATE '2026-01-01' GROUP BY d.d_year, d.d_moy
  UNION ALL
  SELECT 'catalog', d.d_year, d.d_moy, count(*), count(DISTINCT cs_order_number), sum(cs_ext_sales_price)
  FROM catalog_sales JOIN date_dim d ON cs_sold_date_sk = d.d_date_sk
  WHERE d.d_date >= DATE '2026-01-01' GROUP BY d.d_year, d.d_moy
  UNION ALL
  SELECT 'web', d.d_year, d.d_moy, count(*), count(DISTINCT ws_order_number), sum(ws_ext_sales_price)
  FROM web_sales JOIN date_dim d ON ws_sold_date_sk = d.d_date_sk
  WHERE d.d_date >= DATE '2026-01-01' GROUP BY d.d_year, d.d_moy
), returns AS (
  SELECT 'store' AS channel, d.d_year, d.d_moy, count(*) AS return_lines, sum(sr_return_amt) AS return_amt
  FROM store_returns JOIN date_dim d ON sr_returned_date_sk = d.d_date_sk
  WHERE d.d_date >= DATE '2026-01-01' GROUP BY d.d_year, d.d_moy
  UNION ALL
  SELECT 'catalog', d.d_year, d.d_moy, count(*), sum(cr_return_amount)
  FROM catalog_returns JOIN date_dim d ON cr_returned_date_sk = d.d_date_sk
  WHERE d.d_date >= DATE '2026-01-01' GROUP BY d.d_year, d.d_moy
  UNION ALL
  SELECT 'web', d.d_year, d.d_moy, count(*), sum(wr_return_amt)
  FROM web_returns JOIN date_dim d ON wr_returned_date_sk = d.d_date_sk
  WHERE d.d_date >= DATE '2026-01-01' GROUP BY d.d_year, d.d_moy
)
SELECT s.channel, s.d_year, s.d_moy, s.line_items, s.orders, round(s.revenue) AS revenue,
       coalesce(r.return_lines, 0) AS return_lines, round(coalesce(r.return_amt, 0)) AS return_amt
FROM sales s LEFT JOIN returns r USING (channel, d_year, d_moy)
ORDER BY s.channel, s.d_year, s.d_moy;
