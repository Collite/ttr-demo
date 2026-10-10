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
#
# `check-investment-model` runs FIRST (IE-P2·S2.3·T3): `model/investment/` is written by
# `sync-investment-model` out of kantheon, so a hand-edit there is a change to a model whose source
# of truth is another repository. CI runs this recipe on every push and pull request
# (.github/workflows/model-gate.yml); the source-commit comparison it cannot make is
# `check-investment-model-source`, which needs a kantheon checkout and so runs locally.
verify-model:
    just check-investment-model
    node --test $(find model agents lexicon -name '*.test.mjs')

# The sync's own suite (IE-P2·S2.3·T2) — idempotency, the stamp, and the interpreted-face-only
# rule. Separate from `verify-model` for the same reason `verify-price-history` is: it drives
# `just` in a temp checkout and needs a kantheon beside this one (IE_KANTHEON_DIR overrides).
verify-investment-sync:
    node --test scripts/tests/sync-investment-model.test.mjs

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

# ── the simulated price history (IE-P1·S1.5·T0c, IE-C64) ──────────────────────
# ⚑IE-12, ruled by Bora 2026-09-07: *simulate it, with some evolution*. DistrInfo's `Prices` is
# CURRENT market data — one row per ISIN, no series — so IE-C30 values every PAST quarter with
# nothing to read. These two recipes generate the history and write it through the door.
#
# DEMO CONTENT, and it says so: every row is labelled `sourcePluginId: sim-prices` in the journal,
# and the runbook's "what is dummy" list names it (IE-P5·S5.1). The most recent point of every
# series is the provider's real number at its real date — only history is ours.
CTX := "hartland"
NS := "data"
PGPOD := "postgres-1"

# The real anchors: one `Prices` row per instrument the estate has ever held. See scripts/anchors.sql.
price-anchors:
    @kubectl --context {{CTX}} -n {{NS}} exec {{PGPOD}} -c postgres -- \
        psql -U postgres -d entry -tAc "$(cat scripts/anchors.sql)"

# Generate + (optionally) submit. DRY RUN by default; the argument is POSITIONAL:
#
#     just seed-price-history          # dry run — prints what it would write
#     just seed-price-history true     # writes
#
# ⚑ NOT `submit=true`. In just, `name=value` before the recipe sets a VARIABLE; after it, it is
# passed as the positional argument's literal text — so `just seed-price-history submit=true` runs
# a DRY RUN and says so, which is a quiet way to believe you have seeded an estate you have not.
# Needs a bearer for the substrate, which is on `jwks` — the door's service token carries the right
# audience and role (olymp apps/investment-door/README.md), and a port-forward to reach it:
#
#   kubectl --context hartland -n kantheon port-forward svc/entry-substrate 18080:8080 &
#   export ENTRY_BEARER=$(kubectl --context hartland -n kantheon get secret investment-door-entry-token \
#                          -o jsonpath='{.data.DOOR_ENTRY_TOKEN}' | base64 -d)
#   just seed-price-history submit=true
seed-price-history submit="false" from="":
    #!/usr/bin/env bash
    set -euo pipefail
    just price-anchors > /tmp/sim-price-anchors.json
    n=$(python3 -c "import json;print(len(json.load(open('/tmp/sim-price-anchors.json'))))")
    echo "anchors: $n instruments"
    node scripts/seed-price-history.mjs --anchors /tmp/sim-price-anchors.json \
        {{ if from != "" { "--from " + from } else { "" } }} \
        {{ if submit == "true" { "--submit" } else { "" } }}

# The T0c property tests (IE-C64's three, plus the two that make them meaningful). No DB, no network.
verify-price-history:
    node --test scripts/tests/price-history.test.mjs

