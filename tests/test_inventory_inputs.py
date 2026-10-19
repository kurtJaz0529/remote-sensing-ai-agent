import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from contracts import validate
from scripts.inventory_inputs import build_manifest, main


class InventoryTests(unittest.TestCase):
    def test_nested_manifest_and_hash(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'nested').mkdir()
            (root / 'nested/a.hdr').write_bytes(b'original')
            result = build_manifest(root, 'user-case')
            validate('input_manifest', result)
            self.assertEqual(result['files'][0]['sha256'], hashlib.sha256(b'original').hexdigest())
            self.assertEqual(result['files'][0]['relative_path'], 'nested/a.hdr')
            self.assertEqual((root / 'nested/a.hdr').read_bytes(), b'original')

    def test_empty_rejected(self):
        with TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                build_manifest(tmp, 'case')

    def test_output_inside_inputs_rejected(self):
        with TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                main(['--root', tmp, '--dataset-id', 'case', '--output', str(Path(tmp) / 'manifest.json')])

    def test_links_rejected(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'original').write_bytes(b'abc')
            try:
                (root / 'alias').symlink_to(root / 'original')
            except OSError:
                self.skipTest('Creating symbolic links is not permitted')
            with self.assertRaises(ValueError):
                build_manifest(root, 'case')
