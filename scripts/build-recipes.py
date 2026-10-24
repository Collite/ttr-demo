#!/usr/bin/env python3
"""Build/check authored recipes with the pinned CLI, staging worktrees for the path-based resolver."""

import argparse
import contextlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CLI = ROOT / '.modeler/toolchains/ttrp/packages/kotlin/ttrp-cli/build/install/ttrp-cli/bin/ttrp-cli'


def literate_documents(root):
    """Find source fences, plus sidecar owners so a removed skeleton still fails the native check."""
    automation = root / 'automation'
    eligible = lambda p: not any(part.endswith('.bundle') for part in p.parts) and '.cs.' not in p.name
    docs = {p for p in automation.rglob('*.md') if eligible(p)
            and re.search(r'^```ttrp(?:\s|$)', p.read_text(), re.M)}
    for sidecar in automation.rglob('*.ttrd'):
        if not eligible(sidecar):
            continue
        try:
            name = json.loads(sidecar.read_text())['document']
        except (ValueError, KeyError):
            # Let the native document check report malformed provenance as drift.
            continue
        candidates = [sidecar.parent / name, sidecar.parent.parent / name]
        found = [p for p in candidates if p.is_file()]
        if not found:
            raise ValueError(f'{sidecar.relative_to(root)}: missing source document {name}')
        docs.add(found[0])
    return sorted(docs)


@contextlib.contextmanager
def recipe_root(root, announce=True, include_bundles=False):
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
                ignored = ['*.bundle.new', '*.bundle.old', 'node_modules', '.modeler']
                if not include_bundles:
                    ignored.append('*.bundle')
                shutil.copytree(root / rel, stage / rel, dirs_exist_ok=True,
                                ignore=shutil.ignore_patterns(*ignored))
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


def deferred_ops(file):
    return file.parent.parent.name == 'ops'


