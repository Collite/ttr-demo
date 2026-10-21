# generated — committed build artifacts

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

`kustomization.yaml` — renders `lexicon.tar.zst` (and only it) into the `hartland-lexicon`
ConfigMap that the cluster's readers mount (RV-P3.3). olymp's `lexicon` Application applies this
directory at the same ref veles serves the model from. Binary ⇒ kustomize emits `binaryData`;
measured 7,856 B → 10,626 B base64 → 11,325 B of manifest, 1.08% of the ~1 MiB ConfigMap cap.
Verify locally with `kustomize build generated/`.

## Who rebuilds, and with what

Only the toolchain **`toolchain.lock`** pins (`[ttr-core].ref`) — the one the gate checks against
and the serving readers were built for. Both files are a function of the model *and* the
toolchain, so an archive built with a newer ttr-core reads as stale to the gate, or worse, passes a
gate that was moved with it while nothing serving can read it (`model-gate.yml`'s pin comment has
both incidents). Locally: `../tatrman` checked out at the lock's ref and built, then
`just resolve-packages && just build-lexicon`, committed with the model change.
