# automation — the automation agents' package

AU — automation agents: designed and planned in `collite-gh/project/kantheon/features/automation-agents/`
(`design/design.md`, `implementation/hartland/`). This folder is the package of `12` §6, read by the automation
service beside `../model/` (ttr-server contracts §1.1):

| path | what |
|---|---|
| `automation.ttrm` | `model automation`, package `hartland.automation`: the parameters, actions, roles and approvals (`17` §1) |
| `programs.ttrm` | the programs and the event schemas (`17` §1) |
| `worlds/demo.ttrm` | the world `hartland.worlds.demo`: engines, storages with `writable:`, and its automation half — the identity, executors, grants, deployments and the `return_line_flow` process (`17` §2) |
| `release_order/release_order.md` | H-1 literate source |
| `handling-a-return-request.md` | H-2 source: Deciding → `decide_return`, Inbound → `monitor_inbound`, Outbound → `settle` |
| `reorder_proposals/reorder_proposals.md`, `winback/winback.md` | H-3/H-5 literate sources |
| `ops/no_run_since/no_run_since.md`, `ops/obligation_due_passed/obligation_due_passed.md` | deferred ops sources |
| `<source>.cs.md` | Czech twin of every English source (six documents, eight recipes); Czech prose approved by Bora on 2026-10-24 |
| `<recipe>/<recipe>.ttrp` | one canonical program per recipe, derived from either language with identical bytes |
| `<recipe>/<recipe>.ttrd`, `<recipe>/<recipe>.cs.ttrd` | native spans and document SHA for each language |
| `<recipe>/<recipe>/README.md` | generated explanation, in the current compiler's unnamed-document output layout; also included in the bundle |
| `<recipe>/README.md` | H-2 explanation beside each named recipe's canonical program and bundle |
| `<explanation-dir>/README.cs.md` | explanation rendered by `ttrp build --lang cs`; one per business recipe |
| `<recipe>/tests/*.yaml` | US and `.cz.yaml` golden cases with explicit world (contracts §7; seeds until pinned from a debug run) |
| `tests/` | the package's suites (`just verify-model` runs them) |

**Why the world is here, not in `../model/`.** Its automation half names the programs and roles of this folder
and the toolchain's automation entities (`obligation`, …). veles and the lexicon build read `../model/` alone, and
would report every one of those names unresolved (the lexicon build refuses to load such a model). So nothing
under `../model/` names an automation object; `../model/` only carries the lifecycles (`states:`) the actions are
checked against.

Recipe authoring uses grammar **0.18**, released compiler **0.18.14**; the TS/lexicon toolchain remains **0.18.3**. The strict serving-loader pin is **0.18.12** / metadata image **0.11.30**, adopted from current master in `toolchain.lock`. The extension the recipes
run on is in `../model/` — the documents (`model/er/orders.ttrm`, `returns-flow.ttrm`, `proposals.ttrm`) and their
words (`model/lexicon/{en,cs}/automation.ttrm`); see the "Automation extension" paragraph of `../model/README.md`.

Recipe bundles use the independent `[ttrp]` pin in `../toolchain.lock`; the model gate remains on
`[ttr-core]` (the reader pin). From a clean checkout with JDK 21, Git, Python 3.11+ and `just`:

```sh
just toolchain-ttrp   # isolated .modeler/toolchains/ttrp checkout, then Gradle installDist
just check-recipes   # cheap checker pass for the six buildable business recipes
just build-recipes   # derive all sources and check twins; build six business bundles; ops derive only
just check-literate-recipes # read-only Markdown/canonical/provenance/README check; exits 3 on drift
just verify-model    # model/lexicon checks still need the model-gate toolchain beside the repo
```

