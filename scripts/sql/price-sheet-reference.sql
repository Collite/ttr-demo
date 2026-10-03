-- IA-P4·S4.3·T6 — `price-sheet:v1`'s Prices, computed on the book with plain PostgreSQL: the reference its workbook is
-- fingerprinted against (IA-C51; `scripts/fingerprint-overview.sh`).
--
-- ## What it mirrors (contracts IA-C36 (1) (3), v1.8 S3.1·D7) — written from the rules, not from `price_matrix`
--
--   * the rows: every instrument of the latest valuations on or before the as_of (each portfolio's latest
--     `investment_position` day), not every instrument the price table knows;
--   * the columns: the as_of, and the end of each of the `months − 1` months before the as_of's month;
--   * a cell: the latest price on or before its day, in the instrument's own currency; none before the first price.
--
-- ## Use
--
--   psql "$DSN" -X -q --csv -v ON_ERROR_STOP=1 -v as_of=YYYY-MM-DD -v months=24 -f scripts/sql/price-sheet-reference.sql
--
-- One read-only statement. One row per instrument and day (long, not pivoted), UNROUNDED.

WITH prm AS (
    SELECT CAST(:'as_of' AS DATE) AS as_of, LEAST(GREATEST(CAST(:'months' AS INT), 1), 24) AS months
), grid AS (
    SELECT i, CASE WHEN i = 0 THEN prm.as_of
                   ELSE CAST(date_trunc('month', prm.as_of) - make_interval(months => i - 1) AS DATE) - 1 END AS day
      FROM prm, generate_series(0, prm.months - 1) AS i
), latest AS (
    SELECT l.portfolio_ref, MAX(l.valuation_date) AS day
      FROM investment_position l, prm
     WHERE l.valid_to IS NULL AND l.valuation_date <= prm.as_of
     GROUP BY l.portfolio_ref
), valued AS (
    SELECT DISTINCT v.asset_ref AS isin
      FROM investment_position v
      JOIN latest lv ON lv.portfolio_ref = v.portfolio_ref AND lv.day = v.valuation_date
     WHERE v.valid_to IS NULL
)
SELECT trim(a.isin) AS asset_id, g.day, p.price, p.currency
  FROM valued a
 CROSS JOIN grid g
  LEFT JOIN LATERAL (SELECT ap.price, ap.currency FROM investment_asset_price ap
                      WHERE ap.isin = a.isin AND ap.price_date <= g.day
                      ORDER BY ap.price_date DESC LIMIT 1) p ON TRUE
 ORDER BY asset_id, g.day;
