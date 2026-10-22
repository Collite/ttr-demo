import importlib.util
from pathlib import Path
import tempfile
import unittest

MODULE = Path(__file__).with_name('toolchain-lock.py')


class ToolchainLockTest(unittest.TestCase):
    def test_recipe_pin_is_independent_of_model_gate(self):
        spec = importlib.util.spec_from_file_location('toolchain_lock', MODULE)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as tmp:
            lock = Path(tmp) / 'toolchain.lock'
            lock.write_text('[ttr-core]\nref = "grammar/v0.16.1"\n[ttrp]\nref = "grammar/v0.17.3"\n')
            self.assertEqual(module.read_ref('ttrp', lock), 'grammar/v0.17.3')
            self.assertEqual(module.read_ref('ttr-core', lock), 'grammar/v0.16.1')
            self.assertEqual(module.read_version('ttrp', lock), '0.17.3')
            lock.write_text('[ttrp]\nref = "' + 'a' * 40 + '"\nversion = "0.17.3-au.1"\n')
            self.assertEqual(module.read_ref('ttrp', lock), 'a' * 40)
            self.assertEqual(module.read_version('ttrp', lock), '0.17.3-au.1')
            with self.assertRaises(ValueError):
                module.read_ref('missing', lock)


if __name__ == '__main__':
    unittest.main()
