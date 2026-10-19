import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile
from contracts import sha256
from orchestrator.archive import restore


class ArchiveTests(unittest.TestCase):
    def test_wrong_digest_rejected_without_writes(self):
        with TemporaryDirectory() as tmp:
            archive=Path(tmp)/'a.zip';archive.write_bytes(b'not zip')
            target=Path(tmp)/'out'
            with self.assertRaises(ValueError):restore(archive,target,'0'*64)
            self.assertFalse(target.exists())

    def test_traversal_rejected_before_extraction(self):
        with TemporaryDirectory() as tmp:
            archive=Path(tmp)/'a.zip'
            with ZipFile(archive,'w') as out:
                out.writestr('manifest.json','{}');out.writestr('../escape','bad')
            target=Path(tmp)/'out'
            with self.assertRaises(ValueError):restore(archive,target,sha256(archive))
            self.assertFalse(target.exists())
            self.assertFalse((Path(tmp)/'escape').exists())

    def test_existing_target_never_overwritten(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);archive=root/'a.zip';archive.write_bytes(b'x')
            target=root/'existing';target.mkdir();(target/'keep').write_bytes(b'original')
            with self.assertRaises(ValueError):restore(archive,target,sha256(archive))
            self.assertEqual((target/'keep').read_bytes(),b'original')
