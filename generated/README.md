# generated — committed build artifacts

metadata — formerly `veles` (2026-06-13 → 2026-10), originally `ai-platform/infra/metadata`.

`resolved-packages.json` — the deterministic `packages`/`entities`/`areas` snapshot from the
tatrman Modeler CLI (`just resolve-packages`), mirroring the `ai-models` repo's convention.
Regenerate after any `model/` change: `just resolve-packages`. `just check-model` verifies the
committed snapshot isn't stale; the model gate runs it on every pull request.

`lexicon.tar.zst` — the compiled lexicon archive (`kind: "lexicon"`, RV-P1.2's (a3) ruling) from
the tatrman **Kotlin** CLI (`just build-lexicon`). Carries the DECLARED layer (the root `lexicon/`
area + the `model/lexicon/*.ttrm` sugar), the METADATA layer harvested from the model's own labels,
and the shipped operator + grounding stdlib. Regenerate after any change to either surface *or* to
`model/`; `just check-lexicon` fails when the committed archive is stale.

Committed despite being compressed binary (~8 KB): the drift gate needs something to compare
against, and the reviewable part — the archive id and the per-class entry counts — is printed by
the build and recorded in `lexicon/README.md`. See that file for the full reasoning.

`model.tar.zst` — `model/` as a snapshot archive (`snapshot.json` + `docs/<path>`, ttr-snapshot's
format), the model the resolver's cn doors serve (CN-P6 S6.2). Written by `scripts/cn-model-snapshot.mjs`,
which `just build-lexicon` runs after the lexicon: the doors serve it only when its content id equals the
lexicon's `modelSnapshotHash`, so the two are built and shipped together. Freshness is judged on content, not
bytes (another zstd build packs other bytes; the reader does not care), so a rebuild leaves a current archive
untouched; `just check-lexicon` fails when it is stale or the lexicon pins another model.

`kustomization.yaml` — renders `lexicon.tar.zst` and `model.tar.zst` (and only them) into the `hartland-lexicon`
ConfigMap that the cluster's readers mount (RV-P3.3). olymp's `lexicon` Application applies this
directory at the same ref metadata serves the model from. Binary ⇒ kustomize emits `binaryData`;
measured 7,856 B → 10,626 B base64 → 11,325 B of manifest, 1.08% of the ~1 MiB ConfigMap cap.
Verify locally with `kustomize build generated/`.

## Who rebuilds, and with what

Only the toolchain **`toolchain.lock`** pins (`[ttr-core].ref`) — the one the gate checks against
and the serving readers were built for. Both files are a function of the model *and* the
toolchain, so an archive built with a newer ttr-core reads as stale to the gate, or worse, passes a
gate that was moved with it while nothing serving can read it (`model-gate.yml`'s pin comment has
both incidents). Locally: `../tatrman` checked out at the lock's ref and built, then
`scripts/regenerate-local.sh` (it refuses a `../tatrman` at another ref; exit 10 = rebuilt, commit
it; exit 0 = nothing stale), committed with the model change.

**The `regenerate` workflow** (`.github/workflows/regenerate.yml`, SO-demo P0) does the same on a
change's branch: the Studio's *Propose* dispatches it on `model/<user>/<n>`
(`POST /repos/Collite/ttr-demo/actions/workflows/regenerate.yml/dispatches {ref}`), and a pull
request touching `model/`, `automation/`, `lexicon/`, `modeler.toml` or `toolchain.lock` runs it
too. It runs `scripts/regenerate-local.sh` and, when `generated/` moved, commits it as the GitHub App
and pushes (`scripts/regenerate-push.sh` — if a save moved the branch during the build, it
regenerates on the new head rather than failing). The App token makes the push re-trigger
`pull_request: synchronize` (model-gate and this workflow on the new head) when the branch has an
open PR, which a `GITHUB_TOKEN` push would not. On Propose the push lands before the PR exists and
triggers nothing; the gate's first run is the PR's opening. The loop guard is idempotence: a re-run
finds nothing stale and pushes nothing. It never commits `model/**`. Until the App's secrets exist a
stale branch cannot be pushed: a dispatched run fails, a pull-request run warns.