# ── the interpreted investment model, synced from kantheon (IE-P2·S2.3, IE-C27) ───────────────
# Source of truth is `kantheon/packages/investment/model/` — one package, two faces (FO-12). Veles
# on hartland serves THIS repo's `model/` and nothing else, so the interpreted face is copied here
# and never hand-edited. `check-investment-model` is what makes "never hand-edited" checkable.
#
# ⛔ FOUR DIRECTORIES (and the one data file INVESTMENT_FILES names), AND NOT ONE MORE. kantheon's package also holds `model/book.ttrm`,
# `model/parties.ttrm`, `model/instruments.ttrm` (the entry face) and `model/entry/` (DDL + apply
# programs). Those three .ttrm files DO NOT PARSE — `model book` is not one of the grammar's model
# codes — and S2.1·D1 measured what a rejected file still costs: the parser recovers past the bad
# directive, keeps the `def entity` declarations underneath under a GUESSED `er` code, and
# `book.ttrm` sorts before `er/book.ttrm`, so `transaction` and `position` resolved to the wrong
# file. Alphabetical order decided which model a consumer was served. Whatever veles's own Kotlin
# loader does with a parse error, it is never handed one from here.
#
# ⛔ AND NO `tests/`. Each of the four directories has one in kantheon, importing a harness that is
# not synced — and `just verify-model` above runs `find model -name '*.test.mjs'`, so a copied test
# tree does not sit inertly, it turns this repo's own model gate red.
INVESTMENT_KINDS := "db er binding queries"
# IA-P4b·S4b.2: plain files the sync carries beside the kind directories. `income-labels.yaml` (IA-C55) is the
# classification table the report renders by — the fingerprint references classify the book with the SAME file
# (`scripts/lib/income_labels.py`), so it is synced from kantheon like the model, under the same stamp and tree hash,
# never hand-copied here. Not a TTR file: nothing that reads the model tree parses it.
INVESTMENT_FILES := "income-labels.yaml"
# IA-P4b review R15: kantheon files this repo keeps a COPY of outside model/investment/ — `<source under
# packages/investment/model>:<path here>`. The sync does not carry them (they are tests, not model), so
# `check-investment-model-source` compares each, byte for byte, against the commit the stamp names. The label case list is
# the contract the reference's SQL and scripts/lib/income_labels.py are held to, as the renderer is: a stale copy would keep
# this repo green while the renderer normalises differently.
INVESTMENT_COPIES := "tests/income-labels.cases.json:scripts/tests/fixtures/evolution/income-labels.cases.json"

sync-investment-model kantheon="../kantheon" allow_dirty="false":
    #!/usr/bin/env bash
    set -euo pipefail
    src="{{kantheon}}/packages/investment/model"
    [ -d "$src" ] || { echo "no investment package at $src" >&2; exit 2; }
    commit=$(git -C "{{kantheon}}" rev-parse HEAD)
    # ⛔ A STAMP THAT NAMES A COMMIT THE CONTENT IS NOT IS WORSE THAN NO STAMP. Caught on this
    # recipe's own first real run: kantheon's working tree carried the S2.3 query rewrites, so the
    # sync copied them and wrote the sha of the commit BEFORE them. `check-investment-model` would
    # then be green over a tree nobody can reproduce from the named commit — the drift check
    # confirming a lie. Refuse — before anything is written — unless the caller says out loud that
    # they mean it.
    dirty=$(git -C "{{kantheon}}" status --porcelain -- packages/investment/model)
    if [ -n "$dirty" ] && [ "{{allow_dirty}}" != "true" ]; then
        echo "kantheon's investment model has uncommitted changes; the stamp would name $commit and carry something else:" >&2
        echo "$dirty" | sed 's|^|  |' >&2
        echo "Commit them there first, or re-run with: just sync-investment-model {{kantheon}} true" >&2
        exit 2
    fi
    [ -n "$dirty" ] && commit="$commit+dirty"
    just --justfile "{{justfile()}}" --working-directory "$(pwd)" _investment-copy "$src" model/investment
    tree=$(just --justfile "{{justfile()}}" --working-directory "$(pwd)" _investment-tree-sha)
    printf 'source-repo: kantheon\nsource-path: packages/investment/model/{%s}\nsource-commit: %s\nsynced-at: %s\ntree-sha256: %s\n' \
        "$(echo {{INVESTMENT_KINDS}} {{INVESTMENT_FILES}} | tr ' ' ',')" "$commit" "$(date -u +%Y-%m-%d)" "$tree" > model/investment/SYNCED-FROM
    echo "synced $(find model/investment -type f ! -path model/investment/SYNCED-FROM | wc -l | tr -d ' ') files from kantheon $commit"

