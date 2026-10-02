# The `investment-evolution:v2` fingerprint's fixture

Everything here is SYNTHETIC — two invented portfolios of an invented client — and was written by kantheon, not here:

| File | What it is | Written by |
|---|---|---|
| `fixture-ledger.json` | the hand fixture: 2 portfolios, 5 instruments (a EUR fund settled in CZK, a pre-ledger holding, an unpriced one), EUR cash, a USD-reporting portfolio, a Conseq storno across a month-end, transfers in kind, 12 months of prices and rates | kantheon `services/report-renderer/src/test/resources/period/` (IA-P4·S4.1) |
| `expected-average.csv` | its answers, worked by hand (kantheon's `README.md` there shows the working) and checked by an independent script | the same |
| `workbook-200900001-month.xlsx`, `workbook-200900002-quarter.xlsx` | `investment-evolution:v2` rendered over that fixture, 2025-07-01 … 2026-06-15, average cost — the renderer's own output | kantheon report-renderer (IA-P4·S4.2), through its fixture door |
| `reference-200900001-month.csv`, `reference-200900002-quarter.csv` | `scripts/sql/evolution-reference.sql` run with psql on the fixture loaded into PostgreSQL 16 | `just verify-evolution-reference` |
| `book-schema.sql` | the six tables the reference reads, with the estate's column types | — |

Three sides that share no code: the hand answers, the renderer's workbook, and the reference on PostgreSQL.
`scripts/tests/evolution-fingerprint.test.mjs` holds the workbooks to the saved references and the saved references to
the hand answers (no database); `scripts/tests/evolution-reference.test.mjs` re-runs the reference on PostgreSQL and
holds it to both again.

Regenerate a workbook when the renderer's v2 template changes, a reference when the SQL does:

    just verify-evolution-reference --write     # re-runs the reference and rewrites reference-*.csv
