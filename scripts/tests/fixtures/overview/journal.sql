-- IA-P4·S4.3·T6 — a SYNTHETIC journal for `sync-run-changes-reference.sql`, shaped as the substrate writes it: a record
-- committed with `?detail=rows` carries its per-proposal `effects.rows` (IA-C15), one row per proposal, and its counts are
-- `Effects.from` those rows — a `reversed` (ledger correction) or `closed` (SCD2) row counts one `inserted` besides its
-- own count; `unchanged` and `rejected` count nothing (IA-C13 v1.2).
--
--   run-20260930-0530  the run of kantheon's fixture change stream (`report-renderer/src/test/resources/sync/`:
--                      2 movements inserted, 1 updated, 61 prices) — committed whole, with rows
--   run-held           one batch committed and one still held — refused, not compared
--   run-correction     committed with rows: a new movement, a CORRECTION (reversed), an unchanged row and a refused one
--                      — 2 changed movements (IA-P4 review R5)
--   run-counts         committed with counts only (no rows: a commit without `?detail=rows`, S1.4·D11) — refused: its
--                      change log cannot list the rows (R5)
INSERT INTO journal_batch (batch_id, kind, target_ref, model_version, payload, source_plugin_id, source_ref) VALUES
  ('b-1', 'proposal', 'investment.transaction', 'investment-v1', '{}', 'conseq-distrinfo', 'conseq/hartland/run-20260930-0530/transactions/1'),
  ('b-2', 'proposal', 'investment.transaction', 'investment-v1', '{}', 'conseq-distrinfo', 'conseq/hartland/run-20260930-0530/transactions/2'),
  ('b-3', 'proposal', 'investment.asset_price', 'investment-v1', '{}', 'conseq-distrinfo', 'conseq/hartland/run-20260930-0530/prices/1'),
  ('h-1', 'proposal', 'investment.asset_price', 'investment-v1', '{}', 'conseq-distrinfo', 'conseq/hartland/run-held/prices/1'),
  ('h-2', 'proposal', 'investment.transaction', 'investment-v1', '{}', 'conseq-distrinfo', 'conseq/hartland/run-held/transactions/1'),
  ('c-1', 'proposal', 'investment.transaction', 'investment-v1', '{}', 'conseq-distrinfo', 'conseq/hartland/run-correction/transactions/1'),
  ('n-1', 'proposal', 'investment.transaction', 'investment-v1', '{}', 'conseq-distrinfo', 'conseq/hartland/run-counts/transactions/1');
INSERT INTO entry_record (entry_id, batch_id, run_id, target_ref, semantics, payload) VALUES
  ('ent-b-1', 'b-1', 'apply-1', 'investment.transaction', 'ledger',
   '{"effects":{"inserted":2,"updated":0,"closed":0,"reversed":0,"rows":[{"index":0,"outcome":"inserted"},{"index":1,"outcome":"inserted"}]}}'),
  ('ent-b-2', 'b-2', 'apply-2', 'investment.transaction', 'ledger',
   '{"effects":{"inserted":0,"updated":1,"closed":0,"reversed":0,"rows":[{"index":3,"outcome":"unchanged"},{"index":4,"outcome":"updated"}]}}'),
  ('ent-h-1', 'h-1', 'apply-4', 'investment.asset_price', 'scd1',
   '{"effects":{"inserted":5,"updated":0,"closed":0,"reversed":0,"rows":[{"index":0,"outcome":"inserted"},{"index":1,"outcome":"inserted"},{"index":2,"outcome":"inserted"},{"index":3,"outcome":"inserted"},{"index":4,"outcome":"inserted"}]}}'),
  ('ent-c-1', 'c-1', 'apply-5', 'investment.transaction', 'ledger',
   '{"effects":{"inserted":2,"updated":0,"closed":0,"reversed":1,"rows":[{"index":0,"outcome":"inserted"},{"index":1,"outcome":"reversed"},{"index":2,"outcome":"unchanged"},{"index":3,"outcome":"rejected"}]}}'),
  ('ent-n-1', 'n-1', 'apply-6', 'investment.transaction', 'ledger',
   '{"effects":{"inserted":3,"updated":1,"closed":0,"reversed":0}}');
-- the 61 price rows of b-3, one per proposal
INSERT INTO entry_record (entry_id, batch_id, run_id, target_ref, semantics, payload)
SELECT 'ent-b-3', 'b-3', 'apply-3', 'investment.asset_price', 'scd1',
       json_build_object('effects', json_build_object('inserted', 61, 'updated', 0, 'closed', 0, 'reversed', 0,
           'rows', (SELECT json_agg(json_build_object('index', i, 'outcome', 'inserted') ORDER BY i) FROM generate_series(0, 60) i)))::text;
