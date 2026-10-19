"""Regressions found while reviewing the incoming candidate component branch."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from contracts import canonical, fingerprint
from methods.preprocess import resample_raster
from methods.spectral import compute_pca
from methods.postprocess import majority_filter
from verification.dataset_audit import audit_envi_dataset, audit_sample_split
from verification.classification_eval import evaluate_classification
from reports.report_builder import audit_report_payload, audit_report_table
from skills.loader import SkillRegistry
from scripts.probe_provider_mcp import run_probe


class IntegrationReviewTests(unittest.TestCase):
    def test_cubic_is_not_silently_bilinear(self):
        with self.assertRaisesRegex(ValueError, 'not implemented'):
            resample_raster([[[0, 10], [20, 30]]], 4, 4, 'cubic')

    def test_bilinear_upsample_replicates_border(self):
        result = resample_raster([[[0, 100], [200, 300]]], 4, 4, 'bilinear')['cube'][0]
        self.assertEqual(result[0][0], 0)
        self.assertEqual(result[-1][-1], 300)
        self.assertEqual(result[1][1], 75)

    def test_distance_alone_never_establishes_independence(self):
        result = audit_sample_split([{'x': 0, 'y': 0}], [{'x': 9, 'y': 9}])
        self.assertFalse(result['passed'])
        self.assertEqual(result['task_evaluation_kind'], 'unknown')
        with self.assertRaises(ValueError):
            audit_sample_split([], [])

    def test_header_text_is_not_calibration_or_metric_grid_proof(self):
        hdr = 'ENVI\nsamples=1\nlines=1\nbands=1\ndata type=1\ninterleave=bsq\nmap info={Geographic Lat/Lon,1,1,0,0,1,1}\nreflectance scale factor=100\n'
        result = audit_envi_dataset(hdr, claimed_area_unit='ha', claimed_calibrated_reflectance=True)
        self.assertFalse(result['passed'])
        self.assertNotIn('ha', result['allowed_area_units'])
        self.assertFalse(result['metadata']['has_verified_scale_factor'])

    def test_invalid_class_values_are_not_reclassified_as_unclassified(self):
        schema = {1: {'semantic_id': 'water'}}
        for value in (1.7, True, 'unknown-class'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                evaluate_classification([1], [value], schema)
        with self.assertRaises(ValueError):
            majority_filter([[1.2]])

    def test_pca_rejects_negative_and_duplicate_fit_coordinates(self):
        cube = [[[1, 2], [3, 4]], [[2, 3], [4, 6]]]
        for coords in ([(-1, 0), (0, 1)], [(0, 0), (0, 0)]):
            with self.assertRaises(ValueError):
                compute_pca(cube, 'train_split_only', coords)

    def test_formal_report_cannot_pass_with_an_empty_manifest(self):
        result = audit_report_payload({'sections': {}}, {})
        self.assertFalse(result['passed'])
        self.assertIn('CHK-REPORT-READY-001', [i['check_id'] for i in result['issues']])

    def test_missing_and_nonfinite_table_bindings_are_rejected(self):
        table = {'columns': [{'column_id': 'a'}], 'rows': [{'row_id': 'water', 'cells': {'a': 1}}]}
        self.assertFalse(audit_report_table(table, {})['passed'])
        table['rows'][0]['cells']['a'] = float('nan')
        self.assertFalse(audit_report_table(table, {'water': {'a': 1}})['passed'])

    def test_report_figure_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = {'artifacts': [{'artifact_id': 'f', 'relative_path': '../outside.png', 'sha256': 'a'*64}]}
            payload = {'delivery_kind': 'technical_preview', 'figures': [{'artifact_id': 'f', 'sha256': 'a'*64}]}
            self.assertFalse(audit_report_payload(payload, manifest, tmp)['passed'])

    def test_routing_never_invents_python_availability(self):
        with self.assertRaises(ValueError):
            SkillRegistry().route_backend('dataset-audit', 'PythonReference', {})
        result = SkillRegistry().route_backend('dataset-audit', 'PythonReference', {'PythonReference': {'available': True, 'version': '3.13.7'}})
        self.assertFalse(result['execution_eligible'])

    def test_provider_claim_prevents_repeated_paid_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'profile.json').write_text(canonical({}), encoding='utf-8')
            (root/'profile.sha256').write_text(fingerprint({}))
            with patch('scripts.probe_provider_mcp.Provider') as provider:
                provider.return_value.probe.return_value = {'tool_calling': 'verified'}
                first = run_probe(root, 'tool')
                self.assertEqual(run_probe(root, 'tool'), first)
                provider.return_value.probe.assert_called_once()


if __name__ == '__main__':
    unittest.main()
