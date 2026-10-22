#!/usr/bin/env bash
# An isolated checkout, independent of whatever ../tatrman happens to contain.
set -euo pipefail
cd "$(dirname "$0")/.."
ref="$(python3 scripts/toolchain-lock.py ttrp)"
dest=".modeler/toolchains/ttrp"
version="$(python3 scripts/toolchain-lock.py ttrp --version)"
if [ ! -d "$dest/.git" ]; then
  git init "$dest"
  git -C "$dest" remote add origin "${TTR_CORE_REPO:-https://github.com/Collite/ttr-core.git}"
fi
if git -C "$dest" rev-parse --verify HEAD >/dev/null 2>&1 && [ -n "$(git -C "$dest" status --porcelain --untracked-files=no)" ]; then
  echo "toolchain-ttrp: $dest has local changes; refusing an unpinned build" >&2
  exit 1
fi
if ! target="$(git -C "$dest" rev-parse --verify "$ref^{commit}" 2>/dev/null)"; then
  git -C "$dest" fetch --depth 1 origin "$ref"
  target="$(git -C "$dest" rev-parse FETCH_HEAD)"
fi
git -C "$dest" checkout --detach "$target"
cd "$dest"
./gradlew :packages:kotlin:ttrp-cli:installDist -Pversion="$version" --no-daemon -Dorg.gradle.jvmargs=-Xmx4g -Pkotlin.compiler.execution.strategy=in-process --max-workers=2
