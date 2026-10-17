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
| `30-returns.sql` | `return_request_hdr`, `return_request_line` — history, and the H-2 plants |
| `31-receipts.sql` · `32-settlement.sql` | `return_receipt` · `credit_note`, `refund_payment`, `replacement_shipment` |
| `40-plant.sql` | the H-1, H-3 and H-5 plants (orders, invoices, prices, an outage, stock, `winback_mail`) |
| `45-verify.sql` | nothing — replays the recipes over the plants and **fails the build** on any disagreement |
| `50-expected.sql` · `60-events.sql` | `_automation_expected` (the golden seeds) · `_automation_events` (the demo day's timeline) |
| `../views/return_request.sql`, `../views/document_flow.sql` | the two derived views (`CREATE OR REPLACE`) |
| `80-keys.sql` | the 26 foreign keys, once the data is in (one validating scan each) |

Every step records itself in `_automation_meta`; every planted case is a row of `_automation_plan` (below).
After the transaction the runner writes the seeds and the timeline out as files (below) and prints R-A
(`90-recon.sql`). The steps index the
join paths the recipes take (a customer's orders, lines, invoices and requests; an item at a center; a line's
documents) — `ix_*`, dropped with their tables.

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

**The open orders are clean** before the plants: 17 §3's own context queries (`shortfall`,
`price_differences`, `overdue`) find nothing on them — every open order routes `release` — and `40-plant.sql`
plants each defect of `contracts.md` §5 on top. The open set is `placed_orders` (150) + `held_orders` (3), and
avoids the **outage center** (a hash pick among the warehouses): an outage flags every open line shipping from
it, so exactly `outage_orders` (2) open orders have a line there.

## Per-table derivation spec (H-2)

| table | rows | derivation |
|---|---|---|
| `return_request_line` | one per dated `web_returns` ∪ `catalog_returns` row of an item on a kept, **delivered** order, requested on or before `as_of` | `requested date` = the later of the return date and the delivery (no request for goods still on their way: the returns of an undelivered order are left out); `quantity` = the returned, at most the sold; `unit_price` = the sales line's; the TPC-DS reason mapped to `damaged` · `did_not_arrive` · `wrong_size` · `other` (`automation.conf`); `requested_resolution` refund 6 · exchange 2 · replacement 2 in 10 (a hash); an exchange's `variant` = another item of its class (a hash); `line_id` from `line_id_base` (10⁶) by date; `customer` = the request's |
| `return_request_hdr` | one per (customer, order, requested date) | the **order's** customer (TPC-DS draws a return's customer at random; a request is the buyer's); numbered from 1 by date; ≥ 98 % single-line |
| *history* — every line but the plants | — | decided the day after the request by 17 §4.1's own rules without the two run-time contexts (the 12-month share, the stock): delivered more than `return_window` (30) days before → `rejected` (no way: the recipe sets none); a request above the care threshold → settled by care as a refund after return; small and damaged/undelivered → refund, no return; damaged/undelivered → replacement, no return; an exchange with a variant → exchange; else refund after return — all `closed`, with their documents |
| `return_receipt` | per line whose way expects the goods back | in full, `ok`, 3–10 days after the decision; the plants: below |
| `credit_note` · `refund_payment` | per refunded line | the line's value, a day or two after the decision (no return) or the receipt; paid 1–4 days later |
| `replacement_shipment` | per replaced line | the item (the variant, for an exchange), a day or two after the decision or the receipt |

Every document date is on or before `as_of`. The money parameters (`care_threshold`, `small_value`,
`confirmation_threshold`) are 17 §1's, × `threshold_scale_cz` (25) in the CZ world.

## The plants (contracts §5)

The counts and routes are **`contracts.md` §5** (project `kantheon/features/automation-agents/implementation/
hartland/`) — one source; this is how each is made and what `_automation_plan.kind` it is filed under.
`expected_route` is the route — for the overlapping recipes, the sorted set — the recipe must take on the key.

