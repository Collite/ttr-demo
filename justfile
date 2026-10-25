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

# XM-P3: read-only catalog acceptance after scan + two successful projection Jobs.
verify-openmetadata:
    bash scripts/verify-openmetadata.sh

# Offline regressions for pagination, retained links and honest no-op Job evidence.
openmetadata-test:
    python3 -m unittest scripts/test_verify_openmetadata.py

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
#
# Then generated/model.tar.zst — model/ as a snapshot archive, the model the resolver's cn doors serve (CN-P6 S6.2,
# scripts/cn-model-snapshot.mjs). The doors serve it only when its content id is this archive's `modelSnapshotHash`,
# so one recipe writes both.
build-lexicon cli="../tatrman/packages/kotlin/ttr-lexicon-cli/build/install/ttr-lexicon/bin/ttr-lexicon":
    {{cli}} build "$(pwd)" --out generated/lexicon.tar.zst --verbose
    node scripts/cn-model-snapshot.mjs

# Drift check: recompile in memory and compare the archive id against generated/. Exits 3
# when stale or absent, mirroring `check-model`. Only meaningful where the archive exists
# (a fresh clone has none) — CI runs `build-lexicon` first.
check-lexicon cli="../tatrman/packages/kotlin/ttr-lexicon-cli/build/install/ttr-lexicon/bin/ttr-lexicon":
    {{cli}} build "$(pwd)" --check --out generated/lexicon.tar.zst
    node scripts/cn-model-snapshot.mjs --check

# ── the conceptual model (CN-P6 S6.1) ─────────────────────────────────────────
# `ttr cn hygiene` (ttr-concept, Kotlin) over model/ PLUS the automation package: the parametric phases read its
# `def parameter`s (`:tolerance`, …), which live in automation/automation.ttrm — outside model/, by AU's rule — so a
# report over model/ alone calls each `cn/definition-unknown-name`. The report is the golden model/cn/tests/hygiene.md
# (`check-cn-hygiene` fails when it is stale; model/cn/tests/cn.test.mjs reads it). The tree is copied, not linked:
# the loader walks no symlink. The loader's `ttr/package-declaration-mismatch` on every file is hartland's layout (one
# flat `package hartland` in a kind-directory tree, BM-9) and changes nothing in the report; any other load error fails.
#
#     just cn-hygiene                     # print the report
#     just cn-hygiene > model/cn/tests/hygiene.md   # refresh the golden, then read the diff
cn-hygiene cli="../tatrman/packages/kotlin/ttr-concept/build/install/ttr/bin/ttr":
    #!/usr/bin/env bash
    set -euo pipefail
    world="$(mktemp -d)"; trap 'rm -rf "$world"' EXIT
    mkdir -p "$world/automation"
    cp -r model "$world/model"
    cp automation/automation.ttrm "$world/automation/"
    {{cli}} cn hygiene "$world" 2>"$world/stderr"
    if grep -v -e 'ttr/package-declaration-mismatch' -e '^SLF4J' "$world/stderr" >&2; then
      echo "cn-hygiene: the model has a load error beyond the layout's (above)" >&2
      exit 1
    fi

# Drift check: fail if model/cn/tests/hygiene.md is not what `cn-hygiene` prints now.
check-cn-hygiene cli="../tatrman/packages/kotlin/ttr-concept/build/install/ttr/bin/ttr":
    #!/usr/bin/env bash
    set -euo pipefail
    now="$(mktemp)"; trap 'rm -f "$now"' EXIT
    just cn-hygiene "{{cli}}" > "$now"
    if ! diff -u model/cn/tests/hygiene.md "$now"; then
      echo "check-cn-hygiene: model/cn/tests/hygiene.md is stale — just cn-hygiene > model/cn/tests/hygiene.md, and read the diff" >&2
      exit 3
    fi

# The Golem's own layouts (SO-demo P1·S1.1, VL V-44): model/layouts/agent/ rewritten from agents/*.yaml + the
# model — the cards each Golem's area closes over. Run it after an agent's or the model's cards change and commit
# the result; model/layouts/tests/layouts.test.mjs L5 fails while it is stale. `--check` writes nothing.
gen-layouts *FLAGS:
    node scripts/agent-layout.mjs {{FLAGS}}