# The copy the sync makes, and the one `check-investment-model-source` rebuilds to compare against —
# one definition, so the comparison cannot drift from what the sync writes. `dest` is REPLACED, not
# merged into: afterwards it is EXACTLY the source's four directories minus every `tests/`, plus INVESTMENT_FILES (the note
# above). `rsync --delete` per kind directory could see neither a stray top-level file nor a
# receiver-side `tests/` (an excluded path is protected from deletion), so both survived a re-sync
# and were re-certified by the new stamp.
_investment-copy src dest:
    #!/usr/bin/env bash
    set -euo pipefail
    src="{{src}}"; dest="{{dest}}"
    for kind in {{INVESTMENT_KINDS}}; do
        [ -d "$src/$kind" ] || { echo "$src/$kind is missing — refusing a partial sync" >&2; exit 2; }
    done
    for file in {{INVESTMENT_FILES}}; do
        [ -f "$src/$file" ] && [ ! -L "$src/$file" ] || { echo "$src/$file is missing (or not a plain file) — refusing a partial sync" >&2; exit 2; }
    done
    # ⛔ Plain files and directories only, or nothing is written. A symlink is invisible to the tree
    # hash, and what it points at is decided by whoever reads it — so one is refused, not copied.
    odd=$(cd "$src" && find {{INVESTMENT_KINDS}} -name tests -prune -o ! -type f ! -type d -print)
    if [ -n "$odd" ]; then
        echo "refusing to sync entries that are not plain files (symlinks?) from $src:" >&2
        echo "$odd" | sed 's|^|  |' >&2
        exit 2
    fi
    mkdir -p "$(dirname "$dest")"
    stage=$(mktemp -d "$(dirname "$dest")/.investment-sync.XXXXXX")
    trap 'rm -rf "$stage"' EXIT
    chmod 755 "$stage"
    for kind in {{INVESTMENT_KINDS}}; do cp -R "$src/$kind" "$stage/$kind"; done
    for file in {{INVESTMENT_FILES}}; do cp "$src/$file" "$stage/$file"; done
    find "$stage" -type d -name tests -prune -exec rm -rf {} +
    rm -rf "$dest"
    mv "$stage" "$dest"
    trap - EXIT

# The tree hash the stamp records and `check-investment-model` recomputes. Content AND path, so a
# rename is a change. Only the TOP-LEVEL stamp is left out (the hash could never match what contains
# it); a file named SYNCED-FROM anywhere else is content like any other. And plain files only: an
# entry `find -type f` cannot see — a symlink — is refused, because a hash that skips it certifies
# whatever it points at.
_investment-tree-sha dir="model/investment":
    #!/usr/bin/env bash
    set -euo pipefail
    cd "{{dir}}"
    odd=$(find . ! -type f ! -type d)
    if [ -n "$odd" ]; then
        echo "{{dir}} holds entries that are not plain files — the tree hash cannot see them, and the sync never writes them:" >&2
        echo "$odd" | sed 's|^\./|  |' >&2
        exit 3
    fi
    find . -type f ! -path ./SYNCED-FROM -print0 | LC_ALL=C sort -z | xargs -0 shasum -a 256 | shasum -a 256 | cut -d' ' -f1

