# data — the two-world data build

Produces `hartland_us` (EN/USD) and `hartland_cz` (CZ/CZK) and their versioned demo dumps
(`tpcds-staging/hartland/{us,cz}/`). Pipeline order (per stage; see `design/plan-demo-build.md`
Phase 1):

1. `redate/` — `run-redate.sh <host> 23 <db>` (+23y; refuses to run against `tpc-ds-1g`).
2. `localize-cz/` — CZ geography (stores/addresses/DCs incl. Brno), CZK conversion, cs reasons.
   2b. `calendar/` — `date_dim` corrected from `d_date` (`just calendar-data <us|cz> [ctx]`): dsdgen cuts the
   quarters on a 366-day year (non-leap 04-01, 07-01, 10-01 fall in the quarter before), puts the weekend on
   Friday + Saturday and dates two of its three holidays a day late. Quarters, weekday and a Saturday + Sunday
   weekend from the date; the holidays become the world's own (cz: the 13 Czech days off, Easter computed; us:
   the 11 federal holidays and their observed weekdays). Found by the D-134 routing case d1, 2026-10-20.
3. `catalog/` — the bilingual per-item catalog: taxonomy + generator → `catalog/{us,cz}` UPDATEs.
4. `seed/` — `02-seed-incident` — Memphis DC (us) / Brno DC (cz) meltdown S1–S4.
5. `recon/` — the recon battery + committed baselines; R0 freeze; `pg_dump` → staging.
6. `views/` — derived views the model binds to (`channel_sales.sql`: the three sales facts as one
   relation, labelled by channel). Idempotent (`CREATE OR REPLACE`); run in both worlds as the
   tables' owner. Views read the facts live, so they need no re-run after a data rebuild — only
   after a DROP.
7. `extend/` — copy 2024 forward so the facts reach a date you name (LR-P4); re-run before a show.
8. `automation/` — the automation extension (AU): the H-1/H-2 ERP tables derived from the facts for one
   demo day, with its planted cases (`just automation-data <us|cz> [as-of] [ctx]`; `automation/README.md`).

All scripts idempotent + hash-keyed (deterministic). Item keys + category assignments are
invariants (the seeds key on warehouse×week, not item).

## Disaster-recovery / rebuild recipe (Stage 1.6 T5)

Every world is rebuildable from `tpc-ds-1g` + the committed scripts, each step idempotent or
snapshot-guarded:

1. `pg_dump tpc-ds-1g` → restore into a fresh DB (US: adopt the standing `hartland`→`hartland_us`
   rename per Stage 1.2 T1; CZ: `createdb hartland_cz` + restore).
2. `redate/run-redate.sh <ctx> 23 <db>` (guarded — refuses a second run).
3. CZ only: `localize-cz/00-widen-money-columns.sql` → `01-geography.sql` → `02-czk-fx.sql`
   (guarded via `_localize_meta`) → `03-reasons.sql`.
   3b. `calendar/run-calendar.sh <ctx> <db> <us|cz>` (idempotent; after step 3, whose `czk_fx` row tells it the
   world). On a world whose automation extension is built: `just automation-reset` first, `just automation-data`
   after — the working days and the due dates follow the calendar.
4. `catalog/us.sql` / `catalog/cz.sql` (idempotent, PK-keyed).
5. `seed/naming-us.sql` (US only) + `seed/reason-placeholders-fix.sql` (both, `:locale` param) +
   `seed/02-seed-incident/{s1,s2,s3}-*.sql` (guarded via `_seed_meta` — S2 is genuinely
   non-idempotent by nature, deletion, so the guard is load-bearing there).
6. `recon/run-recon.sh dsk <db>` → diff against `data/recon/R0.md`.
7. `views/channel_sales.sql` (both worlds, as `hartland`) — `er.entity.channel_sales` reads it.
   Re-run it on a world that already has the view whenever the script changes: LR ⚑LR-9 appended
   `warehouse_sk`, which the DC-scope row rule filters on, so the model's column must exist in the
   database before that rule is mounted (`SELECT warehouse_sk FROM channel_sales LIMIT 1` checks it).
8. `extend/run-extend.sh <ctx> <db> <until>` (`just extend-data <us|cz> <until> [ctx]`) — copies
   the template year 2024 forward week by week so the facts reach `<until>` (LR-P4, contracts C-8;
   `extend/README.md`). Incremental: `_extend_meta` holds the weeks already done. After a rebuild
   (steps 1–7) the world ends 2026-01-08 again — re-run this step.
9. `automation/run-automation.sh <ctx> <db> [as-of]` (`just automation-data <us|cz> [as-of] [ctx]`) — after step
   8, the H-1/H-2 tables of the automation recipes for one demo day (AU P1; `automation/README.md`). Guarded by
   `_automation_meta`; a different day needs `just automation-reset` first. A rebuild (steps 1–7) drops the
   world, so re-run this step too.

**Prolong before a show.** The data does not move with the calendar: on the day of a show, run
`just extend-data <world> <end of this month>` for the world on stage, then refresh the R1 figures
the script quotes (`recon/R1.md`, "Refreshing R1"). A re-run with a date already covered is a no-op.

**Retained snapshots** (`data/dr-snapshots.md`): the US pre-catalog dump (Stage 1.2 T1) is a
physical rollback point in `tpcds-staging/hartland/us/`. The CZ pre-seed state was **not**
separately snapshotted — steps 1–4 above are fully deterministic and idempotent, so the
pre-seed `hartland_cz` state is reproducible byte-for-byte from `tpc-ds-1g` + the committed
scripts rather than needing its own physical dump (the fallback this stage's spec explicitly
allows).
