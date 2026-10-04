# The overview fingerprints' fixture (IA-P4·S4.3)

Everything here is SYNTHETIC — the same two invented portfolios of an invented client as `../evolution/` — and the
workbooks were written by kantheon, not here:

| File | What it is | Written by |
|---|---|---|
| `workbook-statement.xlsx` | `portfolio-statement:v1` of conseq:200900001, 2025-07-01 … 2026-06-15 | kantheon report-renderer, through its fixture door |
| `workbook-client-overview.xlsx` | `client-overview:v1` of conseq:8809001 as of 2026-06-15 | the same |
| `workbook-distributor-overview.xlsx` | `distributor-overview:v1` as of 2026-06-15 | the same |
| `workbook-price-sheet.xlsx` | `price-sheet:v1`, six month-ends to 2026-06-15 | the same |
| `workbook-sync-run-changes.xlsx` | `sync-run-changes:v1` of `run-20260930-0530`, over kantheon's fixture change stream | the same, through a stub studio-bff |
| `reference-*.csv` | `scripts/sql/{statement,overview,price-sheet,sync-run-changes}-reference.sql` run with psql on the fixture loaded into PostgreSQL 16 | `just verify-overview-reference --write` |
| `overview-schema.sql` | the tables the references read beyond `../evolution/book-schema.sql` (clients, portfolios, the provider's valuation points, the substrate's journal) | — |
| `journal.sql` | a synthetic journal shaped as the substrate writes it (records carry `effects.rows`): the fixture run committed whole, a run with a batch still held, a run with a correction (`reversed`), and a run committed with counts only | — |

The fixture book is `../evolution/fixture-ledger.json` — since IA-P4·S4.3 it carries the provider's own figures the
overviews read (`market_values` per valuation, `valuation_points`), and kantheon's fixture door answers
`client_overview` from them by the program's rules.

Three sides that share no code: the answers `overview-reference.test.mjs` computes in JavaScript from that JSON, the
reference SQL on PostgreSQL, and the renderer's workbooks. `overview-fingerprint.test.mjs` holds the workbooks to the
saved references (no database; in CI); `overview-reference.test.mjs` re-runs the references and holds them to the
JavaScript answers.

Regenerate a workbook when the renderer's template or its fixture door changes, a reference when its SQL does:

    just verify-overview-reference --write     # re-runs the references and rewrites reference-*.csv

A workbook is regenerated through the renderer's own HTTP surface over its hand fixture (kantheon
`./gradlew :services:report-renderer:fixtureServer --args="<port> <artifact dir> <stub studio-bff url>"`): `POST /render`
as `dan` of tenant `hartland` with the parameters in the table above (a bearer on the request — the change log reads
with it), then `GET /artifacts/<id>?principal=dan` (a download is its principal's alone). The stub studio-bff serves
kantheon's `report-renderer/src/test/resources/sync/run-header.json` and `run-changes.ndjson` at
`/api/sync/runs/run-20260930-0530` and `…/changes`. Only the Notes' `Generated` stamp differs between two renders.