# Drift check: fail when `model/investment/` no longer matches its stamp. CI runs it on every push
# and pull request (.github/workflows/model-gate.yml), and `verify-model` runs it first locally.
# It proves the tree is what the stamp SAYS — not that the stamp is what kantheon holds; that is
# `check-investment-model-source`, below.
check-investment-model:
    #!/usr/bin/env bash
    set -euo pipefail
    stamp=model/investment/SYNCED-FROM
    [ -f "$stamp" ] || { echo "$stamp is missing — run \`just sync-investment-model <kantheon>\`" >&2; exit 3; }
    want=$(grep '^tree-sha256: ' "$stamp" | cut -d' ' -f2)
    have=$(just --justfile "{{justfile()}}" --working-directory "$(pwd)" _investment-tree-sha)
    if [ "$want" = "$have" ]; then
        echo "model/investment is in sync with $(grep '^source-commit: ' "$stamp" | cut -d' ' -f2)"
        exit 0
    fi
    echo "model/investment has drifted from its stamp (want $want, have $have)." >&2
    echo "The source of truth is kantheon; edit it THERE and re-sync. Files that differ:" >&2
    # Name the files, not just the tree — a bare hash mismatch tells an operator nothing about what
    # to put back. Re-sync into a scratch copy and diff against it.
    tmp=$(mktemp -d)
    trap 'rm -rf "$tmp"' EXIT
    src=$(grep '^source-commit: ' "$stamp" | cut -d' ' -f2)
    if [ -d "${IE_KANTHEON_DIR:-../kantheon}/packages/investment/model" ]; then
        mkdir -p "$tmp/model"
        just --justfile "{{justfile()}}" --working-directory "$tmp" sync-investment-model "$(cd "${IE_KANTHEON_DIR:-../kantheon}" && pwd)" >/dev/null
        diff -rq model/investment "$tmp/model/investment" 2>&1 | grep -v '^Files model/investment/SYNCED-FROM and ' | sed 's|^|  |' >&2 || true
    else
        (cd model/investment && find . -type f ! -path ./SYNCED-FROM | sed 's|^\./|  |') >&2
        echo "  (no kantheon checkout at ${IE_KANTHEON_DIR:-../kantheon} — listing the whole tree instead of the diff)" >&2
    fi
    echo "stamped source commit: $src" >&2
    exit 3

# The comparison `check-investment-model` cannot make. The stamp's hash proves the tree is what the
# stamp SAYS; it cannot prove the stamp is what kantheon holds — a hand-edit followed by a re-stamp
# passes it, and veles serves `master` straight from git. This rebuilds the tree from kantheon AT
# THE STAMPED COMMIT (`git archive`, so the checkout's branch and working tree do not matter) through
# the same `_investment-copy` the sync uses, and compares. LOCAL ONLY: it needs a kantheon checkout
# that has the commit, and CI has none — run it before merging a re-sync.
check-investment-model-source kantheon=env_var_or_default("IE_KANTHEON_DIR", "../kantheon"):
    #!/usr/bin/env bash
    set -euo pipefail
    stamp=model/investment/SYNCED-FROM
    [ -f "$stamp" ] || { echo "$stamp is missing — run \`just sync-investment-model <kantheon>\`" >&2; exit 3; }
    sha=$(grep '^source-commit: ' "$stamp" | cut -d' ' -f2)
    case "$sha" in
        *+dirty) echo "the stamp names a DIRTY source ($sha): no commit holds what was synced, so there is nothing to compare against. Re-sync from a clean kantheon." >&2; exit 3 ;;
    esac
    git -C "{{kantheon}}" cat-file -e "$sha^{commit}" 2>/dev/null \
        || { echo "the kantheon checkout at {{kantheon}} does not have $sha — fetch it there first" >&2; exit 2; }
    tmp=$(mktemp -d)
    trap 'rm -rf "$tmp"' EXIT
    paths=()
    for kind in {{INVESTMENT_KINDS}} {{INVESTMENT_FILES}}; do paths+=("packages/investment/model/$kind"); done
    git -C "{{kantheon}}" archive --format=tar "$sha" "${paths[@]}" | tar -x -C "$tmp"
    just --justfile "{{justfile()}}" --working-directory "$(pwd)" _investment-copy "$tmp/packages/investment/model" "$tmp/want"
    want=$(just --justfile "{{justfile()}}" --working-directory "$(pwd)" _investment-tree-sha "$tmp/want")
    have=$(just --justfile "{{justfile()}}" --working-directory "$(pwd)" _investment-tree-sha)
    rc=0
    if [ "$want" = "$have" ]; then
        echo "model/investment is exactly kantheon $sha"
    else
        echo "model/investment is NOT what kantheon $sha holds — the source of truth is kantheon; edit it THERE and re-sync. Files that differ:" >&2
        diff -rq "$tmp/want" model/investment 2>&1 | grep -v '^Only in model/investment: SYNCED-FROM$' \
            | sed "s|$tmp/want|kantheon@${sha:0:12}|g; s|^|  |" >&2 || true
        rc=3
    fi
    # the copies kept outside model/investment (R15): each byte-identical to the stamped commit's file
    for pair in {{INVESTMENT_COPIES}}; do
        src="packages/investment/model/${pair%%:*}"; dst="${pair#*:}"
        if ! git -C "{{kantheon}}" cat-file -e "$sha:$src" 2>/dev/null; then
            echo "$dst copies $src, which kantheon $sha does not have" >&2; rc=3; continue
        fi
        if [ ! -f "$dst" ]; then
            echo "$dst is missing — it is the copy of kantheon's $src (cp it from $sha)" >&2; rc=3; continue
        fi
        if git -C "{{kantheon}}" show "$sha:$src" | cmp -s - "$dst"; then
            echo "$dst is exactly kantheon $sha:$src"
        else
            echo "$dst is NOT kantheon $sha:$src — copy it from that commit (the stamp's)" >&2; rc=3
        fi
    done
    exit $rc

