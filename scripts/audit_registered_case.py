"""Register an explicitly selected user folder, then audit it through local MCP."""
import argparse
import json
import socket
import subprocess
import sys
import time
from pathlib import Path
from contracts import canonical,fingerprint
from orchestrator.engine import Engine
from orchestrator.examples import mock_plan
from orchestrator.mcp_worker import McpWorker
from scripts.inventory_inputs import build_manifest


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--input-root',required=True)
    parser.add_argument('--runtime',required=True)
    args=parser.parse_args()
    runtime=Path(args.runtime).resolve();inputs=Path(args.input_root).resolve()
    if runtime.exists() or runtime.is_relative_to(inputs):raise ValueError('Choose a new runtime outside inputs')
    manifest=build_manifest(inputs,'SECONDARY-USER-FOLDER-20261019')
    engine=Engine(runtime)
    service=None
    try:
        plan=mock_plan(manifest,'SECONDARY-INPUT-AUDIT-20261019')
        plan.update(objective='Read-only user-specified second-folder input audit; no classification or held-out accuracy',evaluation_kind='unknown')
        plan['method_plan'][0].update(tool='local.registered_input_audit',parameters={},implementation_kind='reimplementation')
        engine.save_plan(plan,manifest,inputs)
        approval=engine.approve(plan['task_id'],1,'user-specified-second-folder')
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        log=(runtime/'mcp-audit.log').open('wb')
        service=subprocess.Popen([sys.executable,'-m','orchestrator.mcp_server','--root',str(runtime),'--http','--port',str(port)],stdin=subprocess.DEVNULL,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0)
        deadline=time.monotonic()+20
        while True:
            try:
                with socket.create_connection(('127.0.0.1',port),timeout=.2):break
            except OSError:
                if time.monotonic()>deadline:raise RuntimeError('MCP audit service unavailable')
                time.sleep(.1)
        result=McpWorker(f'http://127.0.0.1:{port}/mcp',timeout=60).request('registered_input_audit',dict(task_id=plan['task_id'],revision=1,approval_id=approval))
        (runtime/'input-audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        (runtime/'input-manifest.json').write_text(canonical(manifest),encoding='utf-8')
        public=dict(registered_files=result['registered_files'],png_count=result['png_count'],invalid_png_count=result['invalid_png_count'],valid_structure_only_count=sum(p['status']=='structure_verified' for p in result['pngs']),one_byte_png_count=sum(p['size']==1 for p in result['pngs']),known_canon_city_duplicate_count=len(result['repeated_canon_city_image_paths']),input_manifest_hash=fingerprint(manifest),scope=result['scope'],warnings=result['warnings'])
        (runtime/'public-summary.json').write_text(json.dumps(public,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(public,ensure_ascii=False))
    finally:
        engine.store.close()
        if service is not None:service.terminate();service.wait(timeout=15);log.close()


if __name__=='__main__':main()
