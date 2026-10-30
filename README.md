# hartland

metadata — formerly `veles` (2026-06-13 → 2026-10), originally `ai-platform/infra/metadata`.

The **Hartland** demo world — the single home for everything about the Kantheon capabilities
demo (the `ai-models`-analog for the demo, D-7/BM-9). Kantheon is code; **all demo assets live
here**.

Two worlds, one model (BM-1/BM-2): **`hartland_us`** (English, USD) and **`hartland_cz`** (Czech,
CZK) — the same physical TPC-DS schema, the same seeded "DC-meltdown" story, served by **one**
TTR-M model over two connections.

## Layout

| Folder | What |
|---|---|
| `model/` | the TTR-M model — `db/` (physical), `er/` (logical + er2db), `md/` (ROLAP star + md2db), `lexicon/` (en+cs), `queries/` (`q.hartland.*`) |
| `agents/` | the agent def (Ariadne source) + both Golem Shems (`golem-hartland`, `golem-hartland-finance`) with `prompts/{en,cs}` |
| `data/` | the data build — `redate/`, `localize-cz/`, `catalog/`, `seed/`, `recon/` (produces the two versioned demo dumps) |
| `run-set/` | the `hartland-query` e2e run-set (both worlds) |
| `design/` | the design + planning docs (delta, plan, e2e re-plan) and `tasks/` (the per-stage task lists) |

## Where to start

`design/plan-demo-build.md` — the three-phase build plan. `design/08-czech-mirror-and-catalog-delta.md`
— the decisions (BM-1..BM-10). `design/test-fixture-hartland-replan.md` — hartland as the
ecosystem e2e fixture. Task lists: `design/tasks/`.

The olymp GitOps overlay `clusters/hartland` (in the **olymp** repo) deploys the showcase cluster
and reads this repo for the model (Ariadne source) + run-set.

## How a change reaches master

`master` is what hartland serves, so it takes a change only one way (ttr-demo#85): a branch, a pull
request, the **`model-gate`** check green on it, one approving review, the merge. The gate
(`.github/workflows/model-gate.yml`) checks out the ttr-core toolchain beside this repo at the ref
**`toolchain.lock`** pins — `[ttr-core].ref`, the toolchain the serving images were built against —
and runs every suite, the two drift checks (`generated/` matches the model) and, once that toolchain
ships the CLI, the Kotlin loader's strict load at the version metadata serves with
(`[veles].ttr-metadata`). The `[veles]` lock table and `just check-veles-pin` recipe retain their established names. Moving a pin is a change like any other: made in the PR that rolls the
readers, with `generated/` rebuilt by the new toolchain in the same commit.

The second workflow, **`regenerate`**, rebuilds `generated/` on a change's branch and pushes it as
the Studio's GitHub App — dispatched by the Studio's *Propose*, and run on any pull request that
touches the model (`generated/README.md` has the mechanics). Locally, `scripts/regenerate-local.sh`
is the same job. Planned and tracked in `project/platform/features/studio/` (SO-demo).

## OpenMetadata

The [catalog demo](design/demo-openmetadata.md) covers physical scans, the model
projection, CN concepts, the read-only `just verify-openmetadata` rig and Bora's
manual reset. Jobs are deployed by Olymp. The Studio browser round trip remains
pending the separate Studio deployment; the catalog URL is
<https://openmetadata.hartland.collite.cz>.