# ── IE-P2·S2.4 · the estate answers, and it answers DIFFERENTLY after a write ────────────────────
#
# The stage's DoD, and the one check that crosses the whole path a person crosses: bearer → BFF →
# query door → worker for the reads, and bearer → BFF → entry substrate → ledger for the writes,
# then back through the reads to see what changed. kantheon's conformance suite runs the programs'
# SOURCE text on psql and cannot see any of that — S2.3·D18 and D19 both lived only in the text the
# door EMITS, and no read suite can show that a correction moves money without moving units.
#
# ⛔ `full` WRITES, and a ledger is append-only: the drills leave three permanent rows behind. Name a
# THROWAWAY portfolio. There is no default, deliberately — a default here writes to the wrong book.
#
#   just investment-dod                                    # readonly, against IE_DOD_PORTFOLIO
#   IE_DOD_MODE=full just investment-dod                   # + the correction, addition and refusal drills
#   IE_DOD_MODE=full IE_DOD_HOLD_ONLY=1 just investment-dod
#                                                          # journal the correction and stop; it prints
#                                                          # the IE_DOD_MOVEMENT=… run for after the commit
#
# `IE_DOD_MODE` is exactly `readonly` or `full`; anything else is refused before a request is sent.
#
# ⚑ On an estate that caps answers, declare the cap: `IE_DOD_TOP_N=200` on hartland (IE-P3·S3.0 raised
# `VALIDATE_DEFAULT_TOP_N` from 100). A single read is then checked at `min(book, cap)` — and the ledger
# is ALSO read whole, in pages of `cap − 1` through §2.1's `offset`, and THAT count must equal the
# book's (IE-P3·S3.0·T7). Without the declaration the single-read check reads a capped answer as a
# disagreement between the door and the book, which is the honest default. Since the row window the
# estate SAYS when it caps (`top_n_applied`); the drill prints whether it did, because a silent cap
# means validate and query predate it (S2.4·D9).
investment-dod:
    ./scripts/investment-dod.sh

# The drill's own suite: the script against a stub BFF and a fake psql — no estate, no database. Each
# check the drill makes is shown to FAIL against a door that answers wrongly on purpose (a stale door,
# a replacement at the old amount, a price read at scale 0, a refusal that is not the ruled one).
verify-investment-dod:
    node --test scripts/tests/investment-dod.test.mjs