def twin_artifacts(cli, stage, file, out, expected, check):
    """Compile CS in isolation: one executable program, separate prose/provenance; never publish a second bundle."""
    twin = file.with_suffix('.cs.md')
    if not twin.exists():
        raise ValueError(f'TTRP-DOC-003: missing Czech twin: {twin.relative_to(ROOT)}')
    command = [str(cli), 'build', str(stage / twin.relative_to(ROOT)), '--lang', 'cs', '--json', '--out', str(out)]
    if deferred_ops(file):
        command.append('--derive-only')
    result = subprocess.run(command, text=True, capture_output=True, cwd=stage)
    stderr = '\n'.join(line for line in result.stderr.splitlines()
                       if line and not line.startswith(('ANTLR ', 'SLF4J(')))
    payload = json.loads(result.stdout)
    if result.returncode or stderr or payload['diagnostics'] or any(r.get('diagnostics') for r in payload.get('recipes', [])):
        raise ValueError(f'{twin.relative_to(ROOT)}: Czech derivation refused: {result.stdout} {stderr}')
    artifacts = []
    for canonical in out.rglob('*.ttrp'):
        if any(part.endswith('.bundle') for part in canonical.parts):
            continue
        rel = canonical.relative_to(out)
        en_rel = Path(str(rel).replace('.cs.ttrp', '.ttrp'))
        en = file.parent / en_rel
        original = expected.get(en, en)
        if canonical.read_bytes() != original.read_bytes():
            raise ValueError(f'{twin.relative_to(ROOT)}: canonical differs from English: {en_rel}')
        sidecar = canonical.with_suffix('.ttrd')
        artifacts.append((sidecar, en.with_suffix('.cs.ttrd')))
    if not artifacts:
        raise ValueError(f'{twin.relative_to(ROOT)}: no canonical/provenance output')
    for recipe in payload.get('recipes', []):
        manifest = recipe['manifest']
        name = manifest['recipe']['name']
        en_bundle = (file.parent / name / (name + '.bundle') if len(payload['recipes']) > 1
                     else file.parent / (file.stem + '.bundle'))
        en_manifest = expected.get(en_bundle / 'manifest.json', en_bundle / 'manifest.json')
        if manifest['recipe']['fingerprints']['text'] != json.loads(en_manifest.read_text())['recipe']['fingerprints']['text']:
            raise ValueError(f'{twin.relative_to(ROOT)}: {name} text fingerprint differs')
        # Native README directories use the recipe name; keep EN/CS explanations together.
        readme_dir = out / name
        target_dir = file.parent / name if len(payload['recipes']) > 1 else file.parent / file.stem
        artifacts.append((readme_dir / 'README.md', target_dir / 'README.cs.md'))
    for derived, committed in artifacts:
        if not derived.is_file():
            raise ValueError(f'CLI omitted Czech artifact {derived.relative_to(out)}')
    if check:
        for derived, committed in artifacts:
            if not committed.is_file() or derived.read_bytes() != committed.read_bytes():
                raise ValueError(f'TTRP-DOC-003: Czech artifact drifts: {committed.relative_to(ROOT)}')
    return artifacts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cli', default=os.environ.get('TTRP_CLI', str(DEFAULT_CLI)))
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--literate-check', action='store_true', help='Check Markdown-derived artifacts without writing; exit 3 on drift')
    parser.add_argument('--out', type=Path, help='Build into this directory without touching committed bundles')
    parser.add_argument('--recipe', type=Path, help='Limit to one recipe (including deferred authoring probes)')
    parser.add_argument('--command', choices=['check', 'explain'], help='Pass through a staged CLI authoring command')
    args = parser.parse_args()
    cli = Path(args.cli).absolute()
    if not cli.is_file():
        parser.error('pinned ttrp CLI missing: run `just toolchain-ttrp` (or set TTRP_CLI)')
    files = [args.recipe.resolve()] if args.recipe else sorted((ROOT / 'automation').rglob('*.ttrp'))
    files = [p for p in files if not any(part.endswith('.bundle') for part in p.parts)]
    if args.literate_check:
        try:
            files = [args.recipe.resolve()] if args.recipe else literate_documents(ROOT)
        except ValueError as e:
            print(e, file=sys.stderr)
            return 3
        if not files:
            parser.error('no literate recipe documents found')
    elif not args.check and not args.command:
        files = ([p.with_suffix('.md') if p.with_suffix('.md').is_file() else p for p in files]
                 if args.recipe else literate_documents(ROOT) + files)
    if args.command and not args.recipe:
        parser.error('--command requires --recipe')
    with recipe_root(ROOT, announce=not args.command, include_bundles=args.literate_check) as stage, tempfile.TemporaryDirectory(prefix='recipe-output-') as tmp:
        pending = []
        artifacts = []
        owned = set()
        checked = 0
        sources = []
        for i, file in enumerate(files):
            if file in owned:
                continue
            if not args.recipe and deferred_ops(file) and file.suffix != '.md':
                print(f'{file.relative_to(ROOT)}: deferred (automation.ops requires Server P4)')
                continue
            out = Path(tmp) / str(i)
            command = [str(cli), args.command or ('check' if args.check else 'build'), str(stage / file.relative_to(ROOT))]
            if file.suffix == '.md' and deferred_ops(file):
                command.append('--derive-only')
            if args.literate_check:
                command += ['--check', '--json']
            elif not args.check and not args.command:
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
                if not args.check:
                    diagnostics = diagnostics + [d for r in payload.get('recipes', []) for d in r.get('diagnostics', [])]
            except (ValueError, KeyError):
                diagnostics = result.stdout or 'CLI returned no build result'
            if result.returncode or diagnostics or stderr:
                print(f'{file.relative_to(ROOT)}: recipe refused\n{diagnostics}\n{stderr}', file=sys.stderr)
                return 3 if args.literate_check and result.returncode == 3 else 1
            checked += 1
            if file.suffix == '.md':
                sources.append(file)
            if file.suffix == '.md' and deferred_ops(file) and not args.literate_check:
                for rel in (file.stem + '.ttrp', file.stem + '.ttrd'):
                    derived = out / rel
                    if not derived.is_file():
                        print(f'CLI omitted deferred derivation {rel}', file=sys.stderr)
                        return 1
                    artifacts.append((derived, file.parent / rel))
                owned.add(file.with_suffix('.ttrp'))
                continue
            if not args.check and not args.literate_check:
                results = [payload]
                if file.suffix == '.md':
                    results = payload.get('recipes', [])
                    if not results:
                        print(f'{file.relative_to(ROOT)}: document returned no recipes', file=sys.stderr)
                        return 1
                    for result in results:
                        name = result['manifest']['recipe']['name']
                        # Named multi-recipe documents derive <name>/<name>.* beside the source.
                        rels = ([f'{name}/{name}.ttrp', f'{name}/{name}.ttrd', f'{name}/README.md']
                                if len(results) > 1 else
                                [file.stem + '.ttrp', file.stem + '.ttrd', file.stem + '/README.md'])
                        canonical = file.parent / rels[0]
                        if canonical in owned:
                            print(f'{canonical.relative_to(ROOT)}: multiple document owners', file=sys.stderr)
                            return 1
                        owned.add(canonical)
                        for rel in rels:
                            derived = out / rel
                            if not derived.is_file():
                                print(f'CLI omitted derived artifact {rel}', file=sys.stderr)
                                return 1
                            artifacts.append((derived, file.parent / rel))
                for result in results:
                    src = Path(result.get('bundle') or '')
                    if not src.is_absolute():
                        src = stage / src
                    name = result.get('manifest', {}).get('recipe', {}).get('name', file.stem)
                    expected = (Path(name) / (name + '.bundle') if file.suffix == '.md' and len(results) > 1
                                else Path(file.stem + '.bundle'))
                    if src != out / expected or not src.is_dir() or not (src / 'manifest.json').is_file():
                        print(f'CLI wrote {src}, expected {expected} with manifest.json', file=sys.stderr)
                        return 1
                    pending.append((src, file.parent / expected))
        expected = dict((target, source) for source, target in artifacts)
        for source, target in pending:
            expected[target / 'manifest.json'] = source / 'manifest.json'
        try:
            for i, file in enumerate(sources):
                artifacts += twin_artifacts(cli, stage, file, Path(tmp) / f'cs-{i}', expected, args.literate_check)
        except (ValueError, KeyError) as e:
            print(str(e), file=sys.stderr)
            return 3 if args.literate_check else 1
        if args.literate_check:
            print(f'{checked} English documents and their Czech twins checked')
            return 0
        # No committed bundle changes until every recipe has compiled and its output has been validated.
        for src, bundle in pending:
            target = args.out.resolve() / bundle.relative_to(ROOT / 'automation') if args.out else bundle
            target.parent.mkdir(parents=True, exist_ok=True)
            replace_bundle(src, target)
        for src, artifact in artifacts:
            target = args.out.resolve() / artifact.relative_to(ROOT / 'automation') if args.out else artifact
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target)
        if not args.check and not args.literate_check and not args.out and not args.recipe:
            expected = {bundle for _, bundle in pending}
            for bundle in (ROOT / 'automation').rglob('*.bundle'):
                if bundle.is_dir() and bundle not in expected:
                    shutil.rmtree(bundle)
                    print(f'removed stale bundle {bundle.relative_to(ROOT)}')
        count = checked if args.check or args.literate_check else len(pending)
        noun = 'documents' if args.literate_check else 'recipes'
        print(f'{count} {noun} {"checked" if args.check or args.literate_check else "built without diagnostics"}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