# ── the Kotlin loader (SO-demo P0, ttr-core contracts §2.3, review-121 ⚑R121-A) ──────────────────
# Load the model as veles does — the Kotlin loader, strict — and print its diagnostics JSON on stdout.
# Non-zero when veles would drop a file it cannot parse or the loader finds a reconcile error (both
# only WARN at serve time, SO-1 memo [verify-4]), and when the CLI is not the ttr-metadata version
# toolchain.lock says veles serves with. The loader veles serves with, not the ref's toolchain: it is
# ../ttr-loader's, built by `just build-loader` (ttr-metadata-cli exists from ttr-core SO-core P0·S0.3).
load-model cli="../ttr-loader/packages/kotlin/ttr-metadata-cli/build/install/ttr-metadata/bin/ttr-metadata":
    #!/usr/bin/env bash
    set -euo pipefail
    pins="$(python3 scripts/toolchain-lock.py)"   # its own line, so a failed read stops the recipe
    while IFS='=' read -r key value; do export "$key=$value"; done <<<"$pins"
    {{cli}} load "$(pwd)" --strict --expect-version "$VELES_TTR_METADATA" --json

# Build the loader `load-model` runs — the loader veles serves with, not the ref's toolchain: ttr-metadata-cli from
# ttr-core at grammar/v<[veles].ttr-metadata>, stamped with that version as a release is (-Pversion; without it every
# module says 0.0.1-LOCAL and --expect-version fails). Needs ../ttr-loader at that tag; when it is not, prints the
# command that makes it so and exits 2 — it creates and checks out nothing itself.
build-loader:
    #!/usr/bin/env bash
    set -euo pipefail
    pins="$(python3 scripts/toolchain-lock.py)"
    while IFS='=' read -r key value; do export "$key=$value"; done <<<"$pins"
    tag="grammar/v$VELES_TTR_METADATA"
    have="$(git -C ../ttr-loader rev-parse HEAD 2>/dev/null || true)"
    want="$(git -C ../ttr-loader rev-parse --verify --quiet "$tag^{commit}" 2>/dev/null || true)"
    if [ -z "$have" ]; then
      echo "build-loader: no ../ttr-loader checkout. Make one at $tag (veles's ttr-metadata, toolchain.lock):" >&2
      echo "  git -C ../tatrman fetch --tags origin && git -C ../tatrman worktree add --detach ../ttr-loader $tag" >&2
      exit 2
    fi
    if [ "$have" != "$want" ]; then
      echo "build-loader: ../ttr-loader is at ${have:0:12}, not $tag (veles's ttr-metadata, toolchain.lock):" >&2
      echo "  git -C ../ttr-loader fetch --tags origin && git -C ../ttr-loader checkout --detach $tag" >&2
      exit 2
    fi
    cd ../ttr-loader
    ./gradlew --no-configuration-cache -Pversion="$VELES_TTR_METADATA" :packages:kotlin:ttr-metadata-cli:installDist

# The bump-time check of toolchain.lock's [veles] pins (review-121 R6) — for whoever moves them, not CI (olymp is
# private). The image olymp deploys on hartland (its origin/master) must be [veles].image, and ttr-server's
# gradle/libs.versions.toml at veles/v<image> must name [veles].ttr-metadata. Exit 1 on a mismatch, both values
# printed. Needs an authenticated `gh`; the olymp half is skipped when there is no olymp checkout.
#
#     just check-veles-pin                # olymp beside this checkout
#     just check-veles-pin ~/Dev/olymp    # elsewhere — positional, not `olymp=…`
check-veles-pin olymp="../olymp":
    #!/usr/bin/env bash
    set -euo pipefail
    pins="$(python3 scripts/toolchain-lock.py)"
    while IFS='=' read -r key value; do export "$key=$value"; done <<<"$pins"
    rc=0
    values=clusters/hartland/apps/veles/values.yaml
    if git -C "{{olymp}}" rev-parse --git-dir >/dev/null 2>&1; then
      git -C "{{olymp}}" fetch -q origin 2>/dev/null || echo "check-veles-pin: could not fetch {{olymp}} — reading its last-fetched origin/master" >&2
      deployed="$(git -C "{{olymp}}" show "origin/master:$values" \
        | awk '/^image:/{f=1;next} f&&/^[^ #]/{f=0} f&&/^ +tag:/{gsub(/["\047]/,"",$2); print $2; exit}')"
      if [ "$deployed" = "$VELES_IMAGE" ]; then
        echo "ok   olymp origin/master $values: veles $deployed = [veles].image"
      else
        echo "FAIL olymp origin/master $values: veles '$deployed' ≠ [veles].image '$VELES_IMAGE'" >&2; rc=1
      fi
    else
      echo "skipped: no olymp checkout at {{olymp}}"
    fi
    toml="$(gh api "repos/Collite/ttr-server/contents/gradle/libs.versions.toml?ref=veles/v$VELES_IMAGE" --jq .content | base64 -d)"
    built="$(printf '%s\n' "$toml" | sed -n 's/^tatrman-ttr-metadata *= *"\([^"]*\)".*/\1/p' | head -1)"
    if [ "$built" = "$VELES_TTR_METADATA" ]; then
      echo "ok   ttr-server veles/v$VELES_IMAGE: tatrman-ttr-metadata $built = [veles].ttr-metadata"
    else
      echo "FAIL ttr-server veles/v$VELES_IMAGE: tatrman-ttr-metadata '$built' ≠ [veles].ttr-metadata '$VELES_TTR_METADATA'" >&2; rc=1
    fi
    exit $rc

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

# ── the calendar (data/calendar/calendar.sql) ───────────────────────────────────────────────────
# Correct a world's date_dim from d_date: the quarters, the weekday, a Saturday-and-Sunday weekend and the
# world's public holidays. Idempotent. Refused while the automation extension is built (its working days
# come from these flags): reset it first, build it again after.
#
#     just automation-reset cz && just calendar-data cz && just automation-data cz
calendar-data world ctx=CTX:
    #!/usr/bin/env bash
    set -euo pipefail
    case "{{world}}" in us|cz) ;; *) echo "world must be us or cz, got '{{world}}'" >&2; exit 2 ;; esac
    case "{{ctx}}" in
      dsk|collite-o1|hartland) pod=hartland-pg-1 ;;
      *) echo "no hartland-pg pod known for context '{{ctx}}' (dsk, collite-o1, hartland)" >&2; exit 2 ;;
    esac
    data/calendar/run-calendar.sh "{{ctx}}" "hartland_{{world}}" "{{world}}" "$pod"