# IE-P3·S3.3·T1 — the report a client downloads, held against the book (IE-C35).
#
# It renders `investment-evolution:v1` through studio-bff exactly as the Reports tile does, reads the
# Summary sheet back out of the `.xlsx`, and compares it row by row with the REFERENCE query run on the
# book with psql. ⛔ The reference runs on psql and not through the door because ⚑IE-15 (a) ruled that
# program un-runnable there — a live walk re-confirmed the 404 on 2026-09-14 — and because it is the
# same statement kantheon's conformance suite holds to hand-computed answers.
#
#   IE_FP_BFF=… IE_FP_DSN=… IE_FP_PORTFOLIO=conseq:… just report-fingerprint
#   … just report-fingerprint --save          # prints the fingerprint; IE_FP_SAVE_DIR also writes it —
#                                             # ⛔ never inside this repo: it is public (S3.3·D8)
#
# The bearer is IE_FP_BEARER, or the `estate-drill` service account (IE_FP_OIDC_*) — see
# `scripts/lib/estate-token.sh` for why a copied token is not good enough.
report-fingerprint *ARGS:
    ./scripts/report-fingerprint.sh {{ARGS}}

# Its own suite: the script against a stub BFF, a canned psql and a workbook the suite writes itself.
# Every check is shown FAILING against a workbook that is wrong on purpose — a cent too far, a missing
# currency, a changed coverage word — and the two RULED differences (per-line rounding, an as_of on a
# quarter end) are asserted as accepted and refused respectively.
verify-report-fingerprint:
    node --test scripts/tests/report-fingerprint.test.mjs

# IA-P4·S4.2 — `investment-evolution:v2` held against the book (IA-C51): the workbook rendered through studio-bff as
# the Studio's Evolution tab downloads it, and the same period evolution computed ON THE BOOK by
# `scripts/sql/evolution-reference.sql` (plain PostgreSQL, average cost) — Periods and Summary, cell by cell.
#
#   IE_FP_BFF=… IE_FP_DSN=… IE_FP_PORTFOLIO=conseq:… just fingerprint-evolution [--save]
#   (IE_FP_FROM, IE_FP_AS_OF, IE_FP_GRAIN=month|quarter; the bearer as for report-fingerprint)
#   In the cluster: just drill-in-cluster fingerprint investment-evolution:v2
# The v2 evolution workbook held against the book, cell by cell.
fingerprint-evolution *ARGS:
    ./scripts/fingerprint-evolution.sh {{ARGS}}

# Its suite, with no estate: the renderer's OWN workbooks (fixtures/evolution/, kantheon over its hand fixture) against
# the reference's saved answers on that fixture — the local fingerprint — then every check failing on purpose.
# The evolution fingerprint's suite (no estate).
verify-evolution-fingerprint:
    node --test scripts/tests/evolution-fingerprint.test.mjs

# IA-P4·S4.3 — the five overview workbooks held against the book (IA-C51): each rendered through studio-bff as the
# Studio's download buttons render it, and its tables compared with the same figures computed ON THE BOOK by
# `scripts/sql/{statement,overview,price-sheet,sync-run-changes}-reference.sql` (the statement's Evolution sheet by
# `evolution-reference.sql`).
#
#   IE_FP_BFF=… IE_FP_DSN=… IE_FP_PORTFOLIO=conseq:… just fingerprint-overview portfolio-statement:v1
#   IE_FP_CLIENT=conseq:…  … client-overview:v1 · … distributor-overview:v1 · IE_FP_MONTHS=24 … price-sheet:v1
#   IE_FP_RUN=<a committed run> IE_FP_JOURNAL_DSN=<a journal reader> … sync-run-changes:v1
#   In the cluster: just drill-in-cluster fingerprint <template>
# An overview workbook held against the book.
fingerprint-overview template:
    ./scripts/fingerprint-overview.sh {{template}}

# Its suite, with no estate: the renderer's OWN workbooks (fixtures/overview/) against the references' saved answers on
# the hand fixture, the script end to end against a stub studio-bff — then every check failing on purpose.
# The overview fingerprints' suite (no estate).
verify-overview-fingerprint:
    node --test scripts/tests/overview-fingerprint.test.mjs

# The reference itself, RUN on PostgreSQL 16 against the hand fixture and held to the hand answers: a throwaway
# container (`evolution-ref-pg`, C locale as hartland's `entry`), left running for inspection —
# `just verify-evolution-reference-down` removes it. `--write` rewrites the saved answers the suite above reads.
# With REF_PG_DSN set (CI's `references` job: a postgres:16 service, C locale) both recipes use that server instead.
EVOLUTION_REF_PORT := "55436"

