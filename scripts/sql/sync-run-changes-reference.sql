-- IA-P4·S4.3·T6 — `sync-run-changes:v1`'s counts, computed on the substrate's journal with plain PostgreSQL: the
-- reference its workbook is fingerprinted against (IA-C51; `scripts/fingerprint-overview.sh`).
--
-- ## What it mirrors (contracts IA-C16, IA-C20) — the journal itself, not studio-bff's projection
--
--   * the run's batches: `journal_batch` rows whose `source_ref` names the run (`conseq/{tenant}/{runId}/…`);
--   * what each committed batch changed: its `entry_record`'s `effects` — `inserted + updated` per target. Those counts
--     are `Effects.from` the record's rows (IA-C13 v1.2): a ledger CORRECTION (`reversed`) and an SCD2 `closed` row each
--     count one `inserted` — so a correction is a changed movement, and the workbook counts every listed row whose
--     outcome is inserted, updated, closed or reversed (IA-P4 review R5).
--
-- ⛔ COMMITTED runs only: a held batch's changes are a preview, which the journal does not record — such a run is
-- refused (`refused`), not compared.
-- ⛔ Committed WITH ROWS only: a record committed without `?detail=rows` (S1.4·D11) carries counts and no `effects.rows`,
-- so the change log counts its rows but cannot list one — comparing its listing with the counts would be comparing a
-- part with the whole. Such a run is refused, naming how many batches (`undetailed`).
-- And it reads the journal, which the book's read-only role (`entry_readonly`) does not see: run it as a role that may
-- read `journal_batch` and `entry_record`.
--
-- ## Use
--
--   psql "$DSN" -X -q --csv -v ON_ERROR_STOP=1 -v run=<runId> -f scripts/sql/sync-run-changes-reference.sql
--
-- One read-only statement. One row per target; `refused` the same on every row.

WITH prm AS (
    SELECT CAST(:'run' AS TEXT) AS run
), batch AS (
    SELECT b.batch_id, b.target_ref
      FROM journal_batch b, prm
     WHERE split_part(b.source_ref, '/', 3) = prm.run
), effect AS (
    SELECT b.batch_id, b.target_ref,
           r.entry_id IS NOT NULL AS committed,
           r.entry_id IS NOT NULL
             AND json_typeof(r.payload::json -> 'effects' -> 'rows') IS DISTINCT FROM 'array' AS undetailed,
           COALESCE((r.payload::json -> 'effects' ->> 'inserted')::int, 0)
             + COALESCE((r.payload::json -> 'effects' ->> 'updated')::int, 0) AS changed
      FROM batch b
      LEFT JOIN entry_record r ON r.batch_id = b.batch_id
), refusal AS (
    SELECT CASE WHEN (SELECT COUNT(*) FROM batch) = 0 THEN 'the journal holds no batch of this run'
                WHEN (SELECT COUNT(*) FROM effect WHERE NOT committed) > 0
                  THEN (SELECT COUNT(*) FROM effect WHERE NOT committed)
                       || ' batch(es) of the run are not committed — the journal records only committed effects'
                WHEN (SELECT COUNT(*) FROM effect WHERE undetailed) > 0
                  THEN (SELECT COUNT(*) FROM effect WHERE undetailed)
                       || ' batch(es) of the run were committed with counts only (no rows) — its change log counts their'
                       || ' rows but cannot list them; pick a run committed with rows'
                ELSE '' END AS refused
)
SELECT t.target_ref AS target, t.batches, t.committed, t.undetailed, t.changed, refusal.refused
  FROM (SELECT target_ref, COUNT(*) AS batches, COUNT(*) FILTER (WHERE committed) AS committed,
               COUNT(*) FILTER (WHERE undetailed) AS undetailed, SUM(changed) AS changed
          FROM effect GROUP BY target_ref) t
 CROSS JOIN refusal
UNION ALL
SELECT NULL, 0, 0, 0, 0, refusal.refused FROM refusal WHERE NOT EXISTS (SELECT 1 FROM batch)
 ORDER BY 1;
