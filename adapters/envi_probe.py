"""Fixed ENVI native subset with independent byte-level verification."""
import argparse
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    source, out = Path(args.input).resolve(), Path(args.output).resolve()
    raw = source.read_bytes()
    if hashlib.sha256(raw).hexdigest() != '121f1268c855ace06edd642ff191ff04da74499df3ff70c69c8b8bcee11345e5' or out.exists() or out.is_relative_to(source.parent):
        raise ValueError('Unregistered input or unsafe output')
    from envipyengine import Engine
    engine = Engine('ENVI')
    if 'SubsetRaster' not in engine.tasks():
        raise ValueError('Native task unavailable')
    out.mkdir(parents=True)
    task = engine.task('SubsetRaster')
    task.execute(dict(INPUT_RASTER=dict(url=str(source),factory='URLRaster'),SUB_RECT=[0,0,15,15],BANDS=list(range(6)),OUTPUT_RASTER_URI=str(out/'subset.dat')))
    expected = b''.join(raw[b*640*400+r*640:b*640*400+r*640+16] for b in range(6) for r in range(16))
    if (out/'subset.dat').read_bytes() != expected or not (out/'subset.hdr').is_file():
        raise ValueError('Native output verification failed')
    result = dict(software='ENVI',version='5.6',task='SubsetRaster',readback_equal=True,shape=[16,16,6],scope='native fixed-case subset; pixel coordinates only')
    (out/'summary.json').write_text(json.dumps(result),encoding='utf-8')
    if source.read_bytes() != raw:
        raise ValueError('Input changed')


if __name__ == '__main__':
    main()
