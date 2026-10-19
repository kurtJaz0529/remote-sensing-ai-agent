"""Native pixel crop of the user-supplied second RGB case, no semantic claims."""
import argparse
import hashlib
import json
import re
from pathlib import Path
import numpy as np
from PIL import Image
from raster_io import read_envi_u8

SOURCE_HASH='47ab7191fa82b78795269082f1de33fd38cf6e20679dc90ed3e3a87c57f49688'


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--input',required=True);parser.add_argument('--output',required=True);args=parser.parse_args()
    source,out=Path(args.input),Path(args.output)
    if hashlib.sha256(source.read_bytes()).hexdigest()!=SOURCE_HASH or out.exists():raise ValueError('Registered second case mismatch or output exists')
    with Image.open(source) as image:
        if image.mode!='RGB' or image.size!=(1792,1536):raise ValueError('Expected original RGB case')
        expected=np.asarray(image)[:64,:64,:].copy()
    out.mkdir(parents=True)
    from envipyengine import Engine
    task=Engine('ENVI').task('SubsetRaster')
    task.execute(dict(INPUT_RASTER=dict(factory='URLRaster',url=str(source)),SUB_RECT=[0,0,63,63],BANDS=[0,1,2],OUTPUT_RASTER_URI=str(out/'rgb-subset.dat')))
    actual=read_envi_u8(out/'rgb-subset.dat',64,64,3)
    if not np.array_equal(actual,expected):raise ValueError('RGB source/native pixel mismatch')
    if hashlib.sha256(source.read_bytes()).hexdigest()!=SOURCE_HASH:raise ValueError('Source changed')
    result=dict(software='ENVI',version='5.6',readback_equal=True,shape=[64,64,3],pixel_differences=0,source_sha256=SOURCE_HASH,scope='second user RGB image input/crop validation only; no independent semantic accuracy',crs='unknown',physical_scale='unknown',checks=[dict(check_id=name,passed=True) for name in ['native-readback','rgb-pixel-equality']])
    (out/'summary.json').write_text(json.dumps(result,indent=2),encoding='utf-8')


if __name__=='__main__':main()
