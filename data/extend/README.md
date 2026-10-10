# data/extend — keep the worlds current (LR-P4, contracts C-8)

The demo data ends where TPC-DS SF1 ends after the +23-year redate: sales on **2026-01-02**
(store, web) and **2026-01-08** (marketplace), inventory on **2025-12-26**. A question about
*„minulý měsíc“* or *"last month"* on a later date then lands in an empty month. `run-extend.sh`
copies the **template year 2024** (⚑LR-10) forward, week by week, so the facts reach the date
you name, and it can be re-run later to prolong them ("prolong before a show").

```sh
data/extend/run-extend.sh <kube-ctx> <db> <until-date> [pod]     # defaults: dsk hartland_us today hartland-pg-1
just extend-data cz 2026-10-31                                  # = run-extend.sh hartland hartland_cz 2026-10-31 hartland-pg-1
just extend-data us 2026-10-31 dsk                              # another cluster: name its context
```

Single transaction, superuser over the pod-local socket (the `run-redate.sh` path). Refuses
`tpc-ds-1g`. Ends with an `ANALYZE` of the seven facts and an `_extend_meta` summary.

## How a week is copied

`date_dim`'s `d_date_sk` is a consecutive day number and `d_week_seq` a 7-day block (Tue–Mon),
so **364 days later is exactly 52 weeks later**, on the same weekday.

- **Template window** = the 52 `d_week_seq`s that lie wholly inside 2024 (2024-01-02 ..
  2024-12-30). 2024 is a normal year in both worlds: the meltdown seeds (S1–S3) touch 2025 only.
