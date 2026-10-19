# hartland — local task runner (Phase 2, model verification).
#
# Borrows the sibling tatrman checkout's built toolchain (collite-gh/* convention: repos
# live side by side) rather than vendoring a node_modules of its own — this repo stays
# content-only (BM-9). Pass `cli=` to point at a different tatrman checkout.

# Run the Stage 2.x mocked unit-test suites (node's built-in test runner, no deps).
# find picks up every *.test.mjs under model/, agents/ and lexicon/ — new stages' test
# files are discovered automatically, no glob list to maintain here. (`lexicon/` joined at
# RV-P3.2: the root data area is a third authored surface, and its guards belong in the
# same command as the model's.)
verify-model:
    node --test $(find model agents lexicon automation -name '*.test.mjs')

# GX (NLS-P6.2) — check every mounted `intent.yaml` against the plan-composer placeholder
# contract. The kantheon sibling is `IntentPromptContractSpec`; this repo has no CI lane, and
# an uncontracted placeholder renders EMPTY with nothing anywhere saying so — which is exactly
# how five of six kantheon shem prompts were found serving a question-less prompt.
verify-prompts:
    python3 scripts/verify-intent-prompts.py

# Emit the deterministic resolved-packages.json artifact (packages, entities, areas) via
# the tatrman Modeler CLI — the same tool ai-models uses (`just resolve-packages`).
#
# ⛔ Both recipes resolve THROUGH A SYMLINK NAMED `hartland`, never through "$(pwd)". The CLI writes
# `generatedFrom` = the project directory's BASENAME and has no option to name it, so an artifact
# regenerated in a worktree (`hartland-ie`, `hartland-gx`, …) carried that worktree's name — master's
# did, for weeks — and every local check from the same worktree blessed it while a checkout called
# `hartland` (CI's) called it stale. Through the link the name is the repo's, whatever the checkout is
# called.
resolve-packages cli="node ../tatrman/packages/migrate/dist/cli.js":
    #!/usr/bin/env bash
    set -euo pipefail
    link="$(mktemp -d)"; trap 'rm -rf "$link"' EXIT
    ln -s "$(pwd)" "$link/hartland"
    {{cli}} resolve-packages "$link/hartland" --out "$(pwd)/generated/resolved-packages.json" --verbose

# Drift check: fail if the committed snapshot is stale.
check-model cli="node ../tatrman/packages/migrate/dist/cli.js":
    #!/usr/bin/env bash
    set -euo pipefail
    link="$(mktemp -d)"; trap 'rm -rf "$link"' EXIT
    ln -s "$(pwd)" "$link/hartland"
    {{cli}} resolve-packages "$link/hartland" --check --out "$(pwd)/generated/resolved-packages.json"

# ── lexicon (RV-P3.2) ─────────────────────────────────────────────────────────
# Compile the DECLARED (lexicon/ area + model/lexicon/*.ttrm sugar) and METADATA layers
# into the deterministic `kind: "lexicon"` archive. Kotlin, not Node — the compiler and
# the packer are Kotlin (RV-P1.2's (a3) ruling), so this pair does not share the `cli=`
# default with resolve-packages/check-model above. Same override shape, different binary.
#
# The archive IS committed to generated/, beside resolved-packages.json — same precedent,
# and `check-lexicon` is only a gate if there is something committed to check. Reasoning and
# the size measurement: lexicon/README.md.
build-lexicon cli="../tatrman/packages/kotlin/ttr-lexicon-cli/build/install/ttr-lexicon/bin/ttr-lexicon":
    {{cli}} build "$(pwd)" --out generated/lexicon.tar.zst --verbose

# Drift check: recompile in memory and compare the archive id against generated/. Exits 3
# when stale or absent, mirroring `check-model`. Only meaningful where the archive exists
# (a fresh clone has none) — CI runs `build-lexicon` first.
check-lexicon cli="../tatrman/packages/kotlin/ttr-lexicon-cli/build/install/ttr-lexicon/bin/ttr-lexicon":
    {{cli}} build "$(pwd)" --check --out generated/lexicon.tar.zst

# The kube context the cluster recipes below default to.
CTX := "hartland"