`TTR_CORE_REPO` may point bootstrap at a local ttr-core clone; it still checks out the exact lock-file commit.
`TTRP_CLI` (or the recipes' positional `cli` argument) overrides the CLI for development. CI checks out the
model and recipe pins separately, stamps the recipe CLI with the locked version, builds the bundles, and fails
on any tracked or untracked change under `automation/`. Run `just build-recipes` and commit the result after a
recipe or golden seed changes. The bundles include the golden YAML seeds and their hashes in `recipe.tests`.
CI checks literate artifacts before rebuilding. A prose-only source edit, canonical hand edit, missing sidecar or
changed explanation fails; rebuild the document and commit all derived artifacts together.

The recipe toolchain uses released **grammar/v0.18.14**, containing the accepted document/multi-recipe,
writer-default evidence, concat and declared-package resolution fixes. The separate `[automation-preview].server-ref` pins accepted
Server#320 merge **88c12a8b** for the preview CI job; it does not change a deployed image.
The model/reader pins remain independent. H-1's `release_order.md` is authoritative; its canonical
recipe preserves P2's code apart from whitespace/comments. The `.ttrd` records the actual source filename and
spans. The existing `document: "releasing-a-placed-order.md"` identifier is retained for compatibility with the
shared recipe fixture. The current unnamed-document compiler emits the standalone explanation under
`release_order/README.md` inside the recipe directory; keep that generated layout for native `build --check`.
H-2's `handling-a-return-request.md` is beside the three existing recipe folders, preserving their published
paths. All three programs equal P2 after removing whitespace/comments, including the conditional credit-note
and replacement expectations. Its sidecars point into the same source document and its explanations use the
document title. The visibility-policy sentence remains prose with a policy-only HTML comment.

The build discovers fenced recipe documents and existing sidecar owners; it builds each source once and
skips its derived programs. The read-only check also follows sidecars if a source's skeleton fence is removed.
It validates every recipe's outputs and diagnostics before publishing any canonical artifact or bundle.
Every source now has a Czech twin. Executable fences are copied verbatim; Czech parameter mentions use the
package's existing labels. The build compiles twins in temporary output directories with `--lang cs`, requires
byte-equal canonical code and equal `fingerprints.text`, and commits only Czech provenance and explanation
READMEs. There is one executable canonical program and one serving bundle per business recipe. The read-only
check compares both languages without modifying source files; missing/stale Czech artifacts fail with exit 3.
All outputs from both languages are validated before any committed artifact is replaced. Ops twins use the same
native extractor in derivation-only mode, so no compiled fingerprint or generated explanation is claimed for them.

All six bundle manifests hash their generated English READMEs and both worlds' seeds. H3 now preserves decimal
demand before division, rounds only the stored two-place demand and casts proposed quantity to int. Its model
key matches physical bigint; H5 mailing time matches physical timestamptz via datetime. The existing DDL is
unchanged. Explicit writer defaults map every required proposal/mailing attribute; H3/H5 now carry text/2
approval evidence for those declarations and targets. The other four recipes retain their approval text hashes. `uv run scripts/seed-goldens.py --world cz`
generates 27 business and four synthetic ops seeds for each world. The ops fixtures come from
`authoring-stubs/automation/ops/expected/`, use explicit `stub-<world>-…` keys, and are not observations of
served operational data. Replace those synthetic cases during Server P4 certification. Live runs, non-seed pins and
the H-2 replay fixture from those pins remain pending the AU-server runtime on **Hartland** (D-131).
Bora approved the six Czech source documents on **2026-10-24**. Neither world is runtime-certified by these seeds.
Seed generation and `--check` preserve existing pinned cases byte for byte. A malformed `pinned_from` or a pinned
case whose case/recipe/world identity disagrees with its path refuses before any seeds are written. After recording
real pins, rebuild the bundles so their golden files and manifest hashes include the observed evidence.

Six bundles are served: `release_order`, `decide_return`, `monitor_inbound`, `settle`, `reorder_proposals`, and
`winback`. **Bundles load; they do not run until AU-server P1·S1.1.** The cross-storage pair contains door
`parts` and DuckDB combines, which that runner must read. The current P0 service has no run or scheduler loop.

The two ops recipes derive from Markdown under `ops/` using native `ttrp build --derive-only` (also with
`--check`). This mode writes/checks canonical programs and provenance only, without compiling a bundle or an
explanation README; full compilation and generated ops explanations remain pending. Their seed goldens remain
tested, and their hourly
**deployments are omitted** until Server P4 serves the real `automation.ops` package. `no_run_since` also has a
named `TTRP-TYP-001` refusal for row-dependent `minutes(2 * period_minutes)` arithmetic. The stub is an authoring
fixture only and is not included in any bundle; remove all three stub files when the real package lands.

The ops stub lives at `../authoring-stubs/automation/ops/`, outside both roots read by the Server
(`model/` + `automation/`). Neither veles (`model/`) nor the automation Server (`model/` + `automation/`) loads it. The TTR-P toolchain and `resolve-packages` (`generated/resolved-packages.json`) load this extra root through `modeler.toml`.

Recipe build/check uses the actual checkout root; declared packages resolve independently of its basename.
Winback keeps documented workarounds for [#252](https://github.com/Collite/ttr-core/issues/252),
[#253](https://github.com/Collite/ttr-core/issues/253), and [#254](https://github.com/Collite/ttr-core/issues/254).
`RECIPES_REPRO_PASSES=2` enables a second local reproducibility pass; CI uses one test rebuild per recipe.


The `writer-preview` workflow and `just writer-preview /path/to/clean/server` run the Hartland-owned spec
against the exact accepted Server checkout named in the lock. The runner refuses a wrong commit or local
changes, verifies **services/automation runtimeClasspath** against the separate preview grammar pin
0.18.12 (translator/proto 0.12.11), and disables Maven Local. Query result tables are mocked; real bundle loading, approval coverage,
bindings, staging, native preview and writer assignment checks run. The CI checkout is deliberately named
`bundle` to guard package resolution independently of its path. JUnit XML retains all five named cases.

The gate covers H3's complete **writer projection**, including negative retry-stable bigint ID, run/state,
all required attributes and two-place stored demand. Full H3 must produce that same proposal plus the buyer
ask with deferred `start`/`purchasing`, `2 working_days`, warehouse grouping and would-text; replay is stable
and empty full H3 emits no actions or rows. These values are descriptive preview evidence. Callee resolution,
task creation/dispatch and calendar deadlines remain separate P3 work. Physical key conflicts must be refused
transactionally by P2; derived IDs are not globally collision-free. Full H5 tests both routes, UTC quarter/year boundaries, Prague/US edge
instants, pinned Open time, replayed rows and empty selection. H5's mailing key uses the UTC quarter of
as-of in both worlds; D-129's rolling 92-day exclusion stays independent of that label. No connector or
physical write runs in this gate. Actual deployed US/CZ runs, ops support and P3 exit remain pending.
