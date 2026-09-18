# run-set — the hartland-query e2e run-set

The sibling of the retired `tpcds-query` context (Q-BM-7: DB retired, `tpc-ds-1g` dump kept).
Oracle rows for the 15 `q.hartland.*` queries on BOTH worlds (US in USD, CZ = US ×FX). Pointed at
the standing cluster estate; run by `just demo-check hartland` and by the nightlies on every
cluster (bp-dsk, collite-o1, hartland) against the shared `hartland-pg` (BM-10).

## The investment eval sheet is no longer kept here either (2026-09-18)

`investment-questions.md` — the ten-question eval sheet for the investment Shem — **moved to the
private project repository** on 2026-09-18, for the reason in the next section: it is scored against
the live estate, so its pass rules quote a real portfolio's positions, cash and quarterly values.

Only that one file left. The `hartland-query` run-set below — `cases/`, and the `oracle/` and
`queries/` the nightly case-runner reads — stays here, where ⚑N-5 / BM-9 puts it.

## Investment report fingerprints are deliberately NOT kept here (IE-P3·S3.3·D8)

`just drill-in-cluster fingerprint --save` produces a fingerprint of the investment report: its quarter
rows for one portfolio, the oracle a rehearsal is held to. Those rows are a real portfolio's balances, and
this repository is public — so the scripts refuse to write one anywhere inside it, and the rehearsal
fingerprints live in the private project repository (ruled 2026-09-14).