# ── the data extension (LR-P4, contracts C-8) ──────────────────────────────────
# Copy the template year (2024) forward so the world's facts reach <until> — a question about
# „minulý měsíc“ / "last month" then has data. Idempotent and incremental: run it again with a
# later date before a show and only the new weeks are added (data/extend/README.md).
#
#     just extend-data cz 2026-10-31          # the hartland cluster (CTX below)
#     just extend-data us 2026-10-31 dsk      # another cluster — positional, not `ctx=dsk`
#
# Every cluster carries the same olymp `hartland-pg` CNPG (ns `data`), so the pod is `hartland-pg-1`.
extend-data world until ctx=CTX:
    #!/usr/bin/env bash
    set -euo pipefail
    case "{{world}}" in us|cz) ;; *) echo "world must be us or cz, got '{{world}}'" >&2; exit 2 ;; esac
    case "{{ctx}}" in
      dsk|collite-o1|hartland) pod=hartland-pg-1 ;;
      *) echo "no hartland-pg pod known for context '{{ctx}}' (dsk, collite-o1, hartland)" >&2; exit 2 ;;
    esac
    data/extend/run-extend.sh "{{ctx}}" "hartland_{{world}}" "{{until}}" "$pod"

# Undo the extension of a world (data/extend/README.md "Reset"): every copied row goes, the originals
# and the recorded base ends stay. Then `just extend-data` copies every week again — the way to apply
# a changed extend.conf (order_offset, 2026-10-11) to a world already extended.
#
#     just extend-reset cz                    # the hartland cluster
extend-reset world ctx=CTX:
    #!/usr/bin/env bash
    set -euo pipefail
    case "{{world}}" in us|cz) ;; *) echo "world must be us or cz, got '{{world}}'" >&2; exit 2 ;; esac
    case "{{ctx}}" in
      dsk|collite-o1|hartland) pod=hartland-pg-1 ;;
      *) echo "no hartland-pg pod known for context '{{ctx}}' (dsk, collite-o1, hartland)" >&2; exit 2 ;;
    esac
    data/extend/run-reset.sh "{{ctx}}" "hartland_{{world}}" "$pod"

# ── the automation extension (AU-hartland P1, contracts §1, §5) ────────────────────────────────
# Build the H-1/H-2 ERP tables of a world from its facts, for one demo day (data/automation/README.md).
# Needs the extended year (`just extend-data` first). Guarded: the same day again is a no-op, another
# day is refused until `just automation-reset`. as-of `-` (or empty) = the Monday of the last extended week.
#
#     just automation-data cz                       # the hartland cluster, the default demo day
#     just automation-data us 2026-10-26 dsk        # another day and cluster — positional, not `ctx=dsk`
#     just automation-data us - dsk                 # the default day on another cluster
automation-data world as_of="-" ctx=CTX:
    #!/usr/bin/env bash
    set -euo pipefail
    case "{{world}}" in us|cz) ;; *) echo "world must be us or cz, got '{{world}}'" >&2; exit 2 ;; esac
    case "{{ctx}}" in
      dsk|collite-o1|hartland) pod=hartland-pg-1 ;;
      *) echo "no hartland-pg pod known for context '{{ctx}}' (dsk, collite-o1, hartland)" >&2; exit 2 ;;
    esac
    as_of="{{as_of}}"; [ "$as_of" = "-" ] && as_of=""
    data/automation/run-automation.sh "{{ctx}}" "hartland_{{world}}" "$as_of" "$pod"

# Undo the automation extension of a world: the base rows it changed come back from its journal, its
# tables go, the two added columns stay empty. Then `just automation-data` builds it again.
#
#     just automation-reset cz                      # the hartland cluster
automation-reset world ctx=CTX:
    #!/usr/bin/env bash
    set -euo pipefail
    case "{{world}}" in us|cz) ;; *) echo "world must be us or cz, got '{{world}}'" >&2; exit 2 ;; esac
    case "{{ctx}}" in
      dsk|collite-o1|hartland) pod=hartland-pg-1 ;;
      *) echo "no hartland-pg pod known for context '{{ctx}}' (dsk, collite-o1, hartland)" >&2; exit 2 ;;
    esac
    data/automation/run-reset.sh "{{ctx}}" "hartland_{{world}}" "$pod"

# R-A of a built world (data/automation/90-recon.sql) against its committed baseline
# data/automation/recon/R-A-<world>.md — exit 3 on drift, like check-model. After a deliberate change:
# `AUTOMATION_RECON_WRITE=1 just automation-recon <world> [ctx]` writes the new baseline.
automation-recon world ctx=CTX:
    #!/usr/bin/env bash
    set -euo pipefail
    case "{{world}}" in us|cz) ;; *) echo "world must be us or cz, got '{{world}}'" >&2; exit 2 ;; esac
    case "{{ctx}}" in
      dsk|collite-o1|hartland) pod=hartland-pg-1 ;;
      *) echo "no hartland-pg pod known for context '{{ctx}}' (dsk, collite-o1, hartland)" >&2; exit 2 ;;
    esac
    data/automation/run-recon.sh "{{ctx}}" "hartland_{{world}}" "{{world}}" "$pod"

