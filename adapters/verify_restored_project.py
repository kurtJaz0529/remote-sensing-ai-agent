"""Read-only ArcPy verification after moving an archived run to a new root."""
import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--project',required=True)
parser.add_argument('--root',required=True)
args = parser.parse_args()
import arcpy
project = arcpy.mp.ArcGISProject(args.project)
root = Path(args.root).resolve()
layers = [layer for m in project.listMaps() for layer in m.listLayers() if layer.isRasterLayer]
assert layers and all(not layer.isBroken for layer in layers)
assert all(Path(layer.dataSource).resolve().is_relative_to(root) for layer in layers)
for layer in layers:
    raster = arcpy.Raster(layer.dataSource)
    assert (raster.width,raster.height,raster.bandCount)==(640,400,6)
print(json.dumps({'project_reopened':True,'raster_layer_count':len(layers),'broken_layers':0,'all_data_sources_within_restored_root':True,'scope':'native probe project only; no classification accuracy claim'}))
