import contextlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


class RecipeBuildTest(unittest.TestCase):
    def test_warning_refuses_build_without_replacing_existing_bundle(self):
        spec = importlib.util.spec_from_file_location('build_recipes', Path(__file__).with_name('build-recipes.py'))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recipe = root / 'automation/example'
            recipe.mkdir(parents=True)
            (recipe / 'example.ttrp').write_text('recipe {}')
            bundle = recipe / 'example.bundle'
            bundle.mkdir()
            (bundle / 'sentinel').write_text('previous approved build')
            cli = root / 'fake-cli'
            cli.write_text('#!/usr/bin/env python3\nprint(\'{"diagnostics": [{"severity": "WARNING", "message": "unsafe"}]}\')\n')
            cli.chmod(0o755)
            with patch.object(module, 'ROOT', root), patch('sys.argv', ['build-recipes.py', '--cli', str(cli)]):
                with contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(module.main(), 1)
            self.assertEqual((bundle / 'sentinel').read_text(), 'previous approved build')


if __name__ == '__main__':
    unittest.main()
