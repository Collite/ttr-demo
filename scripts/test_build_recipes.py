import contextlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('build_recipes', Path(__file__).with_name('build-recipes.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class RecipeBuildTest(unittest.TestCase):
    def run_case(self, behavior, expected, stale=False, out=False):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'hartland-wt'
            recipe = root / 'automation/example'
            recipe.mkdir(parents=True)
            (recipe / 'example.ttrp').write_text('recipe {}')
            (root / 'modeler.toml').write_text('[ttrp]\nextra-model-roots = []\n')
            bundle = recipe / 'example.bundle'
            bundle.mkdir()
            (bundle / 'sentinel').write_text('approved')
            gone = root / 'automation/gone/gone.bundle'
            gone.mkdir(parents=True)
            (gone / 'manifest.json').write_text('{}')
            ops = root / 'automation/ops/deferred'
            ops.mkdir(parents=True)
            (ops / 'deferred.ttrp').write_text('recipe {}')
            (ops / 'deferred.bundle').mkdir()
            cli = root / 'fake-cli'
            cli.write_text('''#!/usr/bin/env python3
import sys,json
from pathlib import Path
assert Path.cwd().name == 'hartland'
out = Path(sys.argv[sys.argv.index('--out')+1])
''' + behavior)
            cli.chmod(0o755)
            argv = ['build-recipes.py', '--cli', str(cli)]
            if out:
                argv += ['--out', str(root / 'fresh')]
            with patch.object(module, 'ROOT', root), patch('sys.argv', argv):
                with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(module.main(), expected)
            if expected or out:
                self.assertEqual((bundle / 'sentinel').read_text(), 'approved')
                self.assertTrue(gone.exists())
                self.assertTrue((ops / 'deferred.bundle').exists())
            else:
                self.assertTrue((bundle / 'manifest.json').is_file())
                self.assertFalse(gone.exists())
                self.assertFalse((ops / 'deferred.bundle').exists())
            if out:
                self.assertTrue((root / 'fresh/example/example.bundle/manifest.json').is_file())

    def test_warning_preserves_all_bundles(self):
        self.run_case('print(json.dumps({"diagnostics": [{"severity":"WARNING"}]}))', 1)

    def test_missing_output_preserves_all_bundles(self):
        self.run_case('print(json.dumps({"bundle": str(out/"example.bundle"), "diagnostics": []}))', 1)

    def test_wrong_recipe_name_preserves_all_bundles(self):
        self.run_case('p=out/"other.bundle";p.mkdir(parents=True);(p/"manifest.json").write_text("{}")\nprint(json.dumps({"bundle":str(p),"diagnostics":[]}))', 1)

    def test_success_stages_worktree_and_removes_orphans_and_deferred_bundles(self):
        self.run_case(SUCCESS, 0)

    def test_out_does_not_modify_source(self):
        self.run_case(SUCCESS, 0, out=True)


SUCCESS = 'p=out/"example.bundle";p.mkdir(parents=True);(p/"manifest.json").write_text("{}")\nprint(json.dumps({"bundle":str(p),"diagnostics":[]}))'

if __name__ == '__main__':
    unittest.main()
