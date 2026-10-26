import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class PreviewRuntimeTest(unittest.TestCase):
    def test_only_the_exact_clean_runtime_reaches_gradle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = root / 'bundle'
            (app / 'scripts').mkdir(parents=True)
            for name in ['writer-preview.py', 'toolchain-lock.py']:
                shutil.copy2(Path(__file__).with_name(name), app / 'scripts' / name)
            server = root / 'server'
            server.mkdir()

            def git(*args):
                return subprocess.check_output(['git', '-C', str(server), *args], text=True).strip()

            git('init', '-q')
            (server / '.gitignore').write_text('invoked\n')
            (server / 'gradlew').write_text('#!/bin/sh\nprintf "%s\\n" "$PWD" "$@" > invoked\n')
            (server / 'gradlew').chmod(0o755)
            git('add', '.')
            git('-c', 'user.name=test', '-c', 'user.email=test@example.com', 'commit', '-qm', 'runtime')
            expected = git('rev-parse', 'HEAD')

            def pin(ref):
                (app / 'toolchain.lock').write_text(
                    '[ttr-core]\nref="grammar/v0.18.3"\n[ttrp]\nref="grammar/v0.18.11"\n'
                    '[veles]\nimage="0.11.15"\nttr-metadata="0.18.3"\nstrict-load=true\n'
                    f'[automation-preview]\nserver-ref="{ref}"\ngrammar="0.18.12"\n',
                )

            def run():
                return subprocess.run(['python3', str(app / 'scripts/writer-preview.py'), '--server', str(server)],
                                      env=os.environ.copy(), text=True, capture_output=True)

            pin('a' * 40)
            refused = run()
            self.assertNotEqual(refused.returncode, 0)
            self.assertIn('toolchain.lock requires', refused.stderr)
            self.assertFalse((server / 'invoked').exists())
            pin(expected)
            (server / 'stray.kt').write_text('unreviewed source')
            refused = run()
            self.assertNotEqual(refused.returncode, 0)
            self.assertIn('local changes', refused.stderr)
            self.assertFalse((server / 'invoked').exists())
            (server / 'stray.kt').unlink()
            accepted = run()
            self.assertEqual(accepted.returncode, 0, accepted.stderr)
            args = (server / 'invoked').read_text().splitlines()
            self.assertEqual(args[0], str(server.resolve()))
            self.assertIn('-Dhartland.grammar=0.18.12', args)
            self.assertIn(f'-Dhartland.root={app.resolve()}', args)
            self.assertIn('org.tatrman.automation.runner.HartlandWriterPreviewSpec', args)
            self.assertFalse(any('frontend' in arg for arg in args))


if __name__ == '__main__':
    unittest.main()