| kind | key | how |
|---|---|---|
| `release:clean` | order | an open order nothing was planted on → `release` |
| `release:short` · `release:held_yesterday` · `release:both` | order | the first line's pair (that line's alone among the open lines, keeping 3 weeks of cover) set one short of it; held yesterday also `held` / `Sales`; both also overdue |
| `release:outage` | order | the two open orders at the outage center; the center out of service from the day before `as_of` to the day after |
| `release:price_above_list` | order | the first line at 107 % of its price |
| `release:individual_price` | order | a customer price 8 % under the list since `as_of` − 90, the first line priced at it → `release` |
| `release:overdue` | order | the customer's only open order; their latest invoice re-opened, unpaid, due `as_of` − 10 |
| `release:confirm` | order | the dearest line's quantity carries the order to 1.2 × the threshold, its stock covering it → `release_confirmed` |
| `decide:<route>` (8) | line | 40 received lines: picked newest first among single-line requests of the last 21 days, distinct customers and orders, a 12-month share well under the limit; then given what their route needs (one piece; the reason, resolution and variant of their way; the item / variant on stock at the customer's center). **Not ours**: the request names another customer's order. **Late**: delivered before the window. **Abuse**: closed requests returning earlier whole orders of the customer (`request:abuse_history`) carry the share past half |
| `request:multi_line` | request | care + a second line (one task, D-100) · refund after return + an exchange + a refund · refund, no return + a refund after return (`request:added_line` lists every line the plants added) |
| `inbound:expired` · `remind` · `none` · `complete` · `damaged` | line | awaiting the goods, decided 35 / 20 / 10 / 7 / 7 days ago (half exchanges, half refunds after return); complete = received today in full, damaged = one back damaged, one back short. The obligations they hang on are P4's (the note says when) |
| `settle:paid` · `unpaid` · `shipped` · `missing` | line | settling / goods received: credit notes paid today, or issued 12 working days ago and unpaid (7 late); shipments today, or none with the obligation 1 working day late |
| `reorder:propose` | `item:center` | every pair with 8-week demand first has ≥ 4 weeks of stock; 25 hashed pairs nothing else reads then hold 1.5 weeks |
| `winback:list` · `winback:mailed` | customer | 04 H-5 over `sales_order`: ≥ 2 orders in months −18…−6 and none since; premium = the top two income bands. Ten were mailed a month ago (`winback_mail`) and are off the list (route `none`) |

**`45-verify.sql`** replays 17 §3 over every candidate, 17 §4.1 over every received line and H-3's cover rule over
every pair with demand, and **fails the build** if any key routes differently from the plan or any unplanned key
routes at all — the picks are built against a fixture, and a real world differs from it in ways no pick foresees.
`monitor_inbound` and `settle` read obligations (P4); their plants are checked by the suite.

## Expected — the golden seeds (`expected/<world>/<recipe>.csv`)

One file per recipe — `release_order`, `decide_return`, `monitor_inbound`, `settle`, `reorder_proposals`,
`winback` — with one row per planted key and route (`_automation_expected`, from the plan):

| column | holds |
|---|---|
| `key` | the recipe's key (order, line, `item:center`, customer) |
| `route` | one route; an overlapping recipe's key has a row per route (`both` → `hold_ar` and `hold_sales`) |
| `verdict_reason_template` | 17's `because:` with its `{fills}` left in (the comparison fills them first); empty for a recipe that has none yet (H-3, H-5 — P2's) |
| `detail_count` | the rows each detail context of the route carries, `context:rows` (`shortfall:1 price_differences:0`; `receipts:2`; `open_obligations:1` — the obligation P4 seeds) |

A `none` row (monitor_inbound inside the window; a customer mailed inside the win-back window) asserts the key
gets **no** verdict row. The files are the seeds of each recipe's `tests/*.yaml` (contracts §7: no `pinned_from`
— a seed); P3 pins goldens from debug runs. The committed files come from the certification builds (`dsk`); a
build anywhere writes them under `AUTOMATION_OUT` (default: this directory) — the suite writes under `$TMPDIR`.

## Events — the demo day's timeline (`events/<world>.csv`)

`_automation_events (seq, kind, at, payload, demo)`, contracts §6, on the Prague clock: `order_placed
{order_number}` for every open order on its placement day; `line_received {line_id}` for every received line on
its request day; `receipt_posted` / `settlement_posted {line_id}` for every receipt, credit note, payment and
shipment of a line **in flight** (the planted inbound / settle lines) on its day — history's documents are not
events (those lines were settled before the platform ran). `seq` = time order; `demo` flags the 15 events of
the demo day the runbook replays live, its documents first.