- **Target week** `w` → template week `t = ws0 + ((w − ws0) mod 52)`, cycle `k = (w − ws0) div 52`
  (`ws0` = the window's first week). A template row moves `364·k` days. For every 2026 week
  `k = 2`; the "Dec 29–31" days of a year fall into the next cycle's first template week.
- **Base end** — `_extend_base` records, on the first run, each fact's last original date. A
  target row is written only if its date is after its fact's base end, so the partial weeks at
  the seam (2026-01-03..05 for store/web, 2026-01-09..12 for marketplace) fill exactly the days
  the original data lacks.
- **Whole weeks.** A run extends every week up to and including the one that holds `until`
  (data may run up to 6 days past it). `_extend_meta` records each processed week, so a re-run
  with a later date adds only the new weeks, and a re-run with the same or an earlier date is a
  no-op.

## Per-table copy spec

| table | template rows | date columns | key | other columns |
|---|---|---|---|---|
| `store_sales` | sold in the template week (`ss_sold_date_sk`) | every `*_date_sk` + 364·k | `ss_ticket_number` + order_offset·k (item unchanged) | money × jitter, `ss_quantity` × jitter, the rest verbatim |
| `catalog_sales` | `cs_sold_date_sk` in the template week | `cs_sold_date_sk`, `cs_ship_date_sk` + 364·k | `cs_order_number` + order_offset·k | as above (`cs_warehouse_sk` verbatim — the DC mix is 2024's, i.e. **recovered**) |
| `web_sales` | `ws_sold_date_sk` in the template week | `ws_sold_date_sk`, `ws_ship_date_sk` + 364·k | `ws_order_number` + order_offset·k | as above |
| `store_returns` | returns of a **copied** store sale (joined on ticket + item) | `sr_returned_date_sk` + 364·k (k = its sale's cycle) | `sr_ticket_number` + order_offset·k | money / `sr_return_quantity` × the SAME jitter as its sale |
| `catalog_returns` | returns of a copied catalog sale (order + item) | `cr_returned_date_sk` + 364·k | `cr_order_number` + order_offset·k | as above |
| `web_returns` | returns of a copied web sale (order + item) | `wr_returned_date_sk` + 364·k | `wr_order_number` + order_offset·k | as above |
| `inventory` | snapshots in the template week | `inv_date_sk` + 364·k | (date, item, warehouse) — unique by target week | `inv_quantity_on_hand` × jitter (0 stays 0) |

Dimensions are untouched; `channel_sales` is a view over the facts and needs no re-run.

**Returns follow their sale.** TPC-DS returns trail their sale by up to ~9 months (catalog p99
254 days). A return is copied when its *sale* was copied, with the sale's shift, into the run
that covers the return's target week. So every extended return has its extended sale (no
orphans), the lag is kept, and the original trailing returns of 2025 sales (which run into
2026-09) are not doubled by template returns. No return is written past the extended weeks; a
later prolong picks up the rest. (This refines C-8·3's "template rows whose *return* date falls
in the target week" — the same week rule, restricted to returns of copied sales.)

**Not copied:** sales rows with a NULL sale date (~4.5 % in TPC-DS; they never appear in a
date-filtered question). A return with a NULL return date goes into its sale's week.

## Keys, jitter, rounding (C-8·4–5, 7)

- **Keys:** `*_order_number` / `*_ticket_number` + `order_offset × k` (`extend.conf`, 1e9). The
  original numbers stay below 240 001, so every copy is distinct by construction and an extended
  row is recognisable (order number ≥ 1e9). ⛔ The columns are `integer`: `2e9 + 240 000` fits,
  **k = 3 does not** (2026-12-29 onward). The script refuses with a clear error before writing.
- **Jitter:** each copied line's amounts and quantities × `1 + ((|hashtext(new_order || item)| mod 401) − 200) / 10 000`
  (±2 %, deterministic; returns use their sale's factor; inventory hashes date‖item‖warehouse).
  C-8·5 wrote `hashtext(…) % 401` without the `abs`; a negative hash would skew it to −6..+2 %.
- **Rounding per world**, detected in the database: a world with `_localize_meta.czk_fx`
  (CZ) rounds like `localize-cz/02-czk-fx.sql` — nearest 10 Kč at ≥ 100 Kč, haléře below; any
  other world rounds to the column's scale.

## Tests (`tests/`)

| script | checks |
|---|---|
| `test-incremental.sh <ctx> <db> [pod]` | on a scratch copy: to 2026-03-31, then 2026-06-30 adds exactly the weeks between and leaves earlier weeks untouched; a third run with the same date and one with an earlier date are no-ops |
| `test-determinism.sh <ctx> <db> [pod] [until]` | two scratch copies — one prolonged in two steps, one in one — hold byte-identical extended rows (md5 per table) and identical `_extend_meta` |
| `test-keys.sh <ctx> <db> [pod]` | unique keys in every fact, extended order numbers ≥ 1e9 and originals below, every extended return has its extended sale, `date_dim` covers 2026–2030 |
| `test-story.sh <ctx> <db> [pod]` | in extended weeks: meltdown-DC share of marketplace revenue ≈ 20 % (±1 pt), DC-5 zero-inventory share < 0.2 %, late-delivery reason share at DC 5 < 5 %, and per channel the last whole month's returns-to-revenue ratio within 1 pt of the same month of 2024 (the task's "≈ 5 %" is the annual ratio; per month TPC-DS runs 2–12 %) |
| `test-world-neutral.sh <ctx> <db> [pod]` | CZ: every extended amount ≥ 100 is a multiple of 10 Kč; US: the 10 Kč rule is not applied and amounts keep 2 decimals |

`incremental` and `determinism` work on throwaway copies (`CREATE DATABASE … TEMPLATE`) and drop
them (`KEEP_SCRATCH=1` keeps them). The other three read an already-extended database.

The `<ctx>` of every script may be `docker:<container>` — a throwaway local Postgres, never a
shared cluster — which is how they were developed (see the PR).

## Files

- `extend.conf` — `template_year`, `jitter_bp`, `order_offset`, `meltdown_sk` (documentation only:
  the meltdown DC is recovered in extended weeks because 2024 is the template).
- `extend.sql` — the transaction (`psql -v until=YYYY-MM-DD -f extend.sql`).
- `run-extend.sh` — the runner; `lib.sh` — the psql seam shared with the tests.
