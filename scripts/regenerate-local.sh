#!/usr/bin/env bash
# The regenerate job (SO-demo P0·S0.2, contracts §1, D-21) on any checkout. regenerate.yml runs this script as-is, so
# a local run IS the workflow's dry run, minus the commit and the push.
#
#   scripts/regenerate-local.sh [<checkout>]          # default: the checkout this script is in
#
# Rebuilds generated/ (resolved-packages.json + lexicon.tar.zst + model.tar.zst) and the Golem's layouts
# (model/layouts/agent/, `just gen-layouts`) with the toolchain toolchain.lock pins, then:
#   exit 0   nothing stale: both already matched, nothing changed. The loop guard: the workflow pushes nothing,
#            so its own push → pull_request → run chain stops after one bot commit.
#   exit 10  stale: rebuilt and left in the tree for the caller to commit
#   exit 1   the build failed, or it changed something else under model/ (the job never commits authored model/**)
#   exit 2   the toolchain at <checkout>/../tatrman is not at toolchain.lock's [ttr-core].ref
#
# model/layouts/agent/ is the one folder under model/ the job writes: nobody authors it — scripts/agent-layout.mjs owns
# it, from agents/ and the model's area closure — so a new entity in the agent's area makes it stale exactly as it
# makes the lexicon stale, and the Studio cannot write it (SO-demo P1·S1.2, Bora's ruling 2026-10-28).
#
# The toolchain is the justfile's side-by-side `../tatrman`, built. RESOLVE_CLI / LEXICON_CLI / LAYOUTS_CLI override
# the three builds (the recipes' `cli=`, and the gen-layouts command); with all three set the ref check is skipped —
# that is the tests' stubs, not a way to build generated/ with another toolchain.
set -euo pipefail

checkout="$(cd "${1:-$(dirname "$0")/..}" && pwd)"
cd "$checkout"

pins="$(python3 scripts/toolchain-lock.py)"   # its own line, so a failed read stops the script
while IFS='=' read -r key value; do export "$key=$value"; done <<<"$pins"
echo "toolchain.lock: ttr-core $TTR_CORE_REF · metadata ttr-metadata $VELES_TTR_METADATA"

if [ -n "${RESOLVE_CLI:-}" ] && [ -n "${LEXICON_CLI:-}" ] && [ -n "${LAYOUTS_CLI:-}" ]; then
  echo "regenerate: CLI overrides set — the toolchain's ref is not checked"
else
  toolchain="$checkout/../tatrman"
  have="$(git -C "$toolchain" rev-parse HEAD 2>/dev/null || true)"
  want="$(git -C "$toolchain" rev-parse --verify --quiet "$TTR_CORE_REF^{commit}" 2>/dev/null || true)"
  if [ -z "$have" ] || [ "$have" != "$want" ]; then
    echo "regenerate: $toolchain is at '${have:0:12}', toolchain.lock pins $TTR_CORE_REF${want:+ (${want:0:12})} — check that out and build it first" >&2
    exit 2
  fi
fi

# Content, not `git status`: a file already modified before the build and modified again by it reads the same there.
# The Golem's layouts are left out: they are the build's to write.
agent_layouts=model/layouts/agent
model_hash() { find model -type f -not -path "$agent_layouts/*" -print0 | sort -z | xargs -0 sha256sum | sha256sum; }
model_before="$(model_hash)"

${LAYOUTS_CLI:-node scripts/agent-layout.mjs} || { echo "regenerate: gen-layouts failed" >&2; exit 1; }

just resolve-packages ${RESOLVE_CLI:+"$RESOLVE_CLI"} || { echo "regenerate: resolve-packages failed" >&2; exit 1; }
just build-lexicon ${LEXICON_CLI:+"$LEXICON_CLI"} || { echo "regenerate: build-lexicon failed" >&2; exit 1; }

if [ "$(model_hash)" != "$model_before" ]; then
  echo "regenerate: the build changed files under model/ outside $agent_layouts/ — refusing (the job never commits authored model/**):" >&2
  git status --porcelain -- model ":!$agent_layouts" >&2
  exit 1
fi

stale="$(git status --porcelain -- generated "$agent_layouts")"
if [ -z "$stale" ]; then
  echo "regenerate: nothing stale — generated/ and $agent_layouts/ match the model"
  exit 0
fi
echo "$stale"
echo "regenerate: stale — rebuilt, left in the tree to commit"
exit 10