`scripts/automation-events.py` (`just automation-events <world> [flags]`) replays the file as webhooks to the
Server's HTTP connector: one `{deployment, event, payload, idempotencyKey: "events:<world>:<seq>"}` per event, the
deployment per kind from `automation.conf` (`events_deployment_*`), the timeline's gaps ÷ `--speed`, 5xx retried
three times, 409 = already posted (fine), any other 4xx stops. `--dry-run` posts nothing; `--demo` replays the
subset; `--from` / `--to` cut the window. `just automation-events-check <world>` validates the file with no
cluster.

## Recon — R-A (`recon/R-A-<world>.md`)

`90-recon.sql` prints, as markdown, every plant kind with its count and route, and every table the build writes
with its rows and a fingerprint (Σ `hashtext(row)`). The build prints it; `just automation-recon <world> [ctx]`
(`run-recon.sh`) diffs it against the committed baseline — exit 0 match · 3 drift (the diff printed) · 2 no
baseline. **Refreshing R-A**: after a deliberate change (a new `as_of`, a changed `automation.conf`, a generator
fix), rebuild (`just automation-reset <w> <ctx> && just automation-data <w> <as-of> <ctx>`), check the print, and
write it with `AUTOMATION_RECON_WRITE=1 just automation-recon <w> <ctx>`; commit the baseline with the change that
moved it. A drift nobody meant is the alarm: the world changed under the extension (a prolong without a rebuild,
a data rebuild) or the generator is not deterministic.

## Reset

`run-reset.sh <ctx> <db> [pod]` (= `just automation-reset <us|cz> [ctx]`), one transaction:

1. every base row the build changed comes back from **`_automation_undo`** — every stock edit goes through
   `pg_temp.au_stock` (10-ddl.sql), which journals the row before it changes it (the first old value wins) and
   every row it inserts; a base row carries no "copy" marker, so without the journal an edit could not be found
   again (the `data/seed` S2 lesson). Everything else the plants change lives in the extension's own tables;
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
| `_automation_plan` | every planted case (`kind`, `key`), what it hangs on (`note`) and the route the recipe must take |
| `_automation_events` | the demo day's event timeline (Events, above) |
| `_automation_expected` | the golden seeds (Expected, above) |

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
| `test-orders.sh` | the H-1 derivation rules, and 17 §3's context queries find the clean open orders clean |
| `test-returns.sh` | requests and lines from the return facts (+ the added lines), ≥ 90 % single-line, history settled with a full document set per way, dates in order and ≤ `as_of`, the derived request state on three requests |
| `test-plants.sh` | every §5 kind at its count, and the recipes replayed in SQL (`probe_release`, `probe_decide`, `probe_reorder`) route every key as planned; the inbound / settle documents and working-day lateness; the win-back list |
| `test-fx.sh` | a CZ world (made the localize-cz way on the scratch copy): every money parameter × 25 |
| `test-expected.sh` | the six seed files, a row per planted key and route, 17's reasons with their `{fills}`, the detail counts |
| `test-events.sh` | the timeline is monotone, every key real as its kind says, nothing after the demo day, the demo subset, the CSV = the table — and the driver's own `check` passes on it |
| `test-recon.sh` | R-A against a baseline: none = 2, itself = 0, a changed row = 3 with the diff |

`scripts/test_automation_events.py` (`just automation-events-test`) specs the driver: the timeline check, the
body, `--dry-run`, the window and demo filters, the speed mapping, retry / 409 / stop (httpx's mock transport).
CI: `.github/workflows/data-gate.yml` runs both suites and checks the committed timelines.

## Files

- `automation.conf` — the frozen parameters (`web_order_offset`, `template_year`, `placed_orders`,
  `open_value_cap`, `confirmation_threshold`, …).
- `run-automation.sh`, `run-reset.sh` — the runners; `lib.sh` — sources `data/extend/lib.sh` (one place knows
  psql: `CTX=<kube-ctx>`, `docker:<container>` or `local`).
- `NN-*.sql` — the steps above; `reset.sql` — the reset; `run-recon.sh` + `90-recon.sql` — R-A.
- `expected/<world>/`, `events/<world>.csv`, `recon/R-A-<world>.md` — committed from the certification builds.
