import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).with_name('toolchain-ttrp.sh')
READER = SCRIPT.with_name('toolchain-lock.py')


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True, stderr=subprocess.DEVNULL).strip()


class ToolchainTest(unittest.TestCase):
    def test_recut_tag_remote_update_and_untracked_refusal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / 'source'
            repo.mkdir()
            git(repo, 'init')
            git(repo, 'config', 'user.email', 'test@example.com')
            git(repo, 'config', 'user.name', 'test')
            (repo / 'a').write_text('A')
            git(repo, 'add', 'a')
            git(repo, 'commit', '-m', 'A')
            git(repo, 'tag', 'grammar/v9.9.9')
            app = root / 'hartland'
            (app / 'scripts').mkdir(parents=True)
            shutil.copy2(SCRIPT, app / 'scripts/toolchain-ttrp.sh')
            shutil.copy2(READER, app / 'scripts/toolchain-lock.py')
            (app / 'toolchain.lock').write_text('[ttr-core]\nref="grammar/v0.16.1"\n[ttrp]\nref="grammar/v9.9.9"\n[veles]\nimage="0.11.14"\nttr-metadata="0.16.0"\nstrict-load=false\n')
            env = dict(os.environ, TTR_CORE_REPO=str(repo), TOOLCHAIN_TTRP_SKIP_BUILD='1')
            def bootstrap():
                return subprocess.run(['bash', str(app / 'scripts/toolchain-ttrp.sh')], env=env, text=True, capture_output=True)
            self.assertEqual(bootstrap().returncode, 0)
            dest = app / '.modeler/toolchains/ttrp'
            self.assertEqual(git(dest, 'rev-parse', 'HEAD'), git(repo, 'rev-parse', 'HEAD'))
            (repo / 'a').write_text('B')
            git(repo, 'commit', '-am', 'B')
            git(repo, 'tag', '-f', 'grammar/v9.9.9')
            other = root / 'other.git'
            subprocess.check_call(['git', 'clone', '--bare', str(repo), str(other)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            env['TTR_CORE_REPO'] = str(other)
            r = bootstrap()
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(git(dest, 'rev-parse', 'HEAD'), git(repo, 'rev-parse', 'HEAD'))
            self.assertEqual(git(dest, 'remote', 'get-url', 'origin'), str(other))
            (dest / 'stray.kt').write_text('unpinned source')
            r = bootstrap()
            self.assertNotEqual(r.returncode, 0)
            self.assertIn('stray.kt', r.stderr)

if __name__ == '__main__':
    unittest.main()
