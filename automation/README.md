# automation — the automation agents' package

AU — automation agents: designed and planned in `collite-gh/project/kantheon/features/automation-agents/`
(`design/design.md`, `implementation/hartland/`). This folder is the package of `12` §6, read by the automation
service beside `../model/` (ttr-server contracts §1.1):

| path | what |
|---|---|
| `automation.ttrm` | `model automation`, package `hartland.automation`: the parameters, actions, roles and approvals (`17` §1) |
| `programs.ttrm` | the programs and the event schemas (`17` §1) |
| `worlds/demo.ttrm` | the world `hartland.worlds.demo`: engines, storages with `writable:`, and its automation half — the identity, executors, grants, deployments and the `return_line_flow` process (`17` §2) |
| `<recipe>/<recipe>.ttrp` | the recipes (P2: authored as `.ttrp`; from P3 derived from the literate `<recipe>.md` + its CZ twin) |
| `<recipe>/tests/*.yaml` | the golden cases (contracts §7; seeds until pinned from a debug run) |
| `tests/` | the package's suites (`just verify-model` runs them) |

**Why the world is here, not in `../model/`.** Its automation half names the programs and roles of this folder
and the toolchain's automation entities (`obligation`, …). veles and the lexicon build read `../model/` alone, and
would report every one of those names unresolved (the lexicon build refuses to load such a model). So nothing
under `../model/` names an automation object; `../model/` only carries the lifecycles (`states:`) the actions are
checked against.

Written in ttr-core grammar **0.16** (the CI pin, `.github/workflows/model-gate.yml`). The extension the recipes
run on is in `../model/` — the documents (`model/er/orders.ttrm`, `returns-flow.ttrm`, `proposals.ttrm`) and their
words (`model/lexicon/{en,cs}/automation.ttrm`); see the "Automation extension" paragraph of `../model/README.md`.

Recipe bundles use the independent `[ttrp]` pin in `../toolchain.lock`; the model gate remains on
`[ttr-core]` 0.16.1. From a clean checkout with JDK 21, Git, Python 3.11+ and `just`:

```sh
just toolchain-ttrp   # isolated .modeler/toolchains/ttrp checkout, then Gradle installDist
just check-recipes   # cheap checker pass for the six buildable business recipes
just build-recipes   # fresh manifest-v3 bundles beside their sources; refuses every diagnostic
just verify-model    # model/lexicon checks still need the model-gate toolchain beside the repo
```

`TTR_CORE_REPO` may point bootstrap at a local ttr-core clone; it still checks out the exact lock-file commit.
`TTRP_CLI` (or the recipes' positional `cli` argument) overrides the CLI for development. CI checks out the
model and recipe pins separately, stamps the recipe CLI with the locked version, builds the bundles, and fails
on any tracked or untracked change under `automation/`. Run `just build-recipes` and commit the result after a
recipe or golden seed changes. The bundles include the golden YAML seeds and their hashes in `recipe.tests`.
The literate documents and their drift check remain P3.

The recipe pin is temporarily ttr-core commit `f4001922bef0ab78f01db8343113bddbcdeac6c0`
(`0.17.3-au.1`), based on `grammar/v0.17.3`. The released tag emits retired CNC roles in verdict catalogs,
omits the golden-fixture list, and reports CEIL as unsupported. This commit fixes those handoff issues; replace
it with the next reviewed grammar release (ttr-core PR #249). Generated bundles remain the unmodified output of that toolchain.

Six bundles are served: `release_order`, `decide_return`, `monitor_inbound`, `settle`, `reorder_proposals`, and
`winback`. **Bundles load; they do not run until AU-server P1·S1.1.** The cross-storage pair contains door
`parts` and DuckDB combines, which that runner must read. The current P0 service has no run or scheduler loop.

The two ops recipes remain authored under `ops/` and their golden seeds remain tested, but their hourly
**deployments are omitted** until Server P4 serves the real `automation.ops` package. `no_run_since` also has a
named `TTRP-TYP-001` refusal for row-dependent `minutes(2 * period_minutes)` arithmetic. The stub is an authoring
fixture only and is not included in any bundle; remove all three stub files when the real package lands.

The ops stub lives at `../authoring-stubs/automation/ops/`, outside both roots read by the Server
(`model/` + `automation/`). Only the recipe toolchain loads this extra root through `modeler.toml`.
