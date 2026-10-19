"""ArcGIS Pro dedicated-Python probe, fixed input shape and registered source hash."""
import argparse
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--template', required=True)
    args = parser.parse_args()
    source, output = Path(args.input).resolve(), Path(args.output).resolve()
    assert not output.exists() and not output.is_relative_to(source.parent)
    expected = '121f1268c855ace06edd642ff191ff04da74499df3ff70c69c8b8bcee11345e5'
    assert hashlib.sha256(source.read_bytes()).hexdigest() == expected
    import arcpy
    output.mkdir(parents=True)
    arcpy.env.overwriteOutput = False
    raster = arcpy.Raster(str(source))
    assert (raster.width, raster.height, raster.bandCount) == (640,400,6)
    copied = output / 'copy.tif'
    arcpy.management.CopyRaster(raster, str(copied))
    reread = arcpy.Raster(str(copied))
    import numpy as np
    equal = bool(np.array_equal(arcpy.RasterToNumPyArray(raster), arcpy.RasterToNumPyArray(reread)))
    assert equal
    project = arcpy.mp.ArcGISProject(args.template)
    map_obj = project.createMap('Registered raster probe', 'MAP')
    map_obj.addDataFromPath(str(copied))
    project.saveACopy(str(output / 'probe.aprx'))
    del project
    reopened = arcpy.mp.ArcGISProject(str(output / 'probe.aprx'))
    broken = [layer.name for m in reopened.listMaps() for layer in m.listLayers() if layer.isBroken]
    assert not broken
    result = {'software':'ArcGIS Pro','version':arcpy.GetInstallInfo()['Version'],'readback_equal':equal,'shape':[reread.height,reread.width,reread.bandCount],'broken_layers':broken,'spatial_reference':raster.spatialReference.name,'scope':'native raster copy and project reopen; no classification or accuracy claim'}
    (output / 'summary.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))
    assert hashlib.sha256(source.read_bytes()).hexdigest() == expected


if __name__ == '__main__':
    main()
