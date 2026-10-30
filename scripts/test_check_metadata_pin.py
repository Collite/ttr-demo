"""Exercise the bump-time recipe against proposed Git values and the common server-libs tag."""
import base64
import json
import os
from pathlib import Path
import subprocess
import tempfile
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]
PINS = tomllib.loads((ROOT / 'toolchain.lock').read_text())['veles']


class MetadataPinTest(unittest.TestCase):
    def run_gate(self, image=None, loader=None, old_path=False, version=None, values_tag=True):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            olymp = temp / 'olymp'
            olymp.mkdir()
            app = olymp / 'clusters/hartland/apps' / ('veles' if old_path else 'metadata')
            app.mkdir(parents=True)
            # Before olymp D43 the release is the values file's tag; after it, config.json `version` (phase 2: alone).
            tag = '  tag: "' + (image or PINS['image']) + '"\n' if values_tag else ''
            (app / 'values.yaml').write_text('image:\n  repository: ghcr.io/collite/metadata\n' + tag)
            if version is not None:
                (app / 'config.json').write_text(json.dumps({'chartRevision': 'master', 'version': version}, indent=2) + '\n')
            subprocess.run(['git', 'init', '-q', str(olymp)], check=True)
            subprocess.run(['git', '-C', str(olymp), 'add', '.'], check=True)
            subprocess.run(['git', '-C', str(olymp), '-c', 'commit.gpgsign=false', '-c', 'user.name=Fixture',
                            '-c', 'user.email=fixture@example.test', 'commit', '-qm', 'fixture'], check=True)
            binary = temp / 'bin'
            binary.mkdir()
            gh = binary / 'gh'
            gh.write_text('#!/usr/bin/env python3\nimport os,sys\n'
                          f'assert "ref=server-libs/v{PINS["image"]}" in sys.argv[2], sys.argv\n'
                          'print(os.environ["PIN_TEST_CATALOG"])\n')
            gh.chmod(0o755)
            catalog = f'tatrman-ttr-metadata = "{loader or PINS["ttr-metadata"]}"\n'
            env = dict(os.environ, PATH=str(binary) + os.pathsep + os.environ['PATH'],
                       PIN_TEST_CATALOG=base64.b64encode(catalog.encode()).decode())
            return subprocess.run(['just', 'check-veles-pin', str(olymp), 'HEAD'], cwd=ROOT,
                                  env=env, capture_output=True, text=True)

    def test_common_release_and_proposed_metadata_values_match(self):
        result = self.run_gate()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('server-libs/v' + PINS['image'], result.stdout)
        self.assertIn('apps/metadata/values.yaml', result.stdout)

    def test_wrong_image_is_refused(self):
        result = self.run_gate(image='0.0.1')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('FAIL olymp', result.stderr)

    def test_wrong_loader_is_refused(self):
        result = self.run_gate(loader='0.0.1')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('FAIL ttr-server', result.stderr)

    def test_config_json_version_is_the_release_once_olymp_has_it(self):
        # D43 phase 2: the values file has no tag left
        result = self.run_gate(version=PINS['image'], values_tag=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('apps/metadata/config.json version', result.stdout)

    def test_config_json_version_wins_over_the_values_tag(self):
        # D43 phase 1: both present; ArgoCD deploys `version` (a helm parameter over the values file)
        result = self.run_gate(version='0.0.1')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FAIL olymp HEAD clusters/hartland/apps/metadata/config.json version: metadata '0.0.1'", result.stderr)

    def test_missing_renamed_path_is_not_silently_skipped(self):
        result = self.run_gate(old_path=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('apps/metadata/values.yaml', result.stderr)


if __name__ == '__main__':
    unittest.main()
