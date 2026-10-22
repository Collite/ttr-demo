#!/usr/bin/env python3
"""Build/check authored recipes with the pinned CLI, staging worktrees for the path-based resolver."""

import argparse
import contextlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tomllib

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CLI = ROOT / '.modeler/toolchains/ttrp/packages/kotlin/ttrp-cli/build/install/ttrp-cli/bin/ttrp-cli'


@contextlib.contextmanager
def recipe_root(root, announce=True):
    if root.name == 'hartland':
        yield root
        return
    with tempfile.TemporaryDirectory(prefix='recipe-stage-') as tmp:
        stage = Path(tmp) / 'hartland'
        stage.mkdir()
        config = root / 'modeler.toml'
        roots = ['automation']
        if config.exists():
            shutil.copy2(config, stage / config.name)
            roots += tomllib.loads(config.read_text()).get('ttrp', {}).get('extra-model-roots', [])
        for rel in sorted(set(roots)):
            if (root / rel).is_dir():
                shutil.copytree(root / rel, stage / rel, dirs_exist_ok=True,
                                ignore=shutil.ignore_patterns('*.bundle', '*.bundle.new', '*.bundle.old', 'node_modules', '.modeler'))
        if announce:
            print('recipe CLI staged in a hartland directory (ttr-core path resolver workaround)', file=sys.stderr)
        yield stage


def replace_bundle(src, bundle):
    new = bundle.with_name(bundle.name + '.new')
    old = bundle.with_name(bundle.name + '.old')
    # Recover a prior interruption between the two renames before replacing anything.
    if old.exists() and not bundle.exists():
        old.rename(bundle)
    shutil.rmtree(new, ignore_errors=True)
    shutil.copytree(src, new)
    shutil.rmtree(old, ignore_errors=True)
    if bundle.exists():
        bundle.rename(old)
    try:
        new.rename(bundle)
    except OSError:
        if old.exists():
            old.rename(bundle)
        raise
    shutil.rmtree(old, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cli', default=os.environ.get('TTRP_CLI', str(DEFAULT_CLI)))
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--out', type=Path, help='Build into this directory without touching committed bundles')
    parser.add_argument('--recipe', type=Path, help='Limit to one recipe (including deferred authoring probes)')
    parser.add_argument('--command', choices=['check', 'explain'], help='Pass through a staged CLI authoring command')
    args = parser.parse_args()
    cli = Path(args.cli).absolute()
    if not cli.is_file():
        parser.error('pinned ttrp CLI missing: run `just toolchain-ttrp` (or set TTRP_CLI)')
    files = [args.recipe.resolve()] if args.recipe else sorted((ROOT / 'automation').rglob('*.ttrp'))
    files = [p for p in files if not any(part.endswith('.bundle') for part in p.parts)]
    if args.command and not args.recipe:
        parser.error('--command requires --recipe')
    with recipe_root(ROOT, announce=not args.command) as stage, tempfile.TemporaryDirectory(prefix='recipe-output-') as tmp:
        pending = []
        for i, file in enumerate(files):
            if not args.recipe and file.parent.parent.name == 'ops':
                print(f'{file.relative_to(ROOT)}: deferred (automation.ops requires Server P4)')
                continue
            out = Path(tmp) / str(i)
            command = [str(cli), args.command or ('check' if args.check else 'build'), str(stage / file.relative_to(ROOT))]
            if not args.check and not args.command:
                command += ['--json', '--out', str(out)]
            result = subprocess.run(command, text=True, capture_output=True, cwd=stage)
            stderr = '\n'.join(line for line in result.stderr.splitlines()
                               if line and not line.startswith(('ANTLR ', 'SLF4J(')))
            if args.command:
                print(result.stdout, end='')
                if stderr:
                    print(stderr, file=sys.stderr)
                return result.returncode
            try:
                payload = {} if args.check else json.loads(result.stdout)
                diagnostics = result.stdout.strip() if args.check else payload['diagnostics']
            except (ValueError, KeyError):
                diagnostics = result.stdout or 'CLI returned no build result'
            if result.returncode or diagnostics or stderr:
                print(f'{file.relative_to(ROOT)}: recipe refused\n{diagnostics}\n{stderr}', file=sys.stderr)
                return 1
            if not args.check:
                bundle = file.parent / (file.stem + '.bundle')
                src = Path(payload.get('bundle') or '')
                if not src.is_absolute():
                    src = stage / src
                if src.name != bundle.name or not src.is_dir() or not (src / 'manifest.json').is_file():
                    print(f'CLI wrote {src}, expected {bundle.name} with manifest.json (recipe name must equal file stem)', file=sys.stderr)
                    return 1
                pending.append((src, bundle))
        # No committed bundle changes until every recipe has compiled and its output has been validated.
        for src, bundle in pending:
            target = args.out.resolve() / bundle.relative_to(ROOT / 'automation') if args.out else bundle
            target.parent.mkdir(parents=True, exist_ok=True)
            replace_bundle(src, target)
        if not args.check and not args.out and not args.recipe:
            expected = {bundle for _, bundle in pending}
            for bundle in (ROOT / 'automation').rglob('*.bundle'):
                if bundle.is_dir() and bundle not in expected:
                    shutil.rmtree(bundle)
                    print(f'removed stale bundle {bundle.relative_to(ROOT)}')
        print(f'{len(pending) if not args.check else len(files)} recipes {"checked" if args.check else "built without diagnostics"}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
