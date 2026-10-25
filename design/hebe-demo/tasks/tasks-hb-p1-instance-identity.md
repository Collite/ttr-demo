# HB-P1 — Instance & identity

> **Met by HE-P1 (2026-10-25); these boxes stay as written.** The HE arc ran this phase, for the instance `marketa`
> (HE-D-4), not `dev`. Its tasks and evidence are in `project/kantheon/features/hebe/tasks/tasks-p1-*.md`, and
> `rig-hb/verify.sh` passes 12 checks (0 fail). See [`00-task-management.md`](./00-task-management.md).

> Target = contracts §2 table. Pre-flight: P0 probes done; **⚑1/⚑2 verdicts** (defaults:
> keep `dev`, HTTPRoute); **⚑3 delivered** (bot token in the vault). All changes via olymp
> PRs / the §4.4 provisioning runbook; freeze-calendar checked (task-mgmt rule 7). TDD =
> every task starts by adding its failing check to `rig-hb/verify.sh`.

- [ ] **T1 — `rig-hb/verify.sh` skeleton.** One script, one check per row of contracts §2,
  each currently RED where P0 found gaps: pod health · doctor clean · OBO mint as maya ·
  telegram round-trip · console login · registry heartbeat · unmapped-chat rejection ·
  receipts chain verify. Runs from the presenter machine (port-forwards in one shell call
  each — quirks §5.2 discipline).
- [ ] **T2 — Provisioning gap closed.** Per P0.T1 verdict: run/re-run `just hebe-provision
  dev` (runbook §4.4) to completion — PG schema+role+Flyway, Keycloak client, secret
  skeleton. Pod reaches Healthy. (If ⚑1 = new `maya` instance instead: this task becomes
  the full instance bring-up — appset entry + values + provision — budget accordingly.)
- [ ] **T3 — Bound user = maya.** Keycloak client + bound-user config point at the `maya`
  realm user (the same one from the Kantheon demo — realm-as-code file untouched; the
  binding lives in hebe's secret/config, NOT in the realm JSON). Verify: OBO mint yields a
  token whose subject/claims = maya; a delegation turn lands in **Maya's** Iris history.
- [ ] **T4 — Telegram channel live.** Token (⚑3) into the vault → `hebe-dev` secret;
  `[channels.telegram]` per P0.T6 into values `extraToml` (olymp PR; remember: extraToml
  appends, but any `extraEnv` edits REPLACE — quirks §4.2). Bot answers a "ping" from the
  mapped account.
- [ ] **T5 — chat_user_map = exactly one row** (presenter's chat-id → maya). Verify both
  directions: mapped chat works; a second account's message is rejected/dropped (record
  the exact behavior for Beat 6 — contracts §5).
- [ ] **T6 — Console exposure per ⚑2.** Default: olymp HTTPRoute
  `hebe.20-218-224-115.nip.io` → `svc/hebe:8765` (pattern: the iris/landing routes;
  wildcard cert already covers the host). Console auth per P0.T3 mode; credentials in the
  vault; login verified through the gateway with TLS trusted (ops-manual §2). If
  port-forward was ruled: script it into `rig-hb/console.sh` + pre-show.
- [ ] **T7 — Gateway & cost line.** Verify hebe's LLM calls transit llm-gateway with
  `X-Cost-Center: hebe/dev` (gateway logs/governance view) — the Beat-6 cost line must be
  *shown or dropped*, not claimed blind. Record where to show it (screenshot for the beat
  sheet).
- [ ] **T8 — Green sweep.** `rig-hb/verify.sh` all-green; update contracts §2 "probed →
  target met" per row; olymp PRs merged; check boxes.

## Verify block

```sh
rig-hb/verify.sh          # every check PASS
# doctor clean · OBO=maya · telegram both ways · console via route · registry heartbeat
```
