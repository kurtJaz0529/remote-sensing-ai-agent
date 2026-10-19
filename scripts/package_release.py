"""Freeze a reviewable source archive with all file sizes and SHA-256 hashes."""
import json
import shutil
import zipfile
import argparse
from pathlib import Path
from datetime import datetime, timezone
from contracts import sha256

ROOT=Path(__file__).resolve().parents[1]
if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument('--demo-root',help='optional successful synthetic demo directory to include')
    parser.add_argument('--output',help='archive path; defaults beside the source directory')
    args=parser.parse_args()
    evidence=ROOT/"evidence/mock-demo"
    evidence.mkdir(parents=True,exist_ok=True)
    demo=Path(args.demo_root).resolve() if args.demo_root else None
    if demo and demo.is_dir():
        for name in ('demo_summary.json','plan.json','input_manifest.json'):
            shutil.copy2(demo/name,evidence/name)
        summary=json.loads((demo/'demo_summary.json').read_text())
        run=demo/'runtime/runs'/summary['run_id']
        shutil.copytree(run,evidence/'run',dirs_exist_ok=True)
    excluded={'__pycache__','build','dist','.git','.venv'}
    def include(path):
        parts=path.relative_to(ROOT).parts
        return not any(p in excluded or p.endswith('.egg-info') for p in parts) and path.suffix!='.pyc' and path.name!='release_manifest.json'
    files=[p for p in sorted(ROOT.rglob('*')) if p.is_file() and include(p)]
    manifest=dict(version='0.1.0.dev1',schema_revision='0.1.0',spec_revision='v1.1',created_at=datetime.now(timezone.utc).isoformat(),scope='cloud_core_development_preview; no real API/software validation',requirements='project_manifest.yaml',coverage='docs/COVERAGE.md',validation='evidence/clean-install/test_results.json',files=[dict(relative_path=p.relative_to(ROOT).as_posix(),size=p.stat().st_size,sha256=sha256(p)) for p in files])
    target=ROOT/'releases/release_manifest.json'
    target.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    files.append(target)
    archive=Path(args.output).resolve() if args.output else ROOT.parent/'rsagent-cloud-core-0.1.0-dev1.zip'
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as bundle:
        for file in files:
            bundle.write(file,arcname='rsagent-cloud-core-0.1.0-dev1/'+file.relative_to(ROOT).as_posix())
    print(json.dumps(dict(archive=str(archive),sha256=sha256(archive),size=archive.stat().st_size,file_count=len(files),manifest_sha256=sha256(target)),indent=2))
