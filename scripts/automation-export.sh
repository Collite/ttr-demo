#!/usr/bin/env bash
# AU-hartland P4·S4.1 — the engine exports and deployment of one deployment set (processes/sets.json).
#
#   scripts/automation-export.sh export <set>            exports/<d>/ for every deployment of the set (re-emit)
#   scripts/automation-export.sh deploy <set> [--check]  `ttrp emit --deploy` of the set's deployments, then the
#                                                         composed processes/<set>/*.bpmn as one engine deployment
#
# Every emit runs from a `git archive` copy of HEAD (S4.1 pre-flight 3, P3H Found 4): run from this checkout, the
# program resolver also scans the gitignored .modeler/toolchains/ttrp (ttr-core's fixture recipes) and refuses
# TTRP-EXPORT-REF. So `export` emits what is COMMITTED — commit a recipe/world change before re-exporting.
# deploy: TTR_BEARER (or --token-env's variable) holds the engine bearer; ENGINE_URL overrides the executor's url,
# e.g. a port-forward: ENGINE_URL=http://127.0.0.1:8080/engine-rest.
set -euo pipefail
cd "$(dirname "$0")/.."
mode="${1:?export|deploy}"; set_name="${2:?a deployment set of processes/sets.json}"; shift 2
check=""; [ "${1:-}" = "--check" ] && check="--check"

cli="$PWD/.modeler/toolchains/ttrp/packages/kotlin/ttrp-cli/build/install/ttrp-cli/bin/ttrp-cli"
[ -x "$cli" ] || { echo "no built ttrp CLI — run: just toolchain-ttrp" >&2; exit 1; }

# deployment → its recipe bundle (the deployment's program's recipe)
deployments="$(python3 - "$set_name" <<'PY'
import json, re, sys, pathlib
sets = json.loads(pathlib.Path("processes/sets.json").read_text())
if sys.argv[1] not in sets:
    sys.exit(f"no deployment set {sys.argv[1]!r} in processes/sets.json")
world = pathlib.Path("automation/worlds/demo.ttrm").read_text()
programs = pathlib.Path("automation/programs.ttrm").read_text()
for d in sets[sys.argv[1]]["deployments"].values():
    program = re.search(rf"def deployment {d}\s*\{{\s*program:\s*(\w+)", world).group(1)
    recipe = re.search(rf"def program {program}\s*\{{\s*recipe:\s*(\w+)", programs).group(1)
    print(d, recipe)
PY
)"

copy="$(mktemp -d "${TMPDIR:-/tmp}/s41-archive.XXXXXX")"
trap 'rm -rf "$copy"' EXIT
git archive HEAD | tar -x -C "$copy"

while read -r d recipe; do
  bundle="automation/$recipe/$recipe.bundle"
  if [ "$mode" = export ]; then
    rm -rf "exports/$d"
    (cd "$copy" && "$cli" emit --deployment "$d" --bundle "$bundle" --out "$OLDPWD/exports/$d" >/dev/null)
    echo "exports/$d ← $bundle"
  else
    (cd "$copy" && "$cli" emit --deployment "$d" --bundle "$bundle" --deploy $check \
        ${ENGINE_URL:+--engine-url "$ENGINE_URL"})
  fi
done <<<"$deployments"

if [ "$mode" = deploy ] && [ -z "$check" ]; then
  url="${ENGINE_URL:-$(sed -n 's/.*def executor engine { extends: process_engine, url: "\([^"]*\)".*/\1/p' automation/worlds/demo.ttrm)}"
  token="${TTR_BEARER:?TTR_BEARER holds the engine bearer}"
  args=(-F "deployment-name=hartland-processes-$set_name" -F "enable-duplicate-filtering=true" -F "deployment-source=hartland:processes/$set_name")
  for f in processes/"$set_name"/*.bpmn; do args+=(-F "data$(basename "$f" .bpmn)=@$f"); done
  curl -sS --fail-with-body -H "Authorization: Bearer $token" -X POST "$url/deployment/create" "${args[@]}" \
    | python3 -c 'import json,sys; d=json.load(sys.stdin); print("processes", d["id"], sorted(p["key"] for p in (d.get("deployedProcessDefinitions") or {}).values()) or "(unchanged)")'
fi
