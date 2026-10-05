-- IA-P4·S4.2·T5 — the period evolution of ONE portfolio, computed on the book with plain PostgreSQL: the reference the
-- `investment-evolution:v2` workbook is fingerprinted against (IA-C51; `scripts/fingerprint-evolution.sh`).
--
-- ## Why a second implementation, and why here
--
-- The renderer assembles the evolution in Kotlin from door answers (kantheon `PeriodEvolution`): the door has no
-- recursion, and an average cost is recursive. This file computes the same rows straight from the tables, with a
-- recursive CTE — allowed here, because this is not the door. The two share no code and no query, so where they agree
-- on a real book, each is the other's check.
--
-- ## What it mirrors (contracts IA-C45…C48 v1.18, ruled 2026-10-02) — AVERAGE cost only
--
--   * the effective ledger (the substrate's reversal pairs dropped) from the portfolio's first movement;
--   * Conseq stornos: a `reversal-of-buy`/`-of-sell` paired with the latest unpaired `buy`/`sell` of the same
--     instrument, units and amount dated ON OR BEFORE its day — a same-day original pairs whatever the ids' order (IA-P4
--     review R3) — both dropped from the cost basis (an unpaired one is the opposite trade);
--   * the order within a day (R3): the door answers a day in `external_id` order, which is not the order things
--     happened (`…:RED:…`, `…:SST:…` sort before `…:SUB:…`), so the basis takes a day's security INFLOWS (buy,
--     transfer-in, an unpaired reversal-of-sell) before its OUTFLOWS (sell, transfer-out, payout, an unpaired
--     reversal-of-buy), each in the door's order; settling trades are read newest-first, the reverse of that order;
--   * units the ledger does not explain (S4.1·D2, IA-C46 v1.25): the provider counts a movement when it SETTLES, so its
--     latest valuation is held against the ledger SETTLED by that day — a movement counts on its `settlement_date`, else
--     its deal day, sales, transfers and payouts as much as buys — read past `as_of` when the valuation is later (R1;
--     the window itself never reads past `as_of`). Only a movement with NO settlement day can still be settling unseen:
--     a difference the newest of those dealt in the 20 days before the valuation cancel is no gap; a movement with a
--     settlement day is decided by it (the IA-P4b review's R7). Such an instrument — and one whose units fall below
--     zero before the window — starts the window at its opening market value, its cost UNKNOWN (NULL) when it has no
--     price on the opening (R9): NULL then runs through invested, unrealized, the cost of what leaves, realized,
--     fx_realized and unexplained — not a missing rate, never 0;
--   * each lot's cost in the reporting currency R and the price currency F, so `fx_realized` / `fx_unrealized` split;
--   * market value on the DOOR's units (+ the gap − storno'd originals still outstanding), unrealized on the TRACKED
--     units; cash = the cash leg per currency; `fx_cash` its revaluation; the `unexplained` identity;
--   * income and fees by the provider's LABEL (IA-C55, IA-P4b·S4b.2): each cash and external-flow movement of the window
--     classified with `income-labels.yaml` — the SAME table the renderer packages, synced with the model and handed in
--     as `:labels` (`scripts/lib/income_labels.py sql`). The label normalised as the table spells it (whitespace runs
--     one space, lower case, the text after the LAST ", ", no trailing ` ident. …`); an exact entry first, else the
--     longest prefix; an entry's `leg` restricts it. An external-flow movement classed `fee` LEAVES deposits/withdrawals
--     for `fees` (a withdrawal +, a deposit — a refund — −); dividend/coupon/interest leave them for `income` (deposit +,
--     withdrawal −). A cash movement classed so is shown in `fees` (debit +) or `income` (credit +) and STAYS in
--     `cash_movements` — the identity never moves — UNLESS its external-flow twin carries the same payment (IA-C55
--     v1.25, the IA-P4b review's R1: a cash-account contract's fee arrives on both legs), then the flow counts it, once.
--     Twins: the provider's ids (`…:CASH:<T>:<Id>` is the same payment as `…:DEP:<T><Id>`), else, for a flow with no
--     provider id (`…:DEP:H:…`, or not from the provider), the same day, signed amount, currency and class; each flow
--     twins one cash movement at most, and a twin of another class is none. `labelled` says whether IA-C49's footnotes
--     drop: the book has the `label` column AND every cash/external-flow movement of the window carries one;
--   * the security leg's `fee` (IA-C55 v1.26): the provider's record of a trade's fee, stated in the estate's HOME
--     currency, which mostly arrives as a movement of its own as well (`"<fund>, Vstupní poplatek"` around the
--     settlement day). It is added to `fees` — converted from home to R at its deal day's rate, in the period of its
--     deal day — UNLESS a movement RECORDS it: a cash or external-flow movement that counts in `fees` already (classed
--     fee: any external-flow one, a cash one with no flow twin) or that the table cannot classify (no label, or one it
--     does not know); never one the table knows as another class. A recorder is dated from 3 days before the deal to 7
--     days after the settlement day (the deal day when it has none), and pays the same money: a withdrawal or a cash
--     debit its amount, a deposit or a cash credit minus it — equal to the fee when in the home currency, within 1 % of
--     it when converted from another at the recorder's own day's rate (no rate: no match). One movement records one
--     fee: the fees of the whole ledger to as_of in (deal day, id) order, each taking the untaken recorder nearest its
--     settlement day, then the earlier, then the lower id — so a fee is decided alike whatever the window. A book
--     without the `label` column adds none (nothing can be told apart).
--
-- ⚑ Lower case in a C-locale database (hartland's `entry` is one, and so is every reference container): a C ctype
-- folds ASCII only — `lower('ÚROKY Z PRODLENÍ')` is `Úroky z prodlenÍ` — so the label is lowered under the ICU root
-- collation, `COLLATE "und-x-icu"`, the Unicode folding the renderer's `lowercase()` does (the postgres:16 image and
-- CloudNativePG's are built with ICU; a server without it refuses the statement, naming the collation — never a
-- silent misclassification).
--
-- Rates: the latest `investment_fx_rate` on or before the day, per unit, the home currency at 1 (IA-C66). R is the
-- portfolio's reporting currency, else the home currency. Prices: the latest price on or before the day (IA-C36 (3)).
--
-- ## Use
--
--   psql "$DSN" -X -q --csv -v ON_ERROR_STOP=1 \
--        -v portfolio=conseq:… -v from=YYYY-MM-DD -v as_of=YYYY-MM-DD -v grain=month|quarter \
--        -v labels="$(python3 scripts/lib/income_labels.py sql model/investment/income-labels.yaml)" \
--        -f scripts/sql/evolution-reference.sql
--
-- One statement, read-only (no temporary object — the drill's session is a read-only one). One row per period, in the
-- Periods sheet's column names, UNROUNDED (the comparison rounds both sides; a total built from rounded rows would
-- carry their rounding); `refused` and `labelled` are the same on every row — `refused` empty, or why this book cannot
-- be compared (the
-- renderer refuses the same cases — `incomplete_ledger`). `unconverted` / `missing_rate` are not computed (so R15's
-- "each boundary once" has nothing to count here): a window with an amount the rates cannot convert is not
-- fingerprinted (the script checks the workbook's count is 0). An unknown COST is not a missing rate: its NULLs are
-- compared as NULLs.

WITH RECURSIVE
prm AS (
    SELECT CAST(:'portfolio' AS TEXT) AS pid,
           CAST(:'as_of' AS DATE)     AS as_of,
           CASE WHEN :'grain' = 'quarter' THEN 3 ELSE 1 END AS step,
           CAST(date_trunc(CASE WHEN :'grain' = 'quarter' THEN 'quarter' ELSE 'month' END, CAST(:'from' AS DATE)) AS DATE)
               AS first_start
),
opening AS (
    SELECT first_start - 1 AS opening FROM prm
),
grid AS (
    SELECT CAST(s AS DATE) AS period_start,
           LEAST(CAST(s + make_interval(months => prm.step) - INTERVAL '1 day' AS DATE), prm.as_of) AS period_end,
           CASE WHEN prm.step = 1 THEN to_char(s, 'YYYY-MM')
                ELSE to_char(s, 'YYYY') || '-Q' || EXTRACT(QUARTER FROM s) END AS period
    FROM prm,
         generate_series(CAST(prm.first_start AS TIMESTAMP), CAST(prm.as_of AS TIMESTAMP), make_interval(months => prm.step)) AS s
),
spans AS (
    -- each period with the boundary it opens on: the window's opening, then the previous period's end
    SELECT g.*, COALESCE(LAG(g.period_end) OVER (ORDER BY g.period_start), o.opening) AS prev_day
    FROM grid g CROSS JOIN opening o
),
bounds AS (
    SELECT opening AS day FROM opening
    UNION
    SELECT period_end FROM grid
),
home AS (
    SELECT MAX(home_currency) AS h FROM investment_estate_setting
),
rc AS (
    SELECT COALESCE((SELECT MAX(ps.reporting_currency) FROM investment_portfolio_setting ps, prm
                      WHERE ps.portfolio_ref = prm.pid), home.h) AS r
    FROM home
),

-- ── the ledger ──────────────────────────────────────────────────────────────────────────────────────────────────────
vday AS (
    SELECT MAX(p.valuation_date) AS vd
    FROM investment_position p, prm
    WHERE p.valid_to IS NULL AND p.portfolio_ref = prm.pid
),
eff AS (
    -- the effective ledger as far as the gap needs it: to the provider's valuation when that is later than as_of (R1)
    SELECT t.external_id AS id, t.trade_date AS t, t.leg, t.operation AS op, t.asset_ref AS isin,
           t.quantity, t.amount, t.currency,
           -- read through the row, not by name: a book before investment-schema v3 has no `label` column, and its
           -- movements are then simply unlabelled (`labelled` says so) instead of the statement failing
           to_jsonb(t) ->> 'label' AS label,
           -- the day the provider counts a security movement (R7) — read the same way: a pre-v3 book has none
           CAST(to_jsonb(t) ->> 'settlement_date' AS DATE) AS sd,
           -- the security leg's fee, in the home currency (IA-C55 v1.26) — the same way
           CAST(to_jsonb(t) ->> 'fee' AS NUMERIC) AS fee,
           CASE WHEN t.leg = 'security' AND t.operation IN ('buy', 'transfer-in', 'reversal-of-sell')
                     THEN COALESCE(abs(t.quantity), 0)
                WHEN t.leg = 'security' AND t.operation IN ('sell', 'transfer-out', 'payout', 'reversal-of-buy')
                     THEN -COALESCE(abs(t.quantity), 0)
                ELSE 0 END AS qs,
           CASE WHEN t.leg = 'cash' AND t.operation = 'credit' THEN COALESCE(abs(t.amount), 0)
                WHEN t.leg = 'cash' AND t.operation = 'debit' THEN -COALESCE(abs(t.amount), 0)
                WHEN t.leg = 'external-flow' AND t.operation = 'deposit' THEN COALESCE(abs(t.amount), 0)
                WHEN t.leg = 'external-flow' AND t.operation = 'withdrawal' THEN -COALESCE(abs(t.amount), 0)
                ELSE 0 END AS am
    FROM investment_transaction t, prm, vday
    WHERE t.portfolio_ref = prm.pid
      AND t.trade_date <= GREATEST(prm.as_of, COALESCE(vday.vd, prm.as_of))
      AND t.reversal_of IS NULL
      AND NOT EXISTS (SELECT 1 FROM investment_transaction r WHERE r.reversal_of = t.external_id)
),
led AS (
    -- the window's ledger: to as_of, never past it. `pos` is the door's order (day, id); `bpos` the basis order — a day's
    -- inflows (units in: qs > 0) before its outflows, each in the door's order (R3)
    SELECT e.*,
           row_number() OVER (ORDER BY e.t, e.id) AS pos,
           row_number() OVER (ORDER BY e.t, (e.qs > 0) DESC, e.id) AS bpos
    FROM eff e, prm
    WHERE e.t <= prm.as_of
),
stornos AS (
    SELECT row_number() OVER (ORDER BY l.pos) AS n, l.*
    FROM led l
    WHERE l.leg = 'security' AND l.op IN ('reversal-of-buy', 'reversal-of-sell')
),
pairing (n, paired, orig, storno) AS (
    SELECT CAST(0 AS BIGINT), CAST(ARRAY[] AS TEXT[]), CAST(NULL AS TEXT), CAST(NULL AS TEXT)
    UNION ALL
    SELECT s.n,
           CASE WHEN o.id IS NULL THEN pr.paired ELSE pr.paired || o.id || s.id END,
           o.id, s.id
    FROM pairing pr
    JOIN stornos s ON s.n = pr.n + 1
    LEFT JOIN LATERAL (
        -- the LATEST original of the same instrument, units and amount dated on or before the storno's day, not paired
        -- yet — on the same day whatever the ids' order (R3)
        SELECT x.id FROM led x
        WHERE x.t <= s.t
          AND x.id <> s.id
          AND x.leg = 'security'
          AND x.op = CASE WHEN s.op = 'reversal-of-buy' THEN 'buy' ELSE 'sell' END
          AND x.isin = s.isin
          AND abs(x.quantity) IS NOT DISTINCT FROM abs(s.quantity)
          AND abs(x.amount) IS NOT DISTINCT FROM abs(s.amount)
          AND NOT (x.id = ANY (pr.paired))
        ORDER BY x.t DESC, x.id DESC
        LIMIT 1
    ) o ON TRUE
),
paired_ids AS (
    SELECT unnest(paired) AS id FROM pairing WHERE n = (SELECT MAX(n) FROM pairing)
),
pair_spans AS (
    -- a storno'd original still counts in the door's units between its day and its storno's
    SELECT o.isin, o.qs, o.t AS from_t, s.t AS to_t
    FROM pairing p JOIN led o ON o.id = p.orig JOIN led s ON s.id = p.storno
),
tracked AS (
    SELECT l.* FROM led l WHERE NOT EXISTS (SELECT 1 FROM paired_ids p WHERE p.id = l.id)
),

-- ── the provider's labels (IA-C55, IA-P4b·S4b.2) ────────────────────────────────────────────────────────────────────
lbl (ord, label, leg, mtch, cls) AS (
    :labels
),
classed AS (
    -- every cash and external-flow movement, its label as the table spells it (NULL = it carries none), its class
    SELECT l.*, n.norm, c.cls
    FROM tracked l
    CROSS JOIN LATERAL (
        -- the expression between the two `norm` markers is held to the renderer's case list, verbatim (evolution-reference.test.mjs)
        SELECT /* norm */ NULLIF(btrim(regexp_replace(regexp_replace(
                   lower(btrim(regexp_replace(COALESCE(l.label, ''),
                       '[[:space:]\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+', ' ', 'g'), ' ')
                         COLLATE "und-x-icu"),
                   '^.*, ', ''), ' +ident\..*$', ''), ' '), '') /* /norm */ AS norm
    ) n
    LEFT JOIN LATERAL (
        -- an exact entry first (the file's first that fits the leg), else the longest prefix
        SELECT b.cls FROM lbl b
        WHERE (b.leg IS NULL OR b.leg = l.leg)
          AND ((b.mtch = 'exact' AND b.label = n.norm)
               OR (b.mtch = 'prefix' AND left(n.norm, length(b.label)) = b.label))
        ORDER BY (b.mtch = 'exact') DESC, CASE WHEN b.mtch = 'prefix' THEN length(b.label) END DESC, b.ord
        LIMIT 1
    ) c ON TRUE
    WHERE l.leg IN ('cash', 'external-flow')
),
label_col AS (
    -- whether the book can be classified at all: it HAS the column (a book before investment-schema v3 does not)
    SELECT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'investment_transaction' AND column_name = 'label'
                      AND table_schema = ANY (current_schemas(false))) AS present
),
labelling AS (
    -- IA-C49's footnotes drop iff the book HAS the column and every cash/flow movement of the window carries a label
    SELECT lc.present
           AND NOT EXISTS (SELECT 1 FROM classed c JOIN grid g ON c.t BETWEEN g.period_start AND g.period_end
                            WHERE c.norm IS NULL) AS labelled
    FROM label_col lc
),
twin_cash AS (
    -- the cash movements a class would show in fees / income — each may be the same payment as an external-flow movement
    SELECT c.id, c.pos, c.t, c.currency, c.am, c.cls
    FROM classed c
    WHERE c.leg = 'cash' AND c.cls IN ('fee', 'dividend', 'coupon', 'interest')
),
twin_flow AS (
    -- `provider`: the flow carries the provider's own id (`…:DEP:<T><Id>`), not a content hash (`…:DEP:H:…`)
    SELECT c.id, c.pos, c.t, c.currency, c.am, COALESCE(c.cls, 'other') AS cls,
           c.id ~ ':DEP:[^:]+$' AS provider
    FROM classed c
    WHERE c.leg = 'external-flow'
),
twin_by_id AS (
    -- the provider's ids: `…:CASH:<T>:<Id>` and `…:DEP:<T><Id>` are one payment, if the two are classed alike; one flow
    -- twins one cash movement (the first, in the door's order)
    SELECT DISTINCT ON (f.id) c.id AS cash_id
    FROM twin_cash c
    JOIN twin_flow f ON c.id ~ '^.+:CASH:[A-Z]+:[^:]+$'
                    AND f.id = regexp_replace(c.id, '^(.+):CASH:([A-Z]+):([^:]+)$', '\1:DEP:\2\3')
                    AND f.cls = c.cls
    ORDER BY f.id, c.pos
),
twin_by_key AS (
    -- a flow with no provider id: the same day, signed amount, currency and class — the k-th such cash movement (door
    -- order) with the k-th such flow, which is what pairing each cash movement with the first flow still free gives
    SELECT c.id AS cash_id
    FROM (SELECT tc.*, row_number() OVER (PARTITION BY tc.t, tc.currency, tc.am, tc.cls ORDER BY tc.pos) AS k
          FROM twin_cash tc
          WHERE NOT EXISTS (SELECT 1 FROM twin_by_id b WHERE b.cash_id = tc.id)) c
    JOIN (SELECT tf.*, row_number() OVER (PARTITION BY tf.t, tf.currency, tf.am, tf.cls ORDER BY tf.pos) AS k
          FROM twin_flow tf
          WHERE NOT tf.provider) f
      ON f.t = c.t AND f.currency IS NOT DISTINCT FROM c.currency AND f.am = c.am AND f.cls = c.cls AND f.k = c.k
),
twinned AS (
    SELECT cash_id FROM twin_by_id
    UNION
    SELECT cash_id FROM twin_by_key
),

-- ── rates and prices ────────────────────────────────────────────────────────────────────────────────────────────────
days AS (
    SELECT day FROM bounds
    UNION
    SELECT t FROM led
),
curs AS (
    SELECT currency AS cur FROM investment_fx_rate
    UNION SELECT h FROM home
    UNION SELECT r FROM rc
    UNION SELECT currency FROM led WHERE currency IS NOT NULL
    UNION SELECT currency FROM investment_asset_price
),
ron AS (
    -- each currency's worth in the home currency on each day: the latest rate on or before it, per unit
    SELECT d.day, c.cur,
           CASE WHEN c.cur = home.h THEN CAST(1 AS NUMERIC)
                ELSE (SELECT fr.rate / fr.units FROM investment_fx_rate fr
                       WHERE fr.currency = c.cur AND fr.rate_date <= d.day
                       ORDER BY fr.rate_date DESC LIMIT 1) END AS v
    FROM days d CROSS JOIN curs c CROSS JOIN home
    WHERE c.cur IS NOT NULL
),
fx AS (
    -- the factor that turns an amount in `cur` on `day` into R
    SELECT a.day, a.cur, a.v / NULLIF(b.v, 0) AS f
    FROM ron a JOIN ron b ON b.day = a.day AND b.cur = (SELECT r FROM rc)
),
fcur AS (
    -- each instrument's price currency: its latest price's on or before as_of
    SELECT DISTINCT ON (ap.isin) ap.isin, ap.currency AS f
    FROM investment_asset_price ap, prm
    WHERE ap.price_date <= prm.as_of
    ORDER BY ap.isin, ap.price_date DESC
),

-- ── the security leg's fee (IA-C55 v1.26) ─────────────────────────────────────────────────────────────────────────
sec_fees AS (
    -- every security movement of the ledger to as_of (storno pairs dropped) that carries a fee, in the order the fees are
    -- decided: deal day, then id (byte order, as the renderer compares ids)
    SELECT row_number() OVER (ORDER BY l.t, l.id COLLATE "C") AS n,
           l.id, l.t, l.isin, l.fee, COALESCE(l.sd, l.t) AS settles
    FROM tracked l
    WHERE l.leg = 'security' AND l.fee IS NOT NULL AND l.fee <> 0
),
recorders AS (
    -- the movements that may record a fee — counted in fees already (a flow classed fee; a cash one classed fee with no
    -- flow twin) or not classifiable (no label, a label the table does not know) — and what each pays: minus its signed
    -- amount (a withdrawal or a debit pays, a deposit or a credit refunds), in its currency and in the home currency at
    -- its own day's rate (NULL when no rate converts it); one paying nothing records nothing
    SELECT c.id, c.t, COALESCE(c.currency, rc.r) AS cur, -c.am AS paid, -c.am * rn.v AS paid_home
    FROM classed c
    CROSS JOIN rc
    LEFT JOIN twinned tw ON tw.cash_id = c.id
    LEFT JOIN ron rn ON rn.day = c.t AND rn.cur = COALESCE(c.currency, rc.r)
    WHERE c.am <> 0
      AND (c.cls IS NULL OR (c.cls = 'fee' AND (c.leg = 'external-flow' OR tw.cash_id IS NULL)))
),
fee_match (n, taken, fee_id, rec_id) AS (
    -- one fee at a time, each taking the untaken recorder of its window that pays the same money — the nearest to its
    -- settlement day, then the earlier, then the lower id; `taken` carries the recorders already used
    SELECT CAST(0 AS BIGINT), CAST(ARRAY[] AS TEXT[]), CAST(NULL AS TEXT), CAST(NULL AS TEXT)
    UNION ALL
    SELECT s.n, CASE WHEN x.id IS NULL THEN m.taken ELSE m.taken || x.id END, s.id, x.id
    FROM fee_match m
    JOIN sec_fees s ON s.n = m.n + 1
    LEFT JOIN LATERAL (
        SELECT r.id FROM recorders r
        WHERE r.t BETWEEN s.t - 3 AND s.settles + 7
          AND NOT (r.id = ANY (m.taken))
          AND CASE WHEN r.cur = (SELECT COALESCE(home.h, rc.r) FROM home, rc) THEN r.paid = s.fee
                   ELSE r.paid_home IS NOT NULL AND abs(r.paid_home - s.fee) <= abs(s.fee) * 0.01 END
        ORDER BY abs(r.t - s.settles), r.t, r.id COLLATE "C"
        LIMIT 1
    ) x ON TRUE
),
sec_fee_added AS (
    -- the fees no movement records, in the period of their deal day, from home to R at that day's rate — only in a book
    -- that can be classified; a fee on a movement with no instrument is the renderer's to skip too
    SELECT g.period, SUM(s.fee * fx.f) AS fees
    FROM sec_fees s
    CROSS JOIN label_col lc
    CROSS JOIN home
    CROSS JOIN rc
    JOIN grid g ON s.t BETWEEN g.period_start AND g.period_end
    LEFT JOIN fx ON fx.day = s.t AND fx.cur = COALESCE(home.h, rc.r)
    WHERE lc.present
      AND s.isin IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM fee_match fm WHERE fm.fee_id = s.id AND fm.rec_id IS NOT NULL)
    GROUP BY g.period
),

-- ── what the ledger does not explain (S4.1·D2) ──────────────────────────────────────────────────────────────────────
val AS (
    SELECT p.asset_ref AS isin, p.quantity AS units
    FROM investment_position p, prm, vday
    WHERE p.valid_to IS NULL AND p.portfolio_ref = prm.pid AND p.valuation_date = vday.vd
),
lu AS (
    -- the ledger's units SETTLED BY THE VALUATION DAY (R1, R7): the extended ledger, not the window's — a movement
    -- counts on its settlement day, else its deal day, whatever its direction
    SELECT l.isin, SUM(l.qs) AS units
    FROM eff l, vday
    WHERE l.leg = 'security' AND l.isin IS NOT NULL AND l.t <= vday.vd AND COALESCE(l.sd, l.t) <= vday.vd
    GROUP BY l.isin
),
raw_gap AS (
    SELECT COALESCE(v.isin, u.isin) AS isin, COALESCE(v.units, 0) - COALESCE(u.units, 0) AS raw
    FROM val v FULL JOIN lu u ON u.isin = v.isin
),
settle AS (
    -- trades still settling UNSEEN: only a movement with NO settlement day can be one (a known day already decided `lu`,
    -- R7) — the newest of those dealt in the 20 days up to the valuation (the extended ledger), summed newest first —
    -- the reverse of the basis order: a day's outflows before its inflows, ids descending (R3)
    SELECT l.isin,
           SUM(l.qs) OVER (PARTITION BY l.isin ORDER BY l.t DESC, (l.qs > 0) ASC, l.id DESC ROWS UNBOUNDED PRECEDING) AS run
    FROM eff l, vday
    WHERE l.leg = 'security' AND l.isin IS NOT NULL AND l.sd IS NULL AND l.t <= vday.vd AND l.t > vday.vd - 20
),
gap AS (
    SELECT g.isin, g.raw AS gap
    FROM raw_gap g
    WHERE g.raw <> 0
      AND NOT EXISTS (SELECT 1 FROM settle s WHERE s.isin = g.isin AND g.raw + s.run = 0)
),
pre AS (
    SELECT l.isin, SUM(l.qs) OVER (PARTITION BY l.isin ORDER BY l.bpos ROWS UNBOUNDED PRECEDING) AS run
    FROM tracked l, opening
    WHERE l.leg = 'security' AND l.isin IS NOT NULL AND l.t <= opening.opening
),
marked AS (
    SELECT DISTINCT isin FROM pre WHERE run < 0
),
deemed AS (
    SELECT d.isin,
           COALESCE((SELECT SUM(l.qs) FROM tracked l, opening
                      WHERE l.leg = 'security' AND l.isin = d.isin AND l.t <= opening.opening), 0)
               + COALESCE(g.gap, 0) AS units
    FROM (SELECT isin FROM gap UNION SELECT isin FROM marked) d
    LEFT JOIN gap g ON g.isin = d.isin
),
deemed_lot AS (
    -- the opening state of an instrument the ledger cannot explain: its units at the opening market value — and with no
    -- price on the opening, a cost nobody knows: NULL, never 0 (R9)
    SELECT d.isin, d.units,
           CASE WHEN d.units = 0 THEN 0 WHEN p.price IS NULL THEN NULL ELSE d.units * p.price * fx.f END AS cr,
           CASE WHEN d.units = 0 THEN 0 WHEN p.price IS NULL THEN NULL ELSE d.units * p.price END AS cf
    FROM deemed d CROSS JOIN opening
    LEFT JOIN LATERAL (SELECT ap.price, ap.currency FROM investment_asset_price ap
                        WHERE ap.isin = d.isin AND ap.price_date <= opening.opening
                        ORDER BY ap.price_date DESC LIMIT 1) p ON TRUE
    LEFT JOIN fx ON fx.day = opening.opening AND fx.cur = p.currency
),

-- ── the average cost, movement by movement ──────────────────────────────────────────────────────────────────────────
mv AS (
    SELECT x.isin, x.pos, x.t, x.id, x.op,
           abs(x.quantity) AS q, abs(x.amount) AS a,
           COALESCE(x.currency, rc.r) AS s,
           COALESCE(fc.f, x.currency, rc.r) AS f,
           x.op IN ('buy', 'transfer-in', 'reversal-of-sell') AS inflow,
           row_number() OVER (PARTITION BY x.isin ORDER BY x.bpos) AS k
    FROM tracked x
    CROSS JOIN rc
    CROSS JOIN opening
    LEFT JOIN fcur fc ON fc.isin = x.isin
    WHERE x.leg = 'security' AND x.isin IS NOT NULL
      AND COALESCE(abs(x.quantity), 0) <> 0
      AND x.op IN ('buy', 'transfer-in', 'reversal-of-sell', 'sell', 'transfer-out', 'payout', 'reversal-of-buy')
      AND (x.isin NOT IN (SELECT isin FROM deemed) OR x.t > opening.opening)
),
mvx AS (
    SELECT m.*,
           -- an inflow's cost, R and F; a transfer-in without an amount at the latest price on or before its day
           CASE WHEN m.inflow AND m.op = 'transfer-in' AND m.a IS NULL THEN m.q * tp.price * tpf.f
                WHEN m.inflow THEN m.a * fs.f END AS in_r,
           CASE WHEN m.inflow AND m.op = 'transfer-in' AND m.a IS NULL THEN m.q * tp.price
                WHEN m.inflow THEN m.a * rs.v / NULLIF(rf.v, 0) END AS in_f,
           -- an outflow's proceeds, R and F
           CASE WHEN NOT m.inflow THEN m.a * fs.f END AS pro_r,
           CASE WHEN NOT m.inflow THEN m.a * rs.v / NULLIF(rf.v, 0) END AS pro_f
    FROM mv m
    LEFT JOIN fx fs ON fs.day = m.t AND fs.cur = m.s
    LEFT JOIN ron rs ON rs.day = m.t AND rs.cur = m.s
    LEFT JOIN ron rf ON rf.day = m.t AND rf.cur = m.f
    LEFT JOIN LATERAL (SELECT ap.price, ap.currency FROM investment_asset_price ap
                        WHERE ap.isin = m.isin AND ap.price_date <= m.t
                        ORDER BY ap.price_date DESC LIMIT 1) tp ON TRUE
    LEFT JOIN fx tpf ON tpf.day = m.t AND tpf.cur = tp.currency
),
starts AS (
    -- an instrument not deemed starts empty (0); a deemed one at its lot — whose cost may be unknown (NULL)
    SELECT i.isin, COALESCE(d.units, 0) AS u,
           CASE WHEN d.isin IS NULL THEN 0 ELSE d.cr END AS cr,
           CASE WHEN d.isin IS NULL THEN 0 ELSE d.cf END AS cf
    FROM (SELECT isin FROM mv UNION SELECT isin FROM deemed) i
    LEFT JOIN deemed_lot d ON d.isin = i.isin
),
basis (isin, k, t, u, cr, cf, taken_r, taken_f, short) AS (
    SELECT s.isin, CAST(0 AS BIGINT), o.opening, s.u, s.cr, s.cf,
           CAST(NULL AS NUMERIC), CAST(NULL AS NUMERIC), FALSE
    FROM starts s CROSS JOIN opening o
    UNION ALL
    SELECT b.isin, m.k, m.t,
           CASE WHEN m.inflow THEN b.u + m.q ELSE b.u - m.q END,
           CASE WHEN m.inflow THEN b.cr + m.in_r WHEN m.q >= b.u THEN 0 ELSE b.cr - b.cr * m.q / b.u END,
           CASE WHEN m.inflow THEN b.cf + m.in_f WHEN m.q >= b.u THEN 0 ELSE b.cf - b.cf * m.q / b.u END,
           CASE WHEN NOT m.inflow THEN (CASE WHEN m.q = b.u THEN b.cr WHEN b.u = 0 THEN 0 ELSE b.cr * m.q / b.u END) END,
           CASE WHEN NOT m.inflow THEN (CASE WHEN m.q = b.u THEN b.cf WHEN b.u = 0 THEN 0 ELSE b.cf * m.q / b.u END) END,
           (NOT m.inflow AND m.q > b.u)
    FROM basis b JOIN mvx m ON m.isin = b.isin AND m.k = b.k + 1
),

-- ── each period's movements ─────────────────────────────────────────────────────────────────────────────────────────
trade_parts AS (
    SELECT g.period,
           CASE WHEN m.op IN ('buy', 'reversal-of-sell') THEN m.in_r ELSE 0 END AS purchases,
           CASE WHEN m.op = 'transfer-in' THEN m.in_r ELSE 0 END AS transfers_in,
           CASE WHEN m.op IN ('sell', 'payout', 'reversal-of-buy') THEN b.taken_r ELSE 0 END AS sales_at_cost,
           CASE WHEN m.op = 'transfer-out' THEN b.taken_r ELSE 0 END AS transfers_out,
           CASE WHEN m.op IN ('sell', 'payout', 'reversal-of-buy') THEN m.pro_r ELSE 0 END AS proceeds,
           CASE WHEN m.op IN ('sell', 'payout', 'reversal-of-buy') THEN m.pro_r - b.taken_r ELSE 0 END AS realized,
           CASE WHEN m.op IN ('sell', 'payout', 'reversal-of-buy')
                THEN (CASE WHEN b.taken_f = 0 THEN 0 ELSE m.pro_r - m.pro_f * b.taken_r / b.taken_f END)
                ELSE 0 END AS fx_realized
    FROM basis b
    JOIN mvx m ON m.isin = b.isin AND m.k = b.k
    JOIN grid g ON m.t BETWEEN g.period_start AND g.period_end
),
trades AS (
    -- a sum with an unknown part is unknown (R9) — SUM alone would skip the NULL and print a figure
    SELECT period,
           CASE WHEN bool_or(purchases IS NULL) THEN NULL ELSE SUM(purchases) END AS purchases,
           CASE WHEN bool_or(transfers_in IS NULL) THEN NULL ELSE SUM(transfers_in) END AS transfers_in,
           CASE WHEN bool_or(sales_at_cost IS NULL) THEN NULL ELSE SUM(sales_at_cost) END AS sales_at_cost,
           CASE WHEN bool_or(transfers_out IS NULL) THEN NULL ELSE SUM(transfers_out) END AS transfers_out,
           CASE WHEN bool_or(proceeds IS NULL) THEN NULL ELSE SUM(proceeds) END AS proceeds,
           CASE WHEN bool_or(realized IS NULL) THEN NULL ELSE SUM(realized) END AS realized,
           CASE WHEN bool_or(fx_realized IS NULL) THEN NULL ELSE SUM(fx_realized) END AS fx_realized
    FROM trade_parts
    GROUP BY period
),
flows AS (
    -- a flow classed fee or income LEAVES deposits / withdrawals for its column (IA-C55); tax / other / unknown stay
    SELECT g.period,
           SUM(CASE WHEN l.op = 'deposit' AND COALESCE(l.cls, 'other') IN ('tax', 'other')
                    THEN abs(l.amount) * fx.f ELSE 0 END) AS deposits,
           SUM(CASE WHEN l.op = 'withdrawal' AND COALESCE(l.cls, 'other') IN ('tax', 'other')
                    THEN abs(l.amount) * fx.f ELSE 0 END) AS withdrawals,
           SUM(CASE WHEN l.cls = 'fee' AND l.op = 'withdrawal' THEN abs(l.amount) * fx.f
                    WHEN l.cls = 'fee' AND l.op = 'deposit' THEN -abs(l.amount) * fx.f
                    ELSE 0 END) AS fees,
           SUM(CASE WHEN l.cls IN ('dividend', 'coupon', 'interest') AND l.op = 'deposit' THEN abs(l.amount) * fx.f
                    WHEN l.cls IN ('dividend', 'coupon', 'interest') AND l.op = 'withdrawal' THEN -abs(l.amount) * fx.f
                    ELSE 0 END) AS income
    FROM classed l
    CROSS JOIN rc
    JOIN grid g ON l.t BETWEEN g.period_start AND g.period_end
    LEFT JOIN fx ON fx.day = l.t AND fx.cur = COALESCE(l.currency, rc.r)
    WHERE l.leg = 'external-flow'
    GROUP BY g.period
),
cashm AS (
    -- a cash movement classed fee / income is SHOWN there and stays in cash_movements (the identity reads those) — not
    -- when its external-flow twin already counted the same payment (R1)
    SELECT g.period,
           SUM(l.am * ft.f) AS cash_movements,
           SUM(l.am * (fc.f - ft.f)) AS fx_moves,
           SUM(CASE WHEN l.cls = 'fee' AND tw.cash_id IS NULL THEN -(l.am * ft.f) ELSE 0 END) AS fees,
           SUM(CASE WHEN l.cls IN ('dividend', 'coupon', 'interest') AND tw.cash_id IS NULL THEN l.am * ft.f ELSE 0 END)
               AS income
    FROM classed l
    CROSS JOIN rc
    JOIN grid g ON l.t BETWEEN g.period_start AND g.period_end
    LEFT JOIN twinned tw ON tw.cash_id = l.id
    LEFT JOIN fx ft ON ft.day = l.t AND ft.cur = COALESCE(l.currency, rc.r)
    LEFT JOIN fx fc ON fc.day = g.period_end AND fc.cur = COALESCE(l.currency, rc.r)
    WHERE l.leg = 'cash'
    GROUP BY g.period
),

-- ── the book on each boundary ───────────────────────────────────────────────────────────────────────────────────────
cbal AS (
    SELECT b.day, l.currency AS cur, SUM(l.am) AS bal
    FROM bounds b JOIN led l ON l.leg = 'cash' AND l.t <= b.day AND l.currency IS NOT NULL
    GROUP BY b.day, l.currency
),
cash_at AS (
    SELECT c.day, SUM(c.bal * fx.f) AS cash
    FROM cbal c LEFT JOIN fx ON fx.day = c.day AND fx.cur = c.cur
    GROUP BY c.day
),
fx_open AS (
    -- cash held in another currency at a period's opening, revalued to its close
    SELECT sp.period, SUM(c.bal * (f1.f - f0.f)) AS fx_open
    FROM spans sp
    CROSS JOIN rc
    JOIN cbal c ON c.day = sp.prev_day AND c.cur <> rc.r AND c.bal <> 0
    LEFT JOIN fx f1 ON f1.day = sp.period_end AND f1.cur = c.cur
    LEFT JOIN fx f0 ON f0.day = sp.prev_day AND f0.cur = c.cur
    GROUP BY sp.period
),
door_units AS (
    SELECT day, isin, SUM(u) AS u FROM (
        SELECT b.day, l.isin, l.qs AS u
        FROM bounds b JOIN led l ON l.leg = 'security' AND l.isin IS NOT NULL AND l.t <= b.day
        UNION ALL
        SELECT b.day, g.isin, g.gap FROM bounds b CROSS JOIN gap g
        UNION ALL
        SELECT b.day, ps.isin, -ps.qs FROM bounds b JOIN pair_spans ps ON ps.from_t <= b.day AND b.day < ps.to_t
    ) x
    GROUP BY day, isin
),
market AS (
    SELECT d.day,
           SUM(CASE WHEN p.price IS NOT NULL THEN d.u * p.price * fx.f ELSE 0 END) AS mv,
           COUNT(*) FILTER (WHERE p.price IS NOT NULL) AS priced,
           COUNT(*) FILTER (WHERE p.price IS NULL) AS unpriced
    FROM door_units d
    LEFT JOIN LATERAL (SELECT ap.price, ap.currency FROM investment_asset_price ap
                        WHERE ap.isin = d.isin AND ap.price_date <= d.day
                        ORDER BY ap.price_date DESC LIMIT 1) p ON TRUE
    LEFT JOIN fx ON fx.day = d.day AND fx.cur = p.currency
    WHERE d.u <> 0
    GROUP BY d.day
),
state_at AS (
    -- each instrument's basis on each boundary: its last movement on or before the day (its opening state before any)
    SELECT DISTINCT ON (b.day, s.isin) b.day, s.isin, s.u, s.cr, s.cf
    FROM bounds b JOIN basis s ON s.k = 0 OR s.t <= b.day
    ORDER BY b.day, s.isin, s.k DESC
),
held AS (
    -- a lot of unknown cost makes the day's invested unknown, and its fx part once it has a price to value (R9)
    SELECT st.day,
           CASE WHEN bool_or(st.cr IS NULL) THEN NULL ELSE SUM(st.cr) END AS invested,
           SUM(CASE WHEN p.price IS NOT NULL THEN st.u * p.price * fx.f ELSE 0 END) AS tracked_mv,
           CASE WHEN bool_or(p.price IS NOT NULL AND st.cf IS NULL) THEN NULL
                ELSE SUM(CASE WHEN p.price IS NULL OR st.cf = 0 THEN 0
                              ELSE st.u * p.price * fx.f - st.u * p.price * (st.cr / st.cf) END) END AS fx_unrealized
    FROM state_at st
    LEFT JOIN LATERAL (SELECT ap.price, ap.currency FROM investment_asset_price ap
                        WHERE ap.isin = st.isin AND ap.price_date <= st.day
                        ORDER BY ap.price_date DESC LIMIT 1) p ON TRUE
    LEFT JOIN fx ON fx.day = st.day AND fx.cur = p.currency
    WHERE st.u <> 0
    GROUP BY st.day
),
book AS (
    SELECT b.day,
           COALESCE(m.mv, 0) AS mv, COALESCE(c.cash, 0) AS cash,
           -- a boundary holding nothing is 0; one holding a lot of unknown cost is NULL (R9) — not COALESCEd away
           CASE WHEN h.day IS NULL THEN 0 ELSE h.invested END AS invested,
           CASE WHEN h.day IS NULL THEN 0 ELSE h.tracked_mv - h.invested END AS unrealized,
           CASE WHEN h.day IS NULL THEN 0 ELSE h.fx_unrealized END AS fx_unrealized,
           COALESCE(m.priced, 0) AS priced, COALESCE(m.unpriced, 0) AS unpriced
    FROM bounds b
    LEFT JOIN market m ON m.day = b.day
    LEFT JOIN cash_at c ON c.day = b.day
    LEFT JOIN held h ON h.day = b.day
),

-- ── what cannot be compared ─────────────────────────────────────────────────────────────────────────────────────────
refusals AS (
    SELECT 'no home currency is set (investment_estate_setting)' AS why FROM home WHERE h IS NULL
    UNION ALL
    SELECT 'the ledger holds ' || (-g.gap) || ' more units of ' || g.isin || ' than the provider''s valuation (incomplete_ledger)'
    FROM gap g WHERE g.gap < 0
    UNION ALL
    SELECT 'the window opens with negative units of ' || d.isin || ' (incomplete_ledger)' FROM deemed d WHERE d.units < 0
    UNION ALL
    SELECT 'units of ' || b.isin || ' leave on ' || b.t || ' while fewer are held (incomplete_ledger)' FROM basis b WHERE b.short
),

rows AS (
    SELECT sp.period, sp.period_start, sp.period_end, prm.pid AS portfolio_id, rc.r AS currency,
           o.invested AS invested_open, o.mv AS market_value_open, o.cash AS cash_open,
           o.unrealized AS unrealized_open, o.fx_unrealized AS fx_unrealized_open,
           COALESCE(fl.deposits, 0) AS deposits, COALESCE(fl.withdrawals, 0) AS withdrawals,
           -- a period with no trade is 0; one whose trade has an unknown cost keeps its NULL (R9)
           CASE WHEN tr.period IS NULL THEN 0 ELSE tr.purchases END AS purchases_at_cost,
           CASE WHEN tr.period IS NULL THEN 0 ELSE tr.transfers_in END AS transfers_in_at_cost,
           CASE WHEN tr.period IS NULL THEN 0 ELSE tr.sales_at_cost END AS sales_at_cost,
           CASE WHEN tr.period IS NULL THEN 0 ELSE tr.transfers_out END AS transfers_out_at_cost,
           CASE WHEN tr.period IS NULL THEN 0 ELSE tr.proceeds END AS sales_proceeds,
           CASE WHEN tr.period IS NULL THEN 0 ELSE tr.realized END AS realized_sales,
           CASE WHEN tr.period IS NULL THEN 0 ELSE tr.fx_realized END AS fx_realized,
           COALESCE(fl.income, 0) + COALESCE(cm.income, 0) AS income,
           COALESCE(fl.fees, 0) + COALESCE(cm.fees, 0) + COALESCE(sf.fees, 0) AS fees,
           COALESCE(cm.cash_movements, 0) AS cash_movements,
           COALESCE(fo.fx_open, 0) + COALESCE(cm.fx_moves, 0) AS fx_cash,
           c.invested AS invested_close, c.mv AS market_value_close, c.cash AS cash_close,
           c.unrealized AS unrealized_close, c.fx_unrealized AS fx_unrealized_close,
           c.priced AS priced_instruments, c.unpriced AS unpriced_instruments
    FROM spans sp
    CROSS JOIN prm
    CROSS JOIN rc
    JOIN book o ON o.day = sp.prev_day
    JOIN book c ON c.day = sp.period_end
    LEFT JOIN flows fl ON fl.period = sp.period
    LEFT JOIN trades tr ON tr.period = sp.period
    LEFT JOIN cashm cm ON cm.period = sp.period
    LEFT JOIN sec_fee_added sf ON sf.period = sp.period
    LEFT JOIN fx_open fo ON fo.period = sp.period
)
SELECT r.period, r.period_start, r.period_end, r.portfolio_id, r.currency,
       r.invested_open AS invested_open,
       r.market_value_open AS market_value_open,
       r.cash_open AS cash_open,
       r.unrealized_open AS unrealized_open,
       r.fx_unrealized_open AS fx_unrealized_open,
       r.deposits AS deposits,
       r.withdrawals AS withdrawals,
       r.deposits - r.withdrawals AS flows_net,
       r.purchases_at_cost AS purchases_at_cost,
       r.transfers_in_at_cost AS transfers_in_at_cost,
       r.sales_at_cost AS sales_at_cost,
       r.transfers_out_at_cost AS transfers_out_at_cost,
       r.sales_proceeds AS sales_proceeds,
       r.realized_sales AS realized_sales,
       r.fx_realized AS fx_realized,
       r.income AS income,
       r.realized_sales + r.income AS realized_total,
       r.fees AS fees,
       0.00 AS fx_costs,
       r.fees + 0.00 AS costs_total,
       r.cash_movements AS cash_movements,
       r.fx_cash AS fx_cash,
       r.invested_close AS invested_close,
       r.market_value_close AS market_value_close,
       r.cash_close AS cash_close,
       r.unrealized_close AS unrealized_close,
       r.fx_unrealized_close AS fx_unrealized_close,
       (r.market_value_close - r.market_value_open)
             - (r.purchases_at_cost + r.transfers_in_at_cost - r.sales_at_cost - r.transfers_out_at_cost)
             - (r.unrealized_close - r.unrealized_open)
             + (r.cash_close - r.cash_open - r.cash_movements - r.fx_cash) AS unexplained,
       r.priced_instruments,
       r.unpriced_instruments,
       COALESCE((SELECT string_agg(why, '; ') FROM refusals), '') AS refused,
       (SELECT CASE WHEN labelled THEN 'true' ELSE 'false' END FROM labelling) AS labelled
FROM rows r
ORDER BY r.period_start;
