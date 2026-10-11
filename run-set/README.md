# run-set — the hartland-query e2e run-set

The sibling of the retired `tpcds-query` context (Q-BM-7: DB retired, `tpc-ds-1g` dump kept).
Oracle rows for the 15 `q.hartland.*` queries on BOTH worlds (US in USD, CZ = US ×FX). Pointed at
the standing cluster estate; run by `just demo-check hartland` and by the nightlies on every
cluster (bp-dsk, collite-o1, hartland) against the shared `hartland-pg` (BM-10).
