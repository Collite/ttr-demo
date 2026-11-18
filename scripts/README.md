# scripts/ — the automation driver and the engine processes

Most scripts here document themselves in their header. This page covers the AU-hartland P4·S4.1 pieces that work
together: the engine exports, the authored processes and the demo-day driver.

## The deployment set

`processes/sets.json` names one **deployment set** per cluster: `cz` = bp-dsk (the CZ program twins; bp-dsk serves CZ
data only, D-139). Never deploy two sets on one engine: two definitions cannot both start on `order_placed`.

## Exports → processes → engine

| step | command | writes |
|---|---|---|
| emit the set's five deployments | `just automation-export cz` | `exports/<deployment>/` (BPMN skeleton, DMN, element templates, README) |
| compose the authored processes | `just compose-processes cz` | `processes/cz/{release_order,release_morning,return_request}.bpmn` |
| drift gate | `just compose-processes cz --check` | nothing; exit 1 if `processes/` is stale |
| deploy | `TTR_BEARER=… ENGINE_URL=… just automation-deploy cz` | the five engine deployments (`ttrp emit --deploy`), then the three processes as `hartland-processes-cz` |
| check the deployments | `just automation-deploy cz --check` | nothing; `absent / current / stale / foreign` per deployment |

`automation-export` and `automation-deploy` emit from a `git archive` copy of `HEAD`: the program resolver of ttrp
0.22.8 also scans the gitignored `.modeler/toolchains/ttrp` and refuses `TTRP-EXPORT-REF` in a working checkout. Commit
a recipe or world change before re-exporting.

`scripts/compose-processes.py` keeps every skeleton's run chain exactly as emitted and adds the authored layer, all of
it under ids that start with `s41_`:

- **release_order** (H-1, on placement): the message start `order_placed`; a guard that ends the instance when a
  confirmation for the order is already open (D-98 — a read, not a lock: two placements of one order at the same moment
  can still open two, S4.1 Found L); the confirmation task's due date (2 working days on the Prague clock: no weekend,
  no holiday of the world's rules in `data/calendar/calendar.sql`, counted from the engine's clock); on the lapse, a
  typed `perform hold {order, department: Sales}` (D-168).
- **release_morning** (H-1, the batch): a timer start, `0 0 5 * * ?` on the engine's UTC clock (06:00 CET); the
  batch's business key `release_morning:<date>`; the same guard, due date and lapse per row; one digest send task per
  `who` group after the close (`GET /runs/{id}/digest`, D-148) in place of the per-row mail.
- **return_request** (H-2, one instance per return line): the message start `return_requested` → the decide chain → the
  verdict's way. Rejections end. To customer care: a form task (`way`, group `hartland-care`, 3 working days) whose
  completion performs `decide_way {to, way}` by the person who completed it (D-171), then the way's instructions. The
  inbound and settlement loops wait for their message (`receipt_posted`, `settlement_posted`) or a daily timer, run their
  chain, and read the run's verdict (D-147).

Every send task is an external task on topic `TTR_CONN_MAIL`. The recipient comes from `TTR_MAIL_RECIPIENTS`, a
role → address map that each process sets from `processes/sets.json`.

## The driver — `automation-events.py`

Replays the planted timeline (`data/automation/events/<world>.csv`) as engine messages, as `hartland-driver`:

| timeline kind | message | effect |
|---|---|---|
| `order_placed` | `order_placed` | starts `release_order` (business key = order number) |
| `line_received` | `return_requested` | starts `return_request` (business key = line id) |
| `receipt_posted` | `receipt_posted` | wakes that line's inbound wait |
| `settlement_posted` | `settlement_posted` | wakes that line's settlement wait |

```
just automation-events cz 2026-11-02 --dry-run                    # print the day's messages
just automation-events-check cz 2026-11-02 --dry                   # the same, from `check`
HARTLAND_DRIVER_TOKEN=… just automation-events cz - --to 2026-11-02T00:00:00+01:00 --engine-url …   # pre-show
HARTLAND_DRIVER_TOKEN=… just automation-events cz 2026-11-02 --demo --speed 60 --engine-url …       # the live part
HARTLAND_DRIVER_TOKEN=… just automation-events-check cz 2026-11-02 --engine-url …                    # instances exist
```

- A start carries `ttrInput {key, at}`, where `at` is the event's time on the timeline (the run's clock). A wake
  carries `ttrEventAt`.
- `--approval-due PT2M` shortens a confirmation's due date. `--loop-period PT1M` replaces the return loops' daily
  timer. Both are for certification walks.
- The business rows behind every event are already in the database (`just automation-data` plants the whole
  timeline). `--db-url` only checks, read-only, that each key exists before its message goes.
- **Pre-show:** the demo day's receipts and settlements belong to lines that were requested on earlier days. Replay the
  timeline up to the demo day first (speed 0), so every in-flight line has its instance. A wake that no instance is
  waiting for prints `no waiting instance` and the run goes on; the daily timer picks the line up.
- Any other 4xx (401 for a bad bearer, for example) stops the run with exit 1. 5xx and transport errors are retried
  three times.

Specs: `just automation-events-test` (no cluster, no network). The process specs: `just processes-test` (needs
`npm ci --prefix processes/tests` and `just processes-tools` — the due-date specs run the composed Groovy on the
engine image's Groovy 5.0.4 with a JDK).
