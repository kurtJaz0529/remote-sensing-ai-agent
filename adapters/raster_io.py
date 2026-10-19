"""Header-driven ENVI uint8 decoder; never infer interleave from filename."""
import re
from pathlib import Path
import numpy as np


def read_envi_u8(path,width,height,bands):
    path=Path(path);text=path.with_suffix('.hdr').read_text(encoding='utf-8')
    def value(key):
        match=re.search(r'^'+key+r'\s*=\s*([^\r\n]+)',text,re.M|re.I)
        if not match:raise ValueError('Missing ENVI header field '+key)
        return match.group(1).strip().lower()
    if [int(value(k)) for k in ['samples','lines','bands','data type']]!=[width,height,bands,1]:
        raise ValueError('Unexpected raster dimensions or data type')
    offset=int(value('header offset'))
    if offset<0:raise ValueError('Negative header offset')
    mode=value('interleave')
    raw=np.fromfile(path,dtype=np.uint8,offset=offset)
    if raw.size!=width*height*bands:raise ValueError('Raster byte count mismatch')
    if mode=='bsq':return raw.reshape(bands,height,width).transpose(1,2,0)
    if mode=='bil':return raw.reshape(height,bands,width).transpose(0,2,1)
    if mode=='bip':return raw.reshape(height,width,bands)
    raise ValueError('Unsupported ENVI interleave')