# The calendar's suite on a throwaway local Postgres (pgserver via uv — no Docker, no cluster).
calendar-test:
    bash data/calendar/tests/test-calendar.sh

# ── the label columns (data/labels/labels.sql, BI-4 · C-24) ──────────────────────────────────────
# CHAR(n) → VARCHAR(n), trimmed, for the columns labels are read from: a CHAR value reaches every client padded to n.
# Idempotent; one transaction; refused on tpc-ds-1g.
#
#     just labels-data cz && just labels-data us
labels-data world ctx=CTX:
    #!/usr/bin/env bash
    set -euo pipefail
    case "{{world}}" in us|cz) ;; *) echo "world must be us or cz, got '{{world}}'" >&2; exit 2 ;; esac
    case "{{ctx}}" in
      dsk|collite-o1|hartland) pod=hartland-pg-1 ;;
      *) echo "no hartland-pg pod known for context '{{ctx}}' (dsk, collite-o1, hartland)" >&2; exit 2 ;;
    esac
    data/labels/run-labels.sh "{{ctx}}" "hartland_{{world}}" "$pod"

# The label retype's suite on a throwaway local Postgres (pgserver via uv — no Docker, no cluster).
labels-test:
    bash data/labels/tests/test-labels.sh

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

# Recipe checks and bundles use [ttrp].ref, independently of the model gate's reader pin.
# Bootstrap once from a clean checkout (JDK 21); TTR_CORE_REPO can point at a local ttr-core clone.
toolchain-ttrp:
    bash scripts/toolchain-ttrp.sh

build-recipes cli="":
    python3 scripts/build-recipes.py {{ if cli == "" { "" } else { "--cli '" + cli + "'" } }}

# Cheap checker-only pass; it writes no bundles.
check-recipes cli="":
    python3 scripts/build-recipes.py --check {{ if cli == "" { "" } else { "--cli '" + cli + "'" } }}

# Compare Markdown, canonical recipes, provenance and explanation READMEs without writing.
check-literate-recipes:
    python3 scripts/build-recipes.py --literate-check

# Clean accepted Server checkout; toolchain.lock's test-only pin is independent of serving images.
writer-preview server="../tatrman-server":
    python3 scripts/writer-preview.py --server "{{server}}"

# CI runs this after build-recipes. Include untracked files: a new bundle must be committed too.
check-recipe-drift:
    #!/usr/bin/env bash
    set -euo pipefail
    if [ -n "$(git status --porcelain --untracked-files=all -- automation)" ]; then
      git status --short -- automation
      echo "Recipe bundles drifted: run just build-recipes and commit the result" >&2
      exit 1
    fi

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

# ── the one number (BI-4, contracts C-25) ────────────────────────────────────────────────────────
# run-set/bi-one-number/README.md. DC 5's stock-out weeks in 2025 through the Flight edge, the saved
# query and Iris, against the world DB; the Superset tile joins with S4.2. Personas as for routing-run.
#
#     just bi-one-number cz                        # the world the cluster serves (the Iris legs need it)
#     just bi-one-number cz --out /tmp/one         # + one-number-cz.json
bi-one-number world *FLAGS:
    uv run scripts/bi-one-number.py run --world {{world}} {{FLAGS}}

