-- IA-P4·S4.3·T6 — `sync-run-changes:v1`'s counts, computed on the substrate's journal with plain PostgreSQL: the
-- reference its workbook is fingerprinted against (IA-C51; `scripts/fingerprint-overview.sh`).
--
-- ## What it mirrors (contracts IA-C16, IA-C20) — the journal itself, not studio-bff's projection
--
--   * the run's batches: `journal_batch` rows whose `source_ref` names the run (`conseq/{tenant}/{runId}/…`);
--   * what each committed batch changed: its `entry_record`'s `effects` — `inserted + updated` per target (the
--     projection's own count for a record committed without rows, S1.4·D11).
--
-- ⛔ COMMITTED runs only: a held batch's changes are a preview, which the journal does not record — such a run is
-- refused (`refused`), not compared. And it reads the journal, which the book's read-only role (`entry_readonly`) does
-- not see: run it as a role that may read `journal_batch` and `entry_record`.
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
           COALESCE((r.payload::json -> 'effects' ->> 'inserted')::int, 0)
             + COALESCE((r.payload::json -> 'effects' ->> 'updated')::int, 0) AS changed
      FROM batch b
      LEFT JOIN entry_record r ON r.batch_id = b.batch_id
), refusal AS (
    SELECT CASE WHEN (SELECT COUNT(*) FROM batch) = 0 THEN 'the journal holds no batch of this run'
                WHEN (SELECT COUNT(*) FROM effect WHERE NOT committed) > 0
                  THEN (SELECT COUNT(*) FROM effect WHERE NOT committed)
                       || ' batch(es) of the run are not committed — the journal records only committed effects'
                ELSE '' END AS refused
)
SELECT t.target_ref AS target, t.batches, t.committed, t.changed, refusal.refused
  FROM (SELECT target_ref, COUNT(*) AS batches, COUNT(*) FILTER (WHERE committed) AS committed, SUM(changed) AS changed
          FROM effect GROUP BY target_ref) t
 CROSS JOIN refusal
UNION ALL
SELECT NULL, 0, 0, 0, refusal.refused FROM refusal WHERE NOT EXISTS (SELECT 1 FROM batch)
 ORDER BY 1;
