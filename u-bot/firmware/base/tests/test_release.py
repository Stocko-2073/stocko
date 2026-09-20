import importlib.util
from pathlib import Path
import struct
import unittest

path = Path(__file__).resolve().parents[1] / 'tools/release_manifest.py'
spec = importlib.util.spec_from_file_location('release', path)
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class ReleaseTests(unittest.TestCase):
    def image(self):
        data = bytearray(512)
        data[0] = 0xe9
        struct.pack_into('<H', data, 12, 9)
        struct.pack_into('<I', data, 32, 0xabcd5432)
        data[48:53] = b'1.2.3'
        data[80:89] = b'ubot_base'
        return data

    def test_identity(self):
        m = release.inspect_image(self.image())
        self.assertEqual(m['version'], '1.2.3')
        self.assertEqual(m['project'], 'ubot_base')
        self.assertEqual(m['size'], 512)
        self.assertEqual(len(m['sha256']), 64)

    def test_wrong_target_project_and_truncation(self):
        for offset in [0, 12, 32, 80]:
            data = self.image()
            data[offset] = 0
            with self.assertRaises(ValueError):
                release.inspect_image(data)
        with self.assertRaises(ValueError):
            release.inspect_image(self.image()[:200])

    def test_content_hash_changes(self):
        a = self.image()
        b = bytearray(a)
        b[-1] = 1
        self.assertNotEqual(release.inspect_image(a)['sha256'], release.inspect_image(b)['sha256'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
