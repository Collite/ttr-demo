# DC meltdown — stock-outs

**cz** «Výpadky zásob v distribučních centrech» · **us** "DC meltdown — stock-outs" · slugs
`dc-meltdown-stockouts-cz` / `-us`.

## Purpose

The seed incident of the demo world, as a business user sees it in BI. In 2025 one distribution center (DC 5:
Brno DC in cz, Memphis DC in us) ran out of stock in 17 of its weekly inventory snapshots, August to November. The
other four DCs had none. It is the dashboard of the "one number" (contract C-25): its tile says 17. Iris and the
saved query `warehouse_stockout_week_count` say 17 too (act 3.5), and `just bi-one-number <world>` checks all
three (`run-set/bi-one-number/`).

It is also the governance beat: the same dashboard shows each viewer only the DCs their row rule allows (dc-scope,
`kantheon-scope-dc-<n>`). The door applies that rule to every chart's statement, under the viewer's own token.

## Charts (2025, every chart filtered to `month_start` in 2025)

| chart (cz / us) | viz | reads |
|---|---|---|
| «Týdny s výpadkem zásob v roce 2025» / "Stock-out weeks in 2025" | big number | `SUM(stockout_weeks)`: **the one-number tile** |
| «Týdny s výpadkem podle DC, 2025» / "Stock-out weeks per DC, 2025" | table | per DC: stock-out weeks, weeks observed |
| «Týdny s výpadkem po měsících a DC, 2025» / "Stock-out weeks by month and DC, 2025" | stacked bars | per month (P1M) and DC |

## Dataset

`obj.query.stockouts_monthly_dc`: the logical query `def query stockouts_monthly_dc` (`model/er/stockouts.ttrm`),
one row per DC and month, every month on record (2021-01 … 2026-10). A stock-out week is the seed's: a weekly
snapshot in which at least half of the DC's inventory rows were at zero. Saved metrics: `stockout_weeks_sum`,
`weeks_sum` (labelled per world).

## Personas and the numbers they see (measured 2026-10-23 through the edge)

| persona | world | role (scope) | tile | table rows | bars |
|---|---|---|---|---|---|
| marketa | cz | analyst (all DCs) | **17** | 5: Brno DC 17/52, Hradec Králové, Ostrava, Plzeň, Praha DC 0/52 | Brno DC: Aug 5 · Sep 4 · Oct 5 · Nov 3; 5 DCs in the legend |
| petr | cz | DC manager (`kantheon-scope-dc-5`) | **17** | 1: Brno DC 17/52 | the same four bars; only Brno DC in the legend |
| maya | us | analyst (all DCs) | **17** | 5: Memphis DC 17/52, Allentown, Columbus, Dallas, Reno DC 0/52 | Memphis DC: Aug 5 · Sep 4 · Oct 5 · Nov 3 |
| sam | us | DC manager (`kantheon-scope-dc-5`) | **17** | 1: Memphis DC 17/52 | the same four bars, Memphis DC only |

⚠ The tile does not tell the personas apart: only DC 5 stocked out, so the whole estate's 2025 total is DC 5's
17 too. The table and the legend tell them apart (5 DCs vs 1).

The one-number case's `superset` legs name two charts per world by uuid. The tile gives the number: cz
`65572edb-2694-4098-b3ef-761b8ee7e738`, us `dcdb1d8e-96c4-468b-b138-17bf58e2a629`. The per-DC table's row count says
whom Superset read as (5 for the analyst, 1 for the DC manager): cz `4fe88cbc-d951-4118-b6d8-f444f54690fc`, us
`95f3854e-2d6c-40a8-87fd-c2f47f441e98`.
