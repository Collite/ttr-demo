#!/usr/bin/env python3
"""Run the Hartland-owned preview spec against the exact accepted Server test runtime."""

import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def verify_server(server: Path, expected: str) -> None:
    head = subprocess.check_output(['git', '-C', str(server), 'rev-parse', 'HEAD'], text=True).strip()
    if head != expected:
        raise ValueError(f'preview Server is {head}, toolchain.lock requires {expected}')
    dirty = subprocess.check_output(['git', '-C', str(server), 'status', '--porcelain'], text=True)
    if dirty:
        raise ValueError('preview Server checkout has local changes; refusing an unpinned runtime')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server', type=Path, required=True, help='clean ttr-server checkout at the locked commit')
    args = parser.parse_args()
    pins = dict(line.split('=', 1) for line in subprocess.check_output(
        [sys.executable, str(ROOT / 'scripts/toolchain-lock.py')], text=True,
    ).splitlines())
    try:
        expected = pins['AU_PREVIEW_SERVER_REF']
        server = args.server.resolve()
        verify_server(server, expected)
    except (KeyError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f'writer-preview: {error}\n')
    print(f'Hartland preview: Server {expected}; published grammar {pins["TTRP_VERSION"]}', flush=True)
    return subprocess.call([
        str(server / 'gradlew'),
        '-I', str(ROOT / 'automation/tests/writer-preview/init.gradle'),
        f'-Dhartland.root={ROOT}', f'-Dhartland.grammar={pins["TTRP_VERSION"]}',
        ':services:automation:hartlandVerifyPublishedCatalog',
        ':services:automation:test', '--tests', 'org.tatrman.automation.runner.HartlandWriterPreviewSpec',
        '--console=plain', '--max-workers=2',
    ], cwd=server, env=os.environ.copy())


if __name__ == '__main__':
    sys.exit(main())
