#!/usr/bin/env bash
# The show's byte-compare (SO-demo P2·S2.1, contracts §5, SD-D4): does the change Maya authored live in the Studio
# say exactly what the pre-authored branch says?
#
#   scripts/demo-compare.sh <live-branch>              # e.g. the live PR's head, after its regenerate commit
#
# Compares model/**, modeler.toml and generated/** of <live-branch> against demo/returns-review, both fetched from
# origin (DEMO_COMPARE_REF / DEMO_COMPARE_REMOTE override them). What it normalises, and nothing else:
#   generated/*.tar.zst      unpacked and compared member by member, with snapshot.json's resolvedFrom ids blanked —
#                            the archive's bytes depend on the zstd build that packed it, its content does not
#   model/layouts/*.ttrg     a saved working graph (not model/layouts/agent/, which the bot generates) is compared
#                            without its `layout:` block — Save as layout writes the positions Maya left the cards at
#   exit 0   clean: no differences, or only the normalised ones (listed)
#   exit 1   the paths that differ, one per line
#   exit 2   usage, a branch that will not fetch, or no zstd
set -euo pipefail

live="${1:?usage: scripts/demo-compare.sh <live-branch>}"
ref="${DEMO_COMPARE_REF:-demo/returns-review}"
remote="${DEMO_COMPARE_REMOTE:-origin}"
command -v zstd >/dev/null || { echo "demo-compare: needs zstd on PATH" >&2; exit 2; }

a=refs/demo-compare/ref
b=refs/demo-compare/live
git fetch --no-tags -q "$remote" "+refs/heads/$ref:$a" "+refs/heads/$live:$b" \
  || { echo "demo-compare: cannot fetch '$ref' and '$live' from $remote" >&2; exit 2; }
scope=(model modeler.toml generated)

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

echo "demo-compare: $ref ($(git rev-parse --short "$a")) vs $live ($(git rev-parse --short "$b"))"
git --no-pager diff --stat "$a" "$b" -- "${scope[@]}"

has() { git cat-file -e "$1:$2" 2>/dev/null; }

# An archive's members, unpacked under <dir>; its snapshot.json is compared through `ids` below, never as is.
unpack() { mkdir -p "$3" && git show "$1:$2" | zstd -dcq | tar -x -C "$3"; }
ids() { sed -E 's/"(modelSnapshotId|modelContentId)": *"[^"]*"/"\1": ""/' "$1"; }
same_archive() {
  unpack "$a" "$1" "$work/a/$1" && unpack "$b" "$1" "$work/b/$1" || return 1
  diff -rq -x snapshot.json "$work/a/$1" "$work/b/$1" >/dev/null || return 1
  diff -q <(ids "$work/a/$1/snapshot.json") <(ids "$work/b/$1/snapshot.json") >/dev/null
}

# A saved layout without its `layout: { … }` block — the writer (@tatrman/parser/layout) puts it at two spaces — and
# without trailing commas, so `objects: [ … ],` before a block reads the same as `objects: [ … ]` with none.
objects() {
  git show "$1:$2" | awk '/^  layout: \{/ { skip = 1 } !skip { print } skip && /^  \}/ { skip = 0 }' | sed -E 's/,$//'
}

differ=()
normalised=()
while IFS= read -r p; do
  if ! has "$a" "$p" || ! has "$b" "$p"; then differ+=("$p"); continue; fi
  case "$p" in
    generated/*.tar.zst)
      if same_archive "$p"; then normalised+=("$p (resolvedFrom ids only)"); else differ+=("$p"); fi ;;
    model/layouts/agent/*) differ+=("$p") ;;
    model/layouts/*.ttrg)
      if [ "$(objects "$a" "$p")" = "$(objects "$b" "$p")" ]; then normalised+=("$p (positions only)"); else differ+=("$p"); fi ;;
    *) differ+=("$p") ;;
  esac
done < <(git diff --name-only "$a" "$b" -- "${scope[@]}")

for n in ${normalised[@]+"${normalised[@]}"}; do echo "demo-compare: normalised — $n"; done
if [ "${#differ[@]}" -gt 0 ]; then
  echo "demo-compare: ${#differ[@]} path(s) differ:"
  printf '%s\n' "${differ[@]}"
  exit 1
fi
echo "demo-compare: clean"