# The evolution reference on PostgreSQL 16, held to the hand answers [--write].
verify-evolution-reference *ARGS:
    #!/usr/bin/env bash
    set -euo pipefail
    write=0
    for a in {{ARGS}}; do
        case "$a" in --write) write=1 ;; *) echo "unknown argument '$a' (--write)" >&2; exit 2 ;; esac
    done
    if [ -n "${REF_PG_DSN:-}" ]; then
        # a PostgreSQL 16 someone else runs — CI's service container (model-gate `references`), C locale
        dsn="$REF_PG_DSN"
    else
        if ! docker inspect evolution-ref-pg >/dev/null 2>&1; then
            docker run -d --name evolution-ref-pg -e POSTGRES_PASSWORD=evolution -e POSTGRES_DB=entry \
                -e POSTGRES_INITDB_ARGS="--locale=C --encoding=UTF8" \
                -p 127.0.0.1:{{EVOLUTION_REF_PORT}}:5432 postgres:16 >/dev/null
        fi
        docker start evolution-ref-pg >/dev/null 2>&1 || true
        # readiness over TCP, the way the host psql connects (the init server listens on the socket only)
        for i in $(seq 1 60); do docker exec evolution-ref-pg pg_isready -q -h 127.0.0.1 -U postgres -d entry && break; sleep 1; done
        dsn="postgresql://postgres:evolution@127.0.0.1:{{EVOLUTION_REF_PORT}}/entry"
    fi
    EVOLUTION_REF_DSN="$dsn" EVOLUTION_REF_WRITE="$write" node --test scripts/tests/evolution-reference.test.mjs

# Remove the reference's PostgreSQL container.
verify-evolution-reference-down:
    docker rm -f evolution-ref-pg >/dev/null 2>&1 || true

# IA-P4·S4.3·T6 — the four overview references (statement · client/distributor · price sheet · run changes) on the SAME
# PostgreSQL 16 container, held to answers computed from the hand fixture [--write rewrites fixtures/overview/reference-*].
# The overview references on PostgreSQL 16, held to answers from the hand fixture [--write].
verify-overview-reference *ARGS:
    #!/usr/bin/env bash
    set -euo pipefail
    write=0
    for a in {{ARGS}}; do
        case "$a" in --write) write=1 ;; *) echo "unknown argument '$a' (--write)" >&2; exit 2 ;; esac
    done
    if [ -n "${REF_PG_DSN:-}" ]; then
        dsn="$REF_PG_DSN"   # CI's service container, as above
    else
        if ! docker inspect evolution-ref-pg >/dev/null 2>&1; then
            docker run -d --name evolution-ref-pg -e POSTGRES_PASSWORD=evolution -e POSTGRES_DB=entry \
                -e POSTGRES_INITDB_ARGS="--locale=C --encoding=UTF8" \
                -p 127.0.0.1:{{EVOLUTION_REF_PORT}}:5432 postgres:16 >/dev/null
        fi
        docker start evolution-ref-pg >/dev/null 2>&1 || true
        for i in $(seq 1 60); do docker exec evolution-ref-pg pg_isready -q -h 127.0.0.1 -U postgres -d entry && break; sleep 1; done
        dsn="postgresql://postgres:evolution@127.0.0.1:{{EVOLUTION_REF_PORT}}/entry"
    fi
    OVERVIEW_REF_DSN="$dsn" OVERVIEW_REF_WRITE="$write" node --test scripts/tests/overview-reference.test.mjs

# IE-P3·S3.3 — run a drill FROM INSIDE the cluster: no port-forward (this estate's drop mid-run, which
# is how S3.0·T7 failed twice), and no copied bearer (the Job mints its own from `estate-drill`).
#
#   just drill-in-cluster dod            # the read drill, against conseq:200791223
#   just drill-in-cluster fingerprint    # render the report and hold it against the book
#   just drill-in-cluster fingerprint --save   # …and lift it into the PRIVATE project repo (S3.3·D8)
drill-in-cluster drill *ARGS:
    ./scripts/drill-in-cluster.sh {{drill}} {{ARGS}}
