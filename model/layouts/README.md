# model/layouts — the served layouts

A layout is one named picture of a schema: the cards it shows and, optionally, where they sit. Veles serves every
`.ttrg` under `model/` as a layout (`/model/layouts`, `/model/layout?name=`); the Studio's Model page and the Viewer
list them under **Schemas** as `er · <name>`. The format is ttr-core's *Layout files* page
(<https://docs.tatrman.org/model/layout-files/>).

| file | layout | made by |
|---|---|---|
| `sales.ttrg` | `sales` — the four sales facts, the dimensions they all share above them, the channel-specific ones below | hand |
| `agent/agent_hartland.ttrg` · `agent/agent_hartland_db.ttrg` | the Golem's own, er and db — every card its area closes over | `just gen-layouts` |

- **`.ttrg`, not `.yaml`.** Veles reads only the TTR form (a `.ttrg`, plus an optional `.ttrl` sidecar). The YAML form
  is what the Viewer's *Save as…* offers by default; save as **TTR** for a file that goes here.
- **Write what a layout writer writes:** refs as full qnames (`hartland.er.entity.item`, `hartland.db.dbo.item`),
  sorted alphabetically, integer positions, the graph named after the file. `tests/layouts.test.mjs` reads every file
  with the toolchain's own reader and writer and fails on anything else, and on two cards that overlap.
- **To arrange one:** open it in the Model page or the Viewer, drag the cards, *Save as…* TTR, replace the file.
- **`agent/` is generated** from `agents/*.yaml` and the model by `scripts/agent-layout.mjs`. Edit the agent, run
  `just gen-layouts`, commit the result; the suite fails while it is stale.

Designed in `project/platform/features/studio/` (the Studio offering, ttr-demo contracts §6) and
`project/tatrman/features/viewer-layouts/` (the layout format).
