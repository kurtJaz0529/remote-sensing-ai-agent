import struct
import zlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from orchestrator.image_audit import png_structure,registered_image_audit
from orchestrator.engine import Engine
from orchestrator.examples import mock_plan
from orchestrator.intake import inventory


def chunk(kind,data):
    return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)


class ImageAuditTests(unittest.TestCase):
    def test_one_byte_png_and_crc_failure(self):
        with TemporaryDirectory() as tmp:
            p=Path(tmp)/'a.png';p.write_bytes(b'x')
            self.assertEqual(png_structure(p)['status'],'invalid')
            data=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',1,1,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(b'\x00\x00\x00\x00'))+chunk(b'IEND',b'')
            p.write_bytes(data);self.assertEqual(png_structure(p)['status'],'structure_verified')
            p.write_bytes(data[:-1]+b'x');self.assertEqual(png_structure(p)['status'],'invalid')

    def test_registered_audit_requires_matching_confirmation(self):
        with TemporaryDirectory() as tmp:
            inputs=Path(tmp)/'inputs';inputs.mkdir();(inputs/'broken.png').write_bytes(b'x')
            runtime=Path(tmp)/'runtime';engine=Engine(runtime)
            try:
                manifest=inventory(inputs,'USER-CASE');plan=mock_plan(manifest)
                plan['method_plan'][0].update(tool='local.registered_input_audit',parameters={})
                engine.save_plan(plan,manifest,inputs);approval=engine.approve(plan['task_id'],1,'test-fixture')
                with self.assertRaises(ValueError):registered_image_audit(runtime,plan['task_id'],1,'wrong')
                result=registered_image_audit(runtime,plan['task_id'],1,approval)
                self.assertEqual(result['invalid_png_count'],1)
                (inputs/'broken.png').write_bytes(b'changed')
                with self.assertRaises(ValueError):registered_image_audit(runtime,plan['task_id'],1,approval)
            finally:engine.store.close()
