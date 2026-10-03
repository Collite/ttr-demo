-- IA-P4·S4.3·T6 — a SYNTHETIC journal for `sync-run-changes-reference.sql`: run `run-20260930-0530` — the run of
-- kantheon's fixture change stream (`report-renderer/src/test/resources/sync/`: 2 movements inserted, 1 updated, 61
-- prices) — committed whole; and `run-held`, one batch committed and one still held (refused, not compared).
INSERT INTO journal_batch (batch_id, kind, target_ref, model_version, payload, source_plugin_id, source_ref) VALUES
  ('b-1', 'proposal', 'investment.transaction', 'investment-v1', '{}', 'conseq-distrinfo', 'conseq/hartland/run-20260930-0530/transactions/1'),
  ('b-2', 'proposal', 'investment.transaction', 'investment-v1', '{}', 'conseq-distrinfo', 'conseq/hartland/run-20260930-0530/transactions/2'),
  ('b-3', 'proposal', 'investment.asset_price', 'investment-v1', '{}', 'conseq-distrinfo', 'conseq/hartland/run-20260930-0530/prices/1'),
  ('h-1', 'proposal', 'investment.asset_price', 'investment-v1', '{}', 'conseq-distrinfo', 'conseq/hartland/run-held/prices/1'),
  ('h-2', 'proposal', 'investment.transaction', 'investment-v1', '{}', 'conseq-distrinfo', 'conseq/hartland/run-held/transactions/1');
INSERT INTO entry_record (entry_id, batch_id, run_id, target_ref, semantics, payload) VALUES
  ('ent-b-1', 'b-1', 'apply-1', 'investment.transaction', 'ledger', '{"effects":{"inserted":2,"updated":0,"closed":0,"reversed":0}}'),
  ('ent-b-2', 'b-2', 'apply-2', 'investment.transaction', 'ledger', '{"effects":{"inserted":0,"updated":1,"closed":0,"reversed":0}}'),
  ('ent-b-3', 'b-3', 'apply-3', 'investment.asset_price', 'scd1', '{"effects":{"inserted":61,"updated":0,"closed":0,"reversed":0}}'),
  ('ent-h-1', 'h-1', 'apply-4', 'investment.asset_price', 'scd1', '{"effects":{"inserted":5,"updated":0,"closed":0,"reversed":0}}');
