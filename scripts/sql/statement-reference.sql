-- IA-P4·S4.3·T6 — `portfolio-statement:v1`'s Transactions and Cash, computed on the book with plain PostgreSQL: the
-- reference those two sheets are fingerprinted against (IA-C51; `scripts/fingerprint-overview.sh`). The statement's
-- Evolution sheet is `investment-evolution:v2`'s Periods, so it is held to `evolution-reference.sql` beside this one.
--
-- ## What it mirrors (contracts IA-C50, IE-C25) — written from the rules
--
--   * Transactions: the effective ledger (the substrate's reversal pairs dropped; Conseq stornos stay, each a row) of
--     the portfolio in the window `from` … `as_of`, every leg, as stored;
--   * Cash: the cash leg alone (never the external-flow leg beside it), per currency, to the as_of.
--
-- ## Use
--
--   psql "$DSN" -X -q --csv -v ON_ERROR_STOP=1 -v portfolio=conseq:… -v from=YYYY-MM-DD -v as_of=YYYY-MM-DD \
--        -f scripts/sql/statement-reference.sql
--
-- One read-only statement: `kind` = `transaction` rows (by trade day, then id) and `cash` rows (by currency).

WITH prm AS (
    SELECT CAST(:'portfolio' AS TEXT) AS pid, CAST(:'from' AS DATE) AS from_day, CAST(:'as_of' AS DATE) AS as_of
), effective AS (
    SELECT t.* FROM investment_transaction t, prm
     WHERE t.portfolio_ref = prm.pid
       AND t.reversal_of IS NULL
       AND NOT EXISTS (SELECT 1 FROM investment_transaction r WHERE r.reversal_of = t.external_id)
)
SELECT 'transaction' AS kind, e.external_id AS transaction_id, e.trade_date, e.leg, e.operation,
       trim(e.asset_ref) AS asset_id, e.quantity, e.amount, e.currency, NULL::numeric AS balance
  FROM effective e, prm
 WHERE e.trade_date >= prm.from_day AND e.trade_date <= prm.as_of
UNION ALL
SELECT 'cash', NULL, NULL, NULL, NULL, NULL, NULL, NULL, e.currency,
       SUM(CASE WHEN e.operation = 'credit' THEN abs(e.amount) WHEN e.operation = 'debit' THEN -abs(e.amount) ELSE 0 END)
  FROM effective e, prm
 WHERE e.leg = 'cash' AND e.trade_date <= prm.as_of
 GROUP BY e.currency
 ORDER BY 1 DESC, 3, 2, 9;
