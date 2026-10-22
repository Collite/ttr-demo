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

    def test_failed_build_invalidates_stamp_and_next_run_rebuilds_then_skips(self):
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
            a = git(repo, 'rev-parse', 'HEAD')
            app = root / 'hartland'
            (app / 'scripts').mkdir(parents=True)
            shutil.copy2(SCRIPT, app / 'scripts/toolchain-ttrp.sh')
            shutil.copy2(READER, app / 'scripts/toolchain-lock.py')
            lock = app / 'toolchain.lock'
            def pin(ref):
                lock.write_text(f'[ttr-core]\nref="grammar/v0.16.1"\n[ttrp]\nref="{ref}"\nversion="9.9.9-au.1"\n[veles]\nimage="0.11.14"\nttr-metadata="0.16.0"\nstrict-load=false\n')
            hook = "echo build >> .git/build-count; " + \
                "mkdir -p packages/kotlin/ttrp-cli/build/install/ttrp-cli/bin; " + \
                "git rev-parse HEAD > packages/kotlin/ttrp-cli/build/install/ttrp-cli/bin/ttrp-cli"
            # Match the real compiler checkout: installDist outputs are ignored.
            (repo / '.gitignore').write_text('packages/\n')
            git(repo, 'add', '.gitignore')
            git(repo, 'commit', '-m', 'ignore build outputs')
            a = git(repo, 'rev-parse', 'HEAD')
            env = dict(os.environ, TTR_CORE_REPO=str(repo), TOOLCHAIN_TTRP_BUILD_CMD=hook)
            env.pop('TOOLCHAIN_TTRP_SKIP_BUILD', None)
            def bootstrap():
                return subprocess.run(['bash', str(app / 'scripts/toolchain-ttrp.sh')], env=env, text=True, capture_output=True)
            pin(a)
            first = bootstrap()
            self.assertEqual(first.returncode, 0, first.stderr)
            dest = app / '.modeler/toolchains/ttrp'
            stamp = dest / '.git/ttrp-build'
            count = dest / '.git/build-count'
            self.assertEqual(stamp.read_text().strip(), f'{a} 9.9.9-au.1')
            (repo / 'a').write_text('B')
            git(repo, 'commit', '-am', 'B')
            b = git(repo, 'rev-parse', 'HEAD')
            pin(b)  # Same version deliberately reproduces H-m5.
            env['TOOLCHAIN_TTRP_BUILD_CMD'] = 'echo build >> .git/build-count; false'
            self.assertNotEqual(bootstrap().returncode, 0)
            self.assertFalse(stamp.exists())
            self.assertEqual(git(dest, 'rev-parse', 'HEAD'), b)
            env['TOOLCHAIN_TTRP_BUILD_CMD'] = hook
            rebuilt = bootstrap()
            self.assertEqual(rebuilt.returncode, 0, rebuilt.stderr)
            self.assertEqual(stamp.read_text().strip(), f'{b} 9.9.9-au.1')
            self.assertEqual(len(count.read_text().splitlines()), 3)
            self.assertEqual(bootstrap().returncode, 0)
            self.assertEqual(len(count.read_text().splitlines()), 3, 'same successful build must skip')

if __name__ == '__main__':
    unittest.main()