# The demo day's event driver (contracts §6): replays data/automation/events/<world>.csv as webhooks to the
# Server's HTTP connector. `--dry-run` prints the bodies (no Server needed); `--demo` the runbook's subset.
#
#     just automation-events cz --dry-run --demo
#     just automation-events cz --url https://…/automation/webhooks/events --speed 60 --token-env AUTOMATION_EVENTS_TOKEN
automation-events world *FLAGS:
    uv run scripts/automation-events.py replay --world {{world}} {{FLAGS}}

# The timeline of a world, checked (no cluster): order, kinds, payload keys.
automation-events-check world:
    uv run scripts/automation-events.py check --world {{world}}

# The generator's suite on a throwaway local Postgres (pgserver via uv — no Docker, no cluster) loaded
# with data/automation/tests/fixture.sql. `ONLY=reset just automation-test` runs one script.
automation-test:
    bash data/automation/tests/run-all.sh

# The event driver's own specs (no cluster, no network).
automation-events-test:
    uv run --quiet --with pyyaml --with httpx python3 -B -m unittest scripts/test_automation_events.py

# ── the recipes (AU-hartland P2, contracts §4, §7, §10) ──────────────────────────────────────────────────────
# Seed the golden cases of the recipes from the generator's expected verdicts (data/automation/expected/<world>/):
# one case per route, no `pinned_from`. `--check` exits 3 when a committed seed is stale.
#
#     just seed-goldens            # the us world → automation/<recipe>/tests/<case>.yaml
#     just seed-goldens cz         # → <case>.cz.yaml (P3, with the CZ twins)
seed-goldens world="us" *FLAGS:
    uv run scripts/seed-goldens.py --world {{world}} {{FLAGS}}

# The recipes through the toolchain (contracts §10). Today — ttr-core grammar/v0.16.1 — `ttrp check` per recipe: the
# parse and the RecipeChecker (ttr-core P1), failing on any finding, a warning too (`ttrp build` refuses a recipe with
# TTRP-REC-099 until ttr-core P2; the literate `.md` sources and `--check` come at P3).
# automation/tests/recipes.test.mjs asserts what `ttrp explain` says: the skeleton and the mode verdicts.
build-recipes cli="../tatrman/packages/kotlin/ttrp-cli/build/install/ttrp-cli/bin/ttrp-cli":
    #!/usr/bin/env bash
    set -euo pipefail
    n=0
    while IFS= read -r f; do
      rc=0
      raw="$("{{cli}}" check "$f" 2>&1)" || rc=$?
      out="$(printf '%s\n' "$raw" | grep -v -e '^ANTLR ' -e '^SLF4J(' -e '^$' || true)"
      [ "$rc" -eq 0 ] && [ -z "$out" ] || { echo "$out" >&2; echo "build-recipes: $f does not check clean" >&2; exit 1; }
      n=$((n + 1))
    done < <(find automation -name '*.ttrp' -not -path '*/stub/*' | sort)
    echo "build-recipes: $n recipes check clean (ttrp check)"

# The golden cases' own specs: every case is a contracts §7 case naming only its recipe's routes; the seeds are fresh.
goldens-test:
    uv run --quiet --with pyyaml python3 -B -m unittest scripts/test_seed_goldens.py

# ── the routing corpus (LR P6, contracts C-9·3) ─────────────────────────────────────────────────
# run-set/routing/README.md. `check` needs no cluster; `run` asks every case of the DELIVERED world
# through the public iris-bff as the case's persona (HARTLAND_DEMO_PASSWORD, or the olymp realm file
# beside this checkout) and validates against the world DB as hartland_<world>_readonly.
#
#     just routing-run cz                          # the Czech world (the cluster must be on it)
#     just routing-run us --shadow --out /tmp/r    # + every FAST answer re-asked on the LLM lane
routing-check:
    uv run scripts/routing-run.py check

# The runner's own specs (assertions, verdicts, the schema check) — no cluster.
routing-test:
    uv run --quiet --with pyyaml --with httpx python3 -B -m unittest scripts/test_routing_run.py

routing-run world *FLAGS:
    uv run scripts/routing-run.py run --world {{world}} {{FLAGS}}
