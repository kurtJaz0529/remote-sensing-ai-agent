"""Independent byte-level checks and public summaries, without publishing imagery."""
import json
import re
from pathlib import Path
from contracts import sha256


def main():
    root = Path(__file__).resolve().parents[1]
    local = root / 'local-data/native-probes-20261019'
    source = Path('F:/mtal/实验文件/图像分类/分类数据/can_tmr.img')
    raw = source.read_bytes()
    assert sha256(source) == '121f1268c855ace06edd642ff191ff04da74499df3ff70c69c8b8bcee11345e5'
    expected = b''.join(raw[b*640*400+r*640:b*640*400+r*640+16] for b in range(6) for r in range(16))
    hdr = (local / 'envi-subset.hdr').read_text()
    for key, value in [('samples','16'),('lines','16'),('bands','6'),('interleave','bsq'),('data type','1'),('header offset','0')]:
        assert re.search(r'^' + key + r'\s*=\s*' + value + r'\s*$', hdr, re.M | re.I)
    assert (local / 'envi-subset.dat').read_bytes() == expected
    software = {name:json.loads((local / name / 'summary.json').read_text()) for name in ('matlab','arcpy')}
    outputs = [dict(relative_path=p.relative_to(local).as_posix(),sha256=sha256(p),size=p.stat().st_size) for p in sorted(local.rglob('*')) if p.is_file()]
    result = dict(date='2026-10-19',source_sha256=sha256(source),software=software,envi=dict(task='SubsetRaster',parameters=dict(SUB_RECT=[0,0,15,15],BANDS=list(range(6))),shape=[16,16,6],bytes_equal_to_source_subset=True),outputs=outputs,limitations=['Native probes executed directly through MCP or dedicated software Python, not unified worker handlers.', 'No formal experiment, screenshots, classification accuracy, or independent acceptance is claimed.', 'Source has unknown CRS and scale; no physical areas assigned.'])
    output = root / 'evidence/local-worker/native-probe-summary.json'
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Native probes verified; source unchanged; public summary excludes raster contents.')


if __name__ == '__main__':
    main()
