# data — the two-world data build

Produces `hartland_us` (EN/USD) and `hartland_cz` (CZ/CZK) and their versioned demo dumps
(`tpcds-staging/hartland/{us,cz}/`). Pipeline order (per stage; see `design/plan-demo-build.md`
Phase 1):

1. `redate/` — `run-redate.sh <host> 23 <db>` (+23y; refuses to run against `tpc-ds-1g`).
2. `localize-cz/` — CZ geography (stores/addresses/DCs incl. Brno), CZK conversion, cs reasons.
3. `catalog/` — the bilingual per-item catalog: taxonomy + generator → `catalog/{us,cz}` UPDATEs.
4. `seed/` — `02-seed-incident` — Memphis DC (us) / Brno DC (cz) meltdown S1–S4.
5. `recon/` — the recon battery + committed baselines; R0 freeze; `pg_dump` → staging.
6. `views/` — derived views the model binds to (`channel_sales.sql`: the three sales facts as one
   relation, labelled by channel). Idempotent (`CREATE OR REPLACE`); run in both worlds as the
   tables' owner. Views read the facts live, so they need no re-run after a data rebuild — only
   after a DROP.

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
4. `catalog/us.sql` / `catalog/cz.sql` (idempotent, PK-keyed).
5. `seed/naming-us.sql` (US only) + `seed/reason-placeholders-fix.sql` (both, `:locale` param) +
   `seed/02-seed-incident/{s1,s2,s3}-*.sql` (guarded via `_seed_meta` — S2 is genuinely
   non-idempotent by nature, deletion, so the guard is load-bearing there).
6. `recon/run-recon.sh dsk <db>` → diff against `data/recon/R0.md`.
7. `views/channel_sales.sql` (both worlds, as `hartland`) — `er.entity.channel_sales` reads it.

**Retained snapshots** (`data/dr-snapshots.md`): the US pre-catalog dump (Stage 1.2 T1) is a
physical rollback point in `tpcds-staging/hartland/us/`. The CZ pre-seed state was **not**
separately snapshotted — steps 1–4 above are fully deterministic and idempotent, so the
pre-seed `hartland_cz` state is reproducible byte-for-byte from `tpc-ds-1g` + the committed
scripts rather than needing its own physical dump (the fallback this stage's spec explicitly
allows).
