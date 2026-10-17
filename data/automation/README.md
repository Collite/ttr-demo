# data/automation — the automation extension of a world (AU, step 9 of the data build)

The automation recipes (`automation/`, from P2) need what a TPC-DS world does not have: orders with a state,
price lists, invoices, distribution-center outages, a customer's center, working days (H-1); return requests
with their lines, receipts, credit notes, refunds and replacement shipments (H-2). This directory builds them
**from the world's own facts**, so both worlds get them from one script set, and plants the demo day's cases.
The tables, columns and keys are `contracts.md` §1 (project
`kantheon/features/automation-agents/implementation/hartland/`); the model side is `model/db/{orders,
returns-flow}.ttrm`.

```sh
data/automation/run-automation.sh <kube-ctx> <db> [as-of] [pod]   # defaults: as-of = Monday of the last extended week
just automation-data cz                                           # = run-automation.sh hartland hartland_cz '' hartland-pg-1
just automation-data us 2026-10-26 dsk                            # another day and cluster: positional
just automation-reset cz                                          # undo it (below)
just automation-test                                              # the suite, on a throwaway local Postgres
```

**One transaction**, as the postgres superuser over the pod-local socket (the `data/extend` path); the scripts
create everything as the **owner of the facts** (`hartland`), whose default privileges give `<db>_readonly`
SELECT. The world's currency is read from the database (CZ ⇔ `_localize_meta` holds `czk_fx`; its rate from
`localize-cz/fx.conf`). Refuses `tpc-ds-1g`, and a world that was never extended (`just extend-data` first: the
demo day lies in the extended year). Ends with `ANALYZE` and the `_automation_meta` summary.

**The demo day** (`as_of`) is fixed per build. `_automation_meta` records it: the same day again prints
"already built" and changes nothing; another day is refused until a reset. To move a world to a new day:
`just automation-reset <w> && just automation-data <w> <day>`. **After every prolong** (`just extend-data`) reset
and rebuild too: the new weeks bring newer inventory snapshots than the ones the build gave the open orders, so
17 §3 would find them short.

## How the build runs

`automation.conf` (the frozen parameters) and the steps, in this order, piped as one script:

| step | writes |
|---|---|
| `10-ddl.sql` | the 14 tables, `customer.c_center_sk` + `date_dim.d_working_day`, the internals |
| `20-orders.sql` | `sales_line`, `sales_order` — all history (`released`) |
| `21-pricing.sql` | `price_list`, `customer_price`; opens the demo day's orders (`placed`), priced from them |
| `22-invoices.sql` | `invoice` |
| `23-outages.sql` | `warehouse_outage` |
| `24-centers.sql` | `customer.c_center_sk` |
| `25-calendar.sql` | `date_dim.d_working_day` |
| `26-stock.sql` | `inventory` — the open orders' stock, journaled |
| `../views/return_request.sql`, `../views/document_flow.sql` | the two derived views (`CREATE OR REPLACE`) |
| `80-keys.sql` | the 26 foreign keys, once the data is in (one validating scan each) |

S1.2 adds the returns flow and the plants (`30-`…`40-`), S1.3 the expected verdicts, the event timeline and
the recon (`50-`, `60-`, `90-`).

## Per-table derivation spec (H-1)

Every choice is a hash of a stable key (`abs(hashtext(…))`) or a deterministic order, so a build on the same
base is byte-identical (the suite proves it).

| table | rows | derivation |
|---|---|---|
| `sales_line` | one per **complete** `web_sales` ∪ `catalog_sales` line of a kept order | complete = quantity > 0, amount and warehouse known (TPC-DS leaves ~4 % of each nullable column NULL); `line_no` = the order's lines by item; `unit_price = round(ext_sales_price / quantity, 2)`, the fact's own money (both worlds' facts are already in their currency); `sold_date` and `customer` = the order's |
| `sales_order` | one per kept order | **web order numbers + `web_order_offset` (2·10⁷)**: TPC-DS numbers both channels from 1, so the raw numbers collide (a web order is k·10⁸ + 2·10⁷ + n, a marketplace one k·10⁸ + n). Kept = a complete line, a bill customer, a sold date ≤ `as_of`. `customer` = the modal bill customer, `placed_date` = the first sold date, `fulfilling warehouse` = the modal warehouse of the complete lines, `value` = Σ lines; delivered 3–7 days after placement (hash) when placed more than `delivered_after` (10) days before `as_of`, else NULL; `state` `released`, `placed_by` `shop` |
| `price_list` | two per (item, channel) sold | the **median** unit price of the template year's lines (all its lines if none that year), open-ended from 1 January of the template year; the year before as a closed window at 97 %. The median, not the mode: TPC-DS prices every line on its own, so the mode is just the year's lowest price |
| `customer_price` | ~2 % of the (customer, item) pairs with lines | `hash(customer:item) % 50 = 0`; 90–97 % of the item's lowest open list price, open-ended from the template year |
| *the open orders* | `placed_orders` (150) | 17 §3's candidates. The latest 150 orders placed ≤ `as_of` (a day's ties by a hash) whose value at the price list stays ≤ `open_value_cap` (0.8) × the confirmation threshold (50 000 USD; × 25 = 1 250 000 Kč in CZ); state `placed`, not delivered, every line **re-priced** from the list (the customer's price where valid, else the channel's) — 17 §3 compares a line with its applicable price to the cent, so an open line at its fact's price would be a price difference |
| `invoice` | one per `released` order | issued at delivery (at placement while on its way), due + `payment_days` (14), amount = value, **paid**. S1.2 re-opens the planted customers' |
| `warehouse_outage` | `outages_per_center` (3) per warehouse | 1–3-day windows in the template year, one per third of it (never overlapping), a hashed reason code (`power_failure` · `system_outage` · `stock_count`). None over `as_of`: S1.2 plants that one |
| `customer.c_center_sk` | every customer with lines | the modal warehouse of their lines (ties: the lower sk); NULL for a customer who never ordered |
| `date_dim.d_working_day` | every day | `d_holiday = 'N' AND d_weekend = 'N'` |
| `inventory` (base) | the open orders' (item, warehouse) pairs | 17 §3's `shortfall` reads the pair's **latest** snapshot. TPC-DS stock is uniform 0–1000 with NULLs, so a random open order would be short more often than not; the latest snapshot of every pair an open line needs is raised to the largest such line + a hashed 10–99 (a pair with none gets one at the latest snapshot date). Journaled in `_automation_undo` |
| `return_request` · `document_flow` (views) | — | the model's `definitionSql`, verbatim (`data/views/`) |
| `reorder_proposal` · `winback_mail` | none | written by the H-3 / H-5 recipes (`writable:`) |

