"""Publish only selected original input hashes, keeping the full manifest private."""
import json
from pathlib import Path
from contracts import validate, sha256

def main():
    root = Path(__file__).resolve().parents[1]
    manifest_path = root / 'local-data/classification-archive.manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    validate('input_manifest', manifest)
    selected = [f for f in manifest['files'] if f['relative_path'].startswith('图像分类/')]
    expected = {'can_tmr.img': '121f1268c855ace06edd642ff191ff04da74499df3ff70c69c8b8bcee11345e5', 'new_test_sample1.roi': 'ab0477054c521b7729e203075942b66fb0f4ae411ee2ee293c97f1b5c7d3e727'}
    matches = {name: any(Path(f['relative_path']).name == name and f['sha256'] == digest for f in selected) for name, digest in expected.items()}
    report = dict(observed_date='2026-10-19', source_notion='https://www.notion.so/3fcc5fcc8d9381028310efb0dae1ba37', archive_file_count=len(manifest['files']), manifest_sha256=sha256(manifest_path), selected_original_files=selected, matches_notion=matches, scientific_limits=['No map reference: pixel coordinates and pixel-squared area only.', 'Unknown scale/offset: no physical reflectance claim.', 'Historical test points are diagnostic, not an untouched holdout.'], missing=['New independent T30 holdout', 'T07 acceptance matrix and T17 sample audit'])
    target = root / 'evidence/local-foundation/input-inventory-summary.json'
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'file_count': len(manifest['files']), 'matches': matches}))

if __name__ == '__main__':
    main()
