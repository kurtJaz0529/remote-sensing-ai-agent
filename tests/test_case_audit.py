import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest


@unittest.skipUnless(importlib.util.find_spec('numpy'),'Install the science extra')
class ScientificAuditTests(unittest.TestCase):
    def test_bsq_bil_bip_decode_to_same_pixels(self):
        import numpy as np
        from adapters.raster_io import read_envi_u8
        cube=np.arange(36,dtype=np.uint8).reshape(3,4,3)
        with TemporaryDirectory() as tmp:
            path=Path(tmp)/'cube.dat'
            encodings={'bsq':cube.transpose(2,0,1),'bil':cube.transpose(0,2,1),'bip':cube}
            for mode,data in encodings.items():
                data.tofile(path)
                path.with_suffix('.hdr').write_text(f'ENVI\nsamples=4\nlines=3\nbands=3\ndata type=1\nheader offset=0\ninterleave={mode}\n',encoding='utf-8')
                np.testing.assert_array_equal(read_envi_u8(path,4,3,3),cube)
    def test_asymmetric_matrix_distinguishes_pa_ua(self):
        from adapters.case_audit import confusion_metrics
        metric=confusion_metrics([1,1,1,2,2],[1,1,2,2,0])
        self.assertEqual(metric['overall_accuracy'],.6)
        self.assertAlmostEqual(metric['producer_accuracy'][0],2/3)
        self.assertEqual(metric['user_accuracy'][0],1)
        self.assertEqual(metric['test_unclassified_rate'],.2)
        self.assertIsNone(metric['user_accuracy'][2])

    def test_invalid_and_fractional_class_codes_rejected(self):
        from adapters.case_audit import confusion_metrics
        for pred in ([7],[1.5],[-1]):
            with self.assertRaises(ValueError):confusion_metrics([1],pred)

    def test_mapping_and_coordinate_failures(self):
        from adapters.case_audit import read_samples
        with TemporaryDirectory() as tmp:
            path=Path(tmp)/'roi.csv'
            for row in ['1,水域,1,1,1','1,耕地,0,1,1','1,耕地,1.2,1,1']:
                path.write_text('class_id,class_name,column,row,region_id\n'+row,encoding='utf-8')
                with self.assertRaises(ValueError):read_samples(path,640,400,True)

    def test_buffer_and_duplicate_rejected(self):
        import numpy as np
        from adapters.case_audit import audit_samples
        train=np.array([[1,10,10,1],[1,10,10,2]])
        test=np.array([[1,100,100,0]])
        with self.assertRaisesRegex(ValueError,'Duplicate'):audit_samples(train,test,640,400)
        with self.assertRaisesRegex(ValueError,'buffer'):audit_samples(train[:1],np.array([[1,14,14,0]]),640,400)

    def test_gaussian_class_axis_and_covariance(self):
        import numpy as np
        from adapters.case_audit import gaussian_reference
        cube=np.array([[[0,0],[10,10]],[[2,2],[8,8]]],dtype=np.uint8)
        predicted=gaussian_reference(cube,np.array([[0.,0.],[10.,10.]]),np.array([np.eye(2),np.eye(2)]))
        np.testing.assert_array_equal(predicted,[[1,2],[1,2]])

    def test_separability_identical_classes_fail_guide(self):
        import numpy as np
        from adapters.case_audit import separability
        result=separability(np.zeros((2,2)),np.array([np.eye(2),np.eye(2)]))
        self.assertEqual(result['minimum_jm'],0)
        self.assertFalse(result['all_guide_jm_qualified'])
        self.assertTrue(result['pairs'][0]['guide_reselection_required'])
