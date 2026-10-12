# Hartland Golem demo — the rehearsal protocol (LR P6 S3, gate G6)

> The ladder that turns the demo script into a recorded run, in **cs over `hartland_cz`** and **en
> over `hartland_us`**. Companions: `demo-ops-manual.md` (how to run the cluster: §7.3 pre-show, §7.6
> the world flip), `demo-quirks.md` (the gotchas), `run-set/routing/` (the routing corpus — the
> machine half of R0). The script itself is a local working file (`design/demo-golem-261007.md`);
> it is not committed.

The acceptance (contracts C-9·3, both worlds): every scripted `FAST` question runs `ROUTE_FAST_PATH`
with 0 LLM calls; every `LLM` question runs `ROUTE_LLM_COMPOSE` with a named fall-through reason; the
two-persona act shows 5 rows vs 1 row + the rights sentence (C-6·1), and another DC for the DC manager
shows C-6·2; the protocol's SQL section shows the injected predicate.

## The ladder — each rung green before the next

| rung | what | who | green when |
|---|---|---|---|
| **R0** | the routing corpus on **both** worlds | operator (Claude Code can run it) | `just routing-run cz` on the CZ world, then `just world us` → `just world-smoke us` → `just routing-run us`, then back. No `FAIL` / `ERROR`. Every `XFAIL` names a filed issue and is either fixed or cut from the script |
| **R1** | **cs dry run** in Iris — Markéta, then Petr for Act 6 | presenter | every step answered with the protocol panel open; route, reason, LLM calls and seconds recorded into the script (§ "Recording" below) |
| **R2** | **en dry run** in Iris — Maya, then Sam | presenter | the same, on the US world |
| **R3** | the **two-persona act** in both worlds, and the forged-token drill again | presenter + operator | 6.1: 5 rows (analyst) vs 1 row + C-6·1 (DC manager); 6.2: C-6·2; the protocol's Security section lists the rule and the SQL carries `warehouse_sk = 5`; `just drill-forged-token` (olymp, `DRILL_PASSWORD` set) PASS |

A rung that fails stops the ladder. The fix goes in, then the ladder restarts at R0: the corpus is
cheap, and the same fix can move a route anywhere in the script.

## Three rules

1. **0 rows is never data** (`demo-quirks.md` §0). An empty answer, a bare 0 or „žádná data“ is
   believed only after the protocol's SQL has been read and, for a FAST answer, the corpus's
   validation has the same figure. A failed query used to come back as 0 rows; it now says
   „Dotaz se nepodařilo spustit.“, but the rule stays.
2. **The route is part of the answer.** A right number on the wrong lane is a finding: a scripted
   FAST question answered by the LLM costs 10–40 s on stage and can vary from run to run, and an LLM
   question answered by the door may have dropped something (the `UNHONOURED_*` reasons exist
   because it used to). Record the route of every step, not only the figure.
3. **Check the images before the config** (`demo-quirks.md` §5.4b). Before R1 and before the show:

   ```sh
   kubectl --context hartland get deploy -A \
     -o jsonpath='{range .items[*]}{.metadata.namespace}/{.metadata.name}{"\t"}{.spec.template.spec.containers[*].image}{"\n"}{end}' \
     | grep -E 'golem|iris|resolver|fuzzy|nlp|query|validate|translate|dispatch|veles|postgres|chrono'
   ```

   Every image is `ghcr.io/collite/<module>:<version>` and matches its olymp pin
   (`clusters/hartland/golems/_values.yaml` for the golems, `apps/<app>/values.yaml` for the rest).
   A `boraperusic/*` repository or a `:testing` tag on the demo path stops the rehearsal. After any
   image bump, the restart order of `demo-ops-manual.md` §7.2 / §7.2b (veles refresh → golems;
   lexicon → fuzzy + resolver + golems).

## Recording

The script's route column is replaced, step by step, by what was **recorded**, with the date and the
world — never by what the code is expected to do. One line per step and locale:

```
1.1 cs 2026-10-12 FAST · 0 LLM · 1.2 s · 12 rows · Aug 1 611 mil. Kč ✓
1.1 en 2026-10-12 LLM (MULTI_PERIOD) · 1 · 10.1 s · 12 rows — ttr-server#152
```

A deviation from the script's expected route, or a figure that does not match the recon, gets an
issue (kantheon for golem and Iris, ttr-server for the resolver, chrono, validate and the translator,
ttr-demo for the model and the lexicon) and its id goes into the script beside the step. The corpus
case gets an `xfail` with the same id, so R0 stays meaningful while the fix is open.

## Before every show (from `demo-ops-manual.md` §7.3)

1. `just extend-data cz <end of this month>` and `just extend-data us <end of this month>` (ttr-demo);
   refresh the R1 figures in the script (`data/recon/R1.md`, "Refreshing R1").
2. `just world <cz|us>` + merge + `just world-smoke <cz|us>` (olymp).
3. The stale-image check (rule 3).
4. `just routing-run <world>` — R0 for the delivered world, the morning of the show.
5. **Restart query-mcp after R0** (`kubectl --context hartland -n ttr-server rollout restart deploy/query-mcp`):
   until kantheon#187 / ttr-server#201 are fixed, every golem query leaves an MCP session behind and each
   later query is ~40 ms slower per session — a 72-case corpus run adds ~3 s to every FAST answer.
6. Warm the cluster with one throwaway turn per persona.
