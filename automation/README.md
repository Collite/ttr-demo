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
