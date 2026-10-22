#!/usr/bin/env python3
"""Build/check every authored recipe, refusing warnings as well as errors."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CLI = ROOT / ".modeler/toolchains/ttrp/packages/kotlin/ttrp-cli/build/install/ttrp-cli/bin/ttrp-cli"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cli", default=os.environ.get("TTRP_CLI", str(DEFAULT_CLI)))
    parser.add_argument("--check", action="store_true", help="Check only, without emitting bundles")
    args = parser.parse_args()
    if not Path(args.cli).is_file():
        parser.error("pinned ttrp CLI missing: run `just toolchain-ttrp` first (or set TTRP_CLI)")
    files = sorted(p for p in (ROOT / "automation").rglob("*.ttrp") if "stub" not in p.parts)
    built = 0
    for file in files:
        # Ops are deferred until the Server serves automation.ops (P4).
        if file.parent.parent.name == "ops":
            print(f"{file.relative_to(ROOT)}: deferred (automation.ops requires Server P4)")
            continue
        command = [args.cli, "check" if args.check else "build", str(file)]
        with tempfile.TemporaryDirectory(prefix="recipe-build-") as scratch:
            if not args.check:
                command.extend(["--json", "--out", scratch])
            result = subprocess.run(command, text=True, capture_output=True, cwd=ROOT)
            stderr = "\n".join(
                line for line in result.stderr.splitlines()
                if line and not line.startswith(("ANTLR ", "SLF4J("))
            )
            try:
                diagnostics = result.stdout.strip() if args.check else json.loads(result.stdout)["diagnostics"]
            except (ValueError, KeyError):
                diagnostics = result.stdout or "CLI returned no build result"
            if result.returncode or diagnostics or stderr:
                print(f"{file.relative_to(ROOT)}: recipe {'check' if args.check else 'build'} refused", file=sys.stderr)
                print(diagnostics, stderr, sep="\n", file=sys.stderr)
                return 1
            if not args.check:
                bundle = file.parent / (file.stem + ".bundle")
                if bundle.exists():
                    shutil.rmtree(bundle)
                shutil.copytree(Path(scratch) / bundle.name, bundle)
        built += 1
        print(f"{file.relative_to(ROOT)}: {'checked' if args.check else 'built'}")
    print(f"{built} recipes {'check clean' if args.check else 'built without diagnostics'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