**The open orders are clean**: on a fresh build 17 §3's own context queries (`shortfall`,
`price_differences`, `overdue`) find nothing on them — every open order routes `release` — and S1.2 plants
each defect of `contracts.md` §5 on top. The suite runs those queries (`tests/lib-test.sh` `probe_*`).

H-2 (the returns flow) and the plant table: S1.2.

## Reset

`run-reset.sh <ctx> <db> [pod]` (= `just automation-reset <us|cz> [ctx]`), one transaction:

1. every base row the build changed comes back from **`_automation_undo`** — each step journals a base row
   before it changes it (the first old value wins) and every row it inserts; a base row carries no "copy"
   marker, so without the journal an edit could not be found again (the `data/seed` S2 lesson);
2. the extension's views, tables and internals are dropped, with `fk_c_center`;
3. `customer.c_center_sk` and `date_dim.d_working_day` **stay, emptied** — the model maps them.

A world that was never built resets to itself. A reset followed by a build at the same day writes exactly what
the first build wrote.

## Internals (never modelled)

| table | holds |
|---|---|
| `_automation_meta` | one row per step (rows written) and the `build` row with the demo day — the guard |
| `_automation_base` | per fact, its last date and row count at build |
| `_automation_undo` | the journal of base-row changes (`tbl`, `pk` int[], `col`, `old_value`, `inserted`) |
| `_automation_plan` | every planted case and the route the recipe must take (S1.2) |
| `_automation_events` | the demo day's event timeline (S1.3) |

## Tests (`tests/`)

`tests/run-all.sh` (= `just automation-test`) starts a **throwaway local Postgres** — pgserver's server binaries
through `uv` (`tests/pg-local.sh`), no Docker, no cluster — loads `tests/fixture.sql` into `au_fixture`, and
runs every `test-*.sh` on its own scratch copy (`CREATE DATABASE … TEMPLATE`). The fixture is a small
TPC-DS-shaped world that keeps the shapes the generator must survive: overlapping web/marketplace order numbers,
NULLs in the nullable fact columns, dense weekly inventory with NULL and zero stock, `_extend_meta`.
`tests/run-all.sh <ctx> <db> [pod]` runs the same scripts against another server's database (scratch copies
only). `ONLY=<name>` picks scripts; `KEEP_SCRATCH=1` keeps the copies.

| script | checks |
|---|---|
| `test-ddl.sh` | contracts §1 exactly: every table's columns (order, types) and primary key, the 26 foreign keys validated, the two column adds, the two views, the internals, the owner; the money is the facts' own |
| `test-determinism.sh` | two fresh copies built at the same day hold byte-identical rows in every table the build writes |
| `test-idempotent.sh` | the same day again: "already built", no row changes; another day: refused ("reset first"), nothing changes |
| `test-reset.sh` | the base tables come back byte for byte, nothing of the extension is left, the added columns are empty, a second reset is a no-op, a rebuild equals the first build |
| `test-orders.sh` | the derivation rules above, and 17 §3's context queries find the open orders clean |

## Files

- `automation.conf` — the frozen parameters (`web_order_offset`, `template_year`, `placed_orders`,
  `open_value_cap`, `confirmation_threshold`, …).
- `run-automation.sh`, `run-reset.sh` — the runners; `lib.sh` — sources `data/extend/lib.sh` (one place knows
  psql: `CTX=<kube-ctx>`, `docker:<container>` or `local`).
- `NN-*.sql` — the steps above; `reset.sql` — the reset.