# The one-number runner's specs and the cases' schema — no cluster.
bi-one-number-test:
    uv run --quiet --with pyyaml --with httpx python3 -B -m unittest scripts/test_bi_one_number.py

# ── Hebe on hartland: the HB-P1 rig (HE-P1 · S1.2, design/hebe-demo/rig-hb/) ────────────────────
# Reads only. With HEBE_VERIFY_PASSWORD set it also signs in through the console's edge as marketa and maya.
#
#     just hebe-verify                                   # every check; exit 0 only when all PASS
hebe-verify:
    design/hebe-demo/rig-hb/verify.sh

# Markéta's routine fixtures (HE-P1 · S1.3, data/hebe/README.md): install or update all three, idempotent by name.
#
#     just hebe-routines                       # over a port-forward to svc/hebe
#     just hebe-routines --edge                # through the public console as marketa ($HEBE_VERIFY_PASSWORD)
#     just hebe-routines --fire monday-brief   # pre-show: install, then fire
hebe-routines *args:
    data/hebe/install-routines.sh {{args}}

# The rig's own specs (the Keycloak form parsing) — no cluster.
# Which chats has a Telegram bot seen (B-4.3)? Read-only; the token stays in the vault's 0600 copy, never argv.
hebe-telegram-chat-id secret="hebe-marketa-telegram-token":
    scripts/telegram-chat-id.sh {{secret}}

hebe-verify-test:
    python3 -B -m unittest design/hebe-demo/rig-hb/test_edge_login.py design/hebe-demo/rig-hb/test_verify_helpers.py design/hebe-demo/rig-hb/test_brief_check.py

# ── the Superset dashboards (BI-4, contracts C-23) ───────────────────────────────────────────────
# dashboards/README.md. Bundles per dashboard and world; olymp's superset-dashboards Application
# imports them on merge (the ConfigMap kustomization.yaml renders).
#
#     just dashboards-unpack export.zip dc-meltdown-stockouts cz   # an Admin's export → its bundle
#     just dashboards-kustomize                                      # then the ConfigMap's file list
#     just dashboards-check                                          # every rule, and no stale list
dashboards-check:
    uv run scripts/dashboards.py check

dashboards-kustomize:
    uv run scripts/dashboards.py kustomize

dashboards-unpack export id world:
    uv run scripts/dashboards.py unpack {{export}} {{id}} {{world}}

# The bundle rules' specs, and the shipped bundles against them — no cluster.
dashboards-test:
    uv run --quiet --with pyyaml python3 -B -m unittest scripts/test_dashboards.py

# ── Hebe's identity seeds (HE-P1 · S1.1, design/hebe-demo/runbook-identity.md) ───────────────────
# Bora runs these, logged into az; each never prints or argv's a secret.
#
#     just hebe-seed-client-secrets                  # B-2.1: hebe + hebe-console client secrets (idempotent)
#     just hebe-seed-offline-token marketa marketa   # B-3.1: prompts for the password; --rotate / --verify

# B-2.1: the hebe + hebe-console client secrets into the vault (idempotent).
hebe-seed-client-secrets:
    scripts/seed-hebe-client-secret.sh

# B-3.1: an instance's offline token (prompts for the user's password); --rotate replaces, --verify mints.
hebe-seed-offline-token instance user *FLAGS:
    scripts/seed-hebe-offline-token.sh {{instance}} {{user}} {{FLAGS}}

# The two seed scripts against a fake az + curl — no cluster, no Azure.
hebe-seed-test:
    python3 -B -m unittest scripts/test_seed_hebe_offline_token.py

# n8n identity bootstrap (design/n8n-demo/runbook-identity.md). No cluster writes in the tests.
# Before Mailpit is deployed: just n8n-seed-users --mailpit none (claims the owner only).
n8n-seed-users *FLAGS:
    scripts/seed-n8n-users.sh {{FLAGS}}

# Read-only P1 checks; --phase 2 adds vault-backed persona sign-ins and Mailpit checks.
n8n-verify *FLAGS:
    scripts/verify-n8n.sh {{FLAGS}}

# Restore demo content and publish its reviewed versions; --verify checks content and echoes the webhook.
n8n-seed-content *FLAGS:
    scripts/seed-n8n-content.sh {{FLAGS}}

# Seed + verification rig against local fakes; discovers the future content seed tests too.
n8n-test:
    python3 -B -m unittest discover -s scripts -p 'test_*n8n*.py'
