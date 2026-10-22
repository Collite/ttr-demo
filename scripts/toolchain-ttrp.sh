#!/usr/bin/env bash
# Independent immutable recipe compiler; release tags are refreshed to detect re-cuts.
set -euo pipefail
cd "$(dirname "$0")/.."
pins="$(python3 scripts/toolchain-lock.py)"
while IFS='=' read -r key value; do export "$key=$value"; done <<<"$pins"
ref="$TTRP_REF"; version="$TTRP_VERSION"
dest=".modeler/toolchains/ttrp"
if [ ! -d "$dest/.git" ]; then
  git init "$dest"
  git -C "$dest" remote add origin "${TTR_CORE_REPO:-https://github.com/Collite/ttr-core.git}"
fi
git -C "$dest" remote set-url origin "${TTR_CORE_REPO:-https://github.com/Collite/ttr-core.git}"
dirty="$(git -C "$dest" status --porcelain)"
if [ -n "$dirty" ]; then
  echo "toolchain-ttrp: $dest has local changes; refusing an unpinned build" >&2
  echo "$dirty" >&2
  exit 1
fi
if [[ "$ref" =~ ^[0-9a-f]{40}$ ]]; then
  if ! target="$(git -C "$dest" rev-parse --verify "$ref^{commit}" 2>/dev/null)"; then
    git -C "$dest" fetch --depth 1 --no-tags origin "$ref"
    target="$(git -C "$dest" rev-parse FETCH_HEAD)"
  fi
else
  git -C "$dest" fetch --depth 1 --no-tags --force origin "+refs/tags/$ref:refs/tags/$ref"
  target="$(git -C "$dest" rev-parse "refs/tags/$ref^{commit}")"
fi
installed="$dest/packages/kotlin/ttrp-cli/build/install/ttrp-cli/bin/ttrp-cli"
# Only a successful build certifies the installed CLI's commit and version.
if [ -f "$installed" ] && [ "$(cat "$dest/.git/ttrp-build" 2>/dev/null || true)" = "$target $version" ]; then
  exit 0
fi
rm -f "$dest/.git/ttrp-build" "$dest/.git/ttrp-version"
git -C "$dest" checkout --detach "$target"
if [ "${TOOLCHAIN_TTRP_SKIP_BUILD:-0}" != 1 ]; then
  if [ -n "${TOOLCHAIN_TTRP_BUILD_CMD:-}" ]; then
    (cd "$dest" && bash -euo pipefail -c "$TOOLCHAIN_TTRP_BUILD_CMD")
  else
    (cd "$dest" && ./gradlew --no-configuration-cache :packages:kotlin:ttrp-cli:installDist -Pversion="$version" --no-daemon -Dorg.gradle.jvmargs=-Xmx4g -Pkotlin.compiler.execution.strategy=in-process --max-workers=2)
  fi
  printf '%s %s\n' "$target" "$version" > "$dest/.git/ttrp-build"
fi
