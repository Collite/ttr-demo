# The `investment-evolution:v2` fingerprint's fixture

Everything here is SYNTHETIC — two invented portfolios of an invented client — and was written by kantheon, not here:

| File | What it is | Written by |
|---|---|---|
| `fixture-ledger.json` | the hand fixture (since IA-P4·S4.3 also the provider's `market_values` and `valuation_points` the overviews read — `../overview/`; since IA-P4b·S4b.2 every movement's `label`, the security leg's `fee` and `settlement_date`, and an entry fee + commission withdrawn 2026-05-08; since the IA-P4b review a buy dealt before the provider's 06-12 valuation and settled after it): 2 portfolios, 5 instruments (a EUR fund settled in CZK, a pre-ledger holding, an unpriced one), EUR cash, a USD-reporting portfolio, a Conseq storno across a month-end, transfers in kind, 12 months of prices and rates | kantheon `services/report-renderer/src/test/resources/period/` (IA-P4·S4.1) |
| `expected-average.csv` | its answers, worked by hand (kantheon's `README.md` there shows the working) and checked by an independent script | the same |
| `workbook-200900001-month.xlsx`, `workbook-200900002-quarter.xlsx` | `investment-evolution:v2` rendered over that fixture, 2025-07-01 … 2026-06-15, average cost — the renderer's own output | kantheon report-renderer (IA-P4·S4.2), through its fixture door |
| `reference-200900001-month.csv`, `reference-200900002-quarter.csv` | `scripts/sql/evolution-reference.sql` run with psql on the fixture loaded into PostgreSQL 16 | `just verify-evolution-reference` |
| `expected-as-of-2026-03-15-average.csv` | the main fixture's answers for a window ending BEFORE the provider's valuation (2026-03-15): the gap is still read against the ledger to the valuation day (IA-P4 review R1) | kantheon (`reference.py --as-of`) |
| `fixture-cases.json`, `expected-cases-average.csv` | a book of its own (client `conseq:8809002`): P3 same-day movements — a storno answered before its original, a sale before its buy (R3); P4 a holding deemed at the opening with no opening price, whose cost is unknown (R9); since the IA-P4b review P5 a cash-account contract whose fees arrive on both legs — twins by the provider's ids and, for a hashed flow id, by day + amount + currency + class, counted once (R1) — and P6 a sale and a buy settling after the provider's valuation, which it does not count yet (R7); since IA-C55 v1.26 the fee of P6's 12-05 buy, which no movement of its own records, is in December's `fees` (43.20) — and their answers | kantheon (`reference.py`, its README shows the working) |
| `expected-unlabelled-average.csv` | the same ledger with every label ignored — the book before IA-P4b: fees and income 0, entry fees inside withdrawals, IA-C49's footnotes kept | kantheon (`reference.py --unlabelled`) |
| `income-labels.cases.json` | the label normalisation's case list (IA-C55) — kantheon's `packages/investment/model/tests/income-labels.cases.json` at the commit `model/investment/SYNCED-FROM` names — `just check-investment-model-source` compares it byte for byte (`INVESTMENT_COPIES`); the reference's SQL and `scripts/lib/income_labels.py` are held to it, as the renderer is | kantheon (IA-P4b·S4b.2) |
| `workbook-200900001-month-unlabelled.xlsx` | the IA-P4 workbook (every IA-C49 header still ` *`) — kept so the engine is shown reading an unclassified render too | kantheon report-renderer (IA-P4·S4.2) |
| `book-schema.sql` | the six tables the reference reads, with the estate's column types (since IA-P4b the ledger's `fee`, `label`, `settlement_date`) | — |

Three sides that share no code: the hand answers, the renderer's workbook, and the reference on PostgreSQL.
`scripts/tests/evolution-fingerprint.test.mjs` holds the workbooks to the saved references and the saved references to
the hand answers (no database); `scripts/tests/evolution-reference.test.mjs` re-runs the reference on PostgreSQL and
holds it to both again.

The reference's own rules beyond the hand answers — the security leg's fee added unless a movement records it (IA-C55 v1.26: the window, one recorder per fee, the nearest first, a cash twin no recorder, an unlabelled or unknown movement a recorder, another currency within 1 %) — are planted in P5 by `evolution-reference.test.mjs` and removed again.

The reference classifies fees and income with the SAME table the renderer packages — `model/investment/income-labels.yaml`,
synced from kantheon with the model (`just sync-investment-model` carries it beside the four model directories, under the
stamp's tree hash) and handed to psql as `-v labels=…` (`scripts/lib/income_labels.py sql`).

Regenerate a workbook when the renderer's v2 template changes, a reference when the SQL does:

    just verify-evolution-reference --write     # re-runs the reference and rewrites reference-*.csv
