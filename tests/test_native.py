import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from contracts import fingerprint, validate
from orchestrator.native import REGISTRY, command, configuration, source_path, tool, validate_case_scope


class NativeBoundaryTests(unittest.TestCase):
    def test_reused_labels_cannot_be_called_independent(self):
        for kind in ['independent','reference_agreement','unknown']:
            with self.assertRaises(ValueError):validate_case_scope({'tool':'envi.classification_case'},{'evaluation_kind':kind})
        validate_case_scope({'tool':'envi.classification_case'},{'evaluation_kind':'diagnostic'})
    def test_closed_tools_and_parameter_schemas(self):
        for name in REGISTRY:
            validate('tool', tool(name))
            self.assertFalse(tool(name)['parameters']['additionalProperties'])
        with self.assertRaises(KeyError): tool('arbitrary.script')

    def test_config_not_frozen_rejected(self):
        with TemporaryDirectory() as tmp:
            (Path(tmp)/'native-config.json').write_text('{}',encoding='utf-8')
            with self.assertRaises(ValueError): configuration(tmp,{'frozen_versions':{}})

    def test_changed_adapter_rejected(self):
        with TemporaryDirectory() as tmp:
            config = {'adapter_hashes':{}}
            (Path(tmp)/'native-config.json').write_text(json.dumps(config),encoding='utf-8')
            with self.assertRaises(ValueError): configuration(tmp,{'frozen_versions':{'native_config_sha256':fingerprint(config)}})

    def test_unregistered_input_rejected(self):
        with TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError): source_path({'parameters':{'source_relative':'../outside.img'}},{'files':[]},tmp)

    def test_matlab_path_quotes_are_data(self):
        args = command({'matlab_executable':'matlab.exe'},'matlab.mean_probe',Path("a'b.img"),Path("x'y"))
        self.assertIn("a''b.img",args[-1])
        self.assertIn("x''y",args[-1])
        self.assertEqual(args[1],'-batch')
