# Returns by category

**cz** «Reklamace podle kategorie» · **us** "Returns by category" · slugs `returns-by-category-cz` / `-us`.

## Purpose

The returns side of the demo world in BI: what came back in 2025, by item category. It reads BI's own logical query
over the return requests (⚑BI-4-A). SO's `returns_review` report stays on its demo branch until it reaches master;
then this dashboard's tile can be checked against the Studio report's total, as C-25 planned.

It is also a governance contrast to the DC meltdown dashboard: no row rule covers returns, so a DC manager sees the
same numbers as the analyst. The dc-scope rule narrows `inventory` and `warehouse`, the tables it governs, and
nothing else.

## Charts (2025, every chart filtered to `month_start` in 2025)

| chart (cz / us) | viz | reads |
|---|---|---|
| «Řádky reklamací v roce 2025» / "Return lines in 2025" | big number | `SUM(lines)`, the return lines filed in 2025 |
| «Reklamace podle kategorie zboží, 2025» / "Return requests by item category, 2025" | bars | requests per category |
| «Reklamace po kategoriích, 2025» / "Returns by category, 2025" | table | per category: requests, lines, units, amount, open lines |

**Why the tile counts lines and not requests:** a request whose lines span two categories counts as a request in
each of them. So the categories' requests add up to more than the requests filed: 41 949 vs 41 849 in 2025.
Lines belong to one category each and add up exactly. For the same reason the table has no totals row.

## Dataset

`obj.query.returns_monthly_by_category`: the logical query `def query returns_monthly_by_category`
(`model/er/returns-by-category.ttrm`), one row per item category and month, over `return_request_line JOIN
return_request JOIN item`. Saved metrics: `requests_sum`, `lines_sum`, `units_sum`, `amount_sum`, `open_lines_sum`.

## Personas and the numbers they see (measured 2026-10-23 through the edge)

| persona | world | tile | bars (requests, 2025) |
|---|---|---|---|
| marketa, petr | cz | **41 962** | Electronics 4 332 · Shoes 4 330 · Home 4 288 · Music 4 277 · Women 4 180 · Men 4 159 · Children 4 153 · Sports 4 115 · Books 4 041 · Jewelry 3 964 · no category 110 |
| maya, sam | us | **41 962** | the same counts (the worlds share the seed's returns; the amounts differ: CZK vs USD) |

The category names come from the data, so they are English in both worlds. A NULL category (110 requests of items
with no category) shows as `<NULL>`. Open lines are 0 for 2025, because every 2025 request is closed.
