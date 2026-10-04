-- IA-P4·S4.3·T6 — `client-overview:v1` and `distributor-overview:v1`, per open portfolio, computed on the book with plain
-- PostgreSQL: the reference both workbooks' Portfolios sheets are fingerprinted against (IA-C51;
-- `scripts/fingerprint-overview.sh`).
--
-- ## What it mirrors (contracts IA-C41 v1.9, IA-C67, IA-C70, IA-C73) — written from the rules, not from the program
--
--   * a portfolio is its OPEN version (`valid_to IS NULL`) — of one client, or for the whole book every OPEN client's
--     (a client is its open version too): the book is its open clients, each with its open portfolios. An open client
--     with no open portfolio still counts among the book's clients (`open_clients`, the same on every row); an open
--     portfolio whose client has no open version is not on the book (IA-P4 review R14);
--   * market value: the provider's latest position valuation on or before the as_of, summed, converted from the
--     portfolio's base currency into the home currency at the as_of's rate;
--   * cash: the effective ledger's cash leg (the substrate's reversal pairs dropped) to the as_of, EVERY currency,
--     each converted at the as_of's rate; one non-zero balance with no rate leaves the total empty;
--   * value: the provider's total (`investment_portfolio_valuation`, holdings + cash) at its latest point on or before
--     the as_of, converted at the as_of's rate — and the same at the last quarter end BEFORE the as_of (a quarter end
--     compares with the one before it); the change between them in percent.
--
-- Rates: the latest `investment_fx_rate` on or before the day, per unit, the home currency at 1 (IA-C66). No rate is no
-- figure — never a guess.
--
-- ## Use
--
--   psql "$DSN" -X -q --csv -v ON_ERROR_STOP=1 -v client=conseq:… -v as_of=YYYY-MM-DD -f scripts/sql/overview-reference.sql
--   psql "$DSN" -X -q --csv -v ON_ERROR_STOP=1 -v client= -v as_of=YYYY-MM-DD -f …   # the whole book
--
-- One read-only statement (the drill's session is a read-only one). One row per open portfolio, UNROUNDED, each
-- carrying `open_clients` — the book's open clients, counted whether or not they hold an open portfolio.

WITH prm AS (
    SELECT CAST(:'as_of' AS DATE) AS as_of,
           NULLIF(CAST(:'client' AS TEXT), '') AS client
), days AS (
    SELECT 'now' AS d, as_of AS day FROM prm
    UNION ALL
    -- the last quarter end before the as_of: 06-30 for 09-15 and for 09-30, 09-30 for 10-02
    SELECT 'prev', CAST(date_trunc('quarter', as_of) AS DATE) - 1 FROM prm
), home AS (
    SELECT (SELECT home_currency FROM investment_estate_setting LIMIT 1) AS home
), portfolio AS (
    SELECT p.external_id AS pid, p.client_ref AS client_id, p.base_currency AS base
      FROM investment_portfolio p, prm
     WHERE p.valid_to IS NULL
       AND (CASE WHEN prm.client IS NULL
                 THEN p.client_ref IN (SELECT c.external_id FROM investment_client c WHERE c.valid_to IS NULL)
                 ELSE p.client_ref = prm.client END)
), open_clients AS (
    SELECT COUNT(DISTINCT c.external_id) AS n FROM investment_client c WHERE c.valid_to IS NULL
), rate AS (
    -- what one unit of `cur` is worth in the home currency on each day; the home currency at 1
    SELECT d.d, c.cur,
           CASE WHEN c.cur = (SELECT home FROM home) THEN 1::numeric
                ELSE (SELECT r.rate / r.units FROM investment_fx_rate r
                       WHERE r.currency = c.cur AND r.rate_date <= d.day
                       ORDER BY r.rate_date DESC LIMIT 1) END AS rate
      FROM days d
     CROSS JOIN (SELECT DISTINCT base AS cur FROM portfolio WHERE base IS NOT NULL
                 UNION SELECT DISTINCT currency FROM investment_transaction WHERE currency IS NOT NULL
                 UNION SELECT DISTINCT currency FROM investment_portfolio_valuation) c
), effective AS (
    SELECT t.* FROM investment_transaction t
     WHERE t.reversal_of IS NULL
       AND NOT EXISTS (SELECT 1 FROM investment_transaction r WHERE r.reversal_of = t.external_id)
), market AS (
    SELECT p.pid, SUM(v.market_value) AS mv
      FROM portfolio p
      JOIN LATERAL (SELECT MAX(l.valuation_date) AS day FROM investment_position l, prm
                     WHERE l.portfolio_ref = p.pid AND l.valid_to IS NULL AND l.valuation_date <= prm.as_of) lv ON TRUE
      JOIN investment_position v ON v.portfolio_ref = p.pid AND v.valuation_date = lv.day AND v.valid_to IS NULL
     GROUP BY p.pid
), cash AS (
    SELECT e.portfolio_ref AS pid, e.currency,
           SUM(CASE WHEN e.operation = 'credit' THEN abs(e.amount) WHEN e.operation = 'debit' THEN -abs(e.amount) ELSE 0 END) AS balance
      FROM effective e, prm
     WHERE e.leg = 'cash' AND e.trade_date <= prm.as_of AND e.portfolio_ref IN (SELECT pid FROM portfolio)
     GROUP BY e.portfolio_ref, e.currency
), cash_rc AS (
    SELECT c.pid,
           CASE WHEN bool_or(c.balance <> 0 AND r.rate IS NULL) THEN NULL
                ELSE SUM(CASE WHEN c.balance = 0 THEN 0 ELSE c.balance * r.rate END) END AS cash_rc
      FROM cash c
      LEFT JOIN rate r ON r.d = 'now' AND r.cur = c.currency
     GROUP BY c.pid
), point AS (
    SELECT p.pid, d.d, pv.value, pv.currency
      FROM portfolio p
     CROSS JOIN days d
      JOIN LATERAL (SELECT v.value, v.currency FROM investment_portfolio_valuation v
                     WHERE v.portfolio_ref = p.pid AND v.valuation_date <= d.day
                     ORDER BY v.valuation_date DESC LIMIT 1) pv ON TRUE
), value_rc AS (
    SELECT pt.pid, pt.d,
           CASE WHEN pt.value = 0 OR pt.currency = (SELECT home FROM home) THEN pt.value ELSE pt.value * r.rate END AS v
      FROM point pt
      LEFT JOIN rate r ON r.d = pt.d AND r.cur = pt.currency
)
SELECT p.client_id,
       p.pid AS portfolio_id,
       CASE WHEN m.mv IS NULL THEN NULL
            WHEN m.mv = 0 OR p.base = (SELECT home FROM home) THEN m.mv
            ELSE m.mv * rb.rate END AS market_value_rc,
       cr.cash_rc,
       vn.v AS value_rc,
       vq.v AS value_prev_quarter_end,
       (vn.v / NULLIF(vq.v, 0) - 1) * 100 AS chg_qoq_pct,
       (SELECT n FROM open_clients) AS open_clients
  FROM portfolio p
  LEFT JOIN market m ON m.pid = p.pid
  LEFT JOIN rate rb ON rb.d = 'now' AND rb.cur = p.base
  LEFT JOIN cash_rc cr ON cr.pid = p.pid
  LEFT JOIN value_rc vn ON vn.pid = p.pid AND vn.d = 'now'
  LEFT JOIN value_rc vq ON vq.pid = p.pid AND vq.d = 'prev'
 ORDER BY p.client_id, p.pid;
