import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('build_recipes', Path(__file__).with_name('build-recipes.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class RecipeBuildTest(unittest.TestCase):
    def test_sidecar_keeps_source_in_drift_check_after_all_recipe_fences_are_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / 'automation/one'
            folder.mkdir(parents=True)
            source = root / 'automation/returns.md'
            source.write_text('All executable fences were accidentally removed.\n')
            (folder / 'one.ttrd').write_text(json.dumps({'document': source.name}))
            self.assertEqual(module.literate_documents(root), [source])
            source.unlink()
            with self.assertRaisesRegex(ValueError, 'missing source document returns.md'):
                module.literate_documents(root)

    def test_malformed_sidecar_is_left_for_native_drift_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / 'automation/one'
            folder.mkdir(parents=True)
            source = root / 'automation/returns.md'
            source.write_text('```ttrp\nrecipe: one\nrecipe {}\n```\n')
            (folder / 'one.ttrd').write_text('broken JSON')
            self.assertEqual(module.literate_documents(root), [source])

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

    def multi_recipe_document(self, omit_last=False, warning=False):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'hartland-wt'
            automation = root / 'automation'
            automation.mkdir(parents=True)
            (automation / 'returns.md').write_text('```ttrp\nrecipe: one\nrecipe {}\n```\n')
            for name in ('one', 'two'):
                folder = automation / name
                folder.mkdir()
                (folder / f'{name}.ttrp').write_text('original')
                (folder / f'{name}.bundle').mkdir()
                (folder / f'{name}.bundle/sentinel').write_text('approved')
            cli = root / 'fake-cli'
            cli.write_text('''#!/usr/bin/env python3
import sys,json
from pathlib import Path
assert Path(sys.argv[2]).name == 'returns.md', 'derived canonical must not be compiled again'
out=Path(sys.argv[sys.argv.index('--out')+1])
results=[]
for name in ('one','two'):
    folder=out/name
    bundle=folder/(name+'.bundle')
    bundle.mkdir(parents=True)
    (bundle/'manifest.json').write_text('{}')
    for file in (name+'.ttrp',name+'.ttrd','README.md'):
        (folder/file).write_text('derived')
    results.append({'bundle':str(bundle),'manifest':{'recipe':{'name':name}},'diagnostics':[]})
''' + ("(out/'two/two.ttrd').unlink()\n" if omit_last else '')
                + ("results[-1]['diagnostics']=[{'severity':'WARNING'}]\n" if warning else '')
                + "print(json.dumps({'recipes':results,'diagnostics':[]}))\n")
            cli.chmod(0o755)
            argv = ['build-recipes.py', '--cli', str(cli)]
            expected = 1 if omit_last or warning else 0
            with patch.object(module, 'ROOT', root), patch('sys.argv', argv):
                with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(module.main(), expected)
            for name in ('one', 'two'):
                folder = automation / name
                self.assertEqual((folder / f'{name}.ttrp').read_text(), 'original' if expected else 'derived')
                self.assertEqual((folder / f'{name}.bundle/sentinel').exists(), bool(expected))

    def test_multi_recipe_build_does_not_recompile_derived_canonical(self):
        self.multi_recipe_document()

    def test_incomplete_second_recipe_preserves_all_bundles_and_canonical_files(self):
        self.multi_recipe_document(omit_last=True)

    def test_nested_recipe_warning_preserves_all_bundles_and_canonical_files(self):
        self.multi_recipe_document(warning=True)


SUCCESS = 'p=out/"example.bundle";p.mkdir(parents=True);(p/"manifest.json").write_text("{}")\nprint(json.dumps({"bundle":str(p),"diagnostics":[]}))'

if __name__ == '__main__':
    unittest.main()
