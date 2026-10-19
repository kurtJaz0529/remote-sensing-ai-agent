"""Run the user-authorized fixed-case backend verification through the real worker."""
import argparse
import json
import sys
import time
import socket
import subprocess
from pathlib import Path
from contracts import VERSION, canonical, fingerprint, sha256, validate
from orchestrator.engine import Engine
from orchestrator.examples import mock_plan
from orchestrator.intake import inventory
from orchestrator.native import REGISTRY, tool
from orchestrator.store import now
from orchestrator.mcp_worker import McpWorker


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime',required=True)
    args = parser.parse_args()
    runtime = Path(args.runtime).resolve()
    if runtime.exists():
        raise ValueError('Use a fresh runtime; existing jobs must be resumed explicitly')
    runtime.mkdir(parents=True)
    root = Path(__file__).resolve().parents[1]
    inputs = Path('F:/mtal/实验文件/图像分类/分类数据')
    manifest = inventory(inputs, 'CANON-CITY-REGISTERED')
    config = dict(envi_python='D:/agent/codex/envi-mcp-server/.venv/Scripts/python.exe',envi_engine='C:/Program Files/Harris/ENVI56/IDL88/bin/bin.x86_64/taskengine.exe',arcgis_python='F:/ArcGIS/Pro/bin/Python/envs/arcgispro-py3/python.exe',matlab_executable='F:/mtal/R2022a/bin/matlab.exe',arcgis_template='F:/ArcGIS/Pro/Resources/ArcToolBox/Services/routingservices/data/Blank.aprx')
    config['arcgis_template_sha256'] = sha256(config['arcgis_template'])
    config['adapter_hashes'] = {filename:sha256(root/'adapters'/filename) for _,_,filename in REGISTRY.values()}
    (runtime/'native-config.json').write_text(canonical(config),encoding='utf-8')
    # These IDs refer to actual direct software probes documented in the preceding batch.
    capabilities = dict(schema_revision=VERSION,environment_id='WINDOWS-LOCAL',verified_at=now(),tools=[dict(tool=tool(name),status='available',verification_run_ids=['native-probes-20261019-'+name.split('.')[0]],limitations=['Only the registered fixed-case probe; not a general classification tool']) for name in REGISTRY])
    validate('capabilities',capabilities)
    (runtime/'capabilities.json').write_text(canonical(capabilities),encoding='utf-8')
    plan = mock_plan(manifest, 'NATIVE-INTEGRATION-20261019')
    plan.update(objective='User-authorized three-software native integration verification',assumptions=['Fixed registered case only; no CRS, reflectance, or classification accuracy claim'],requirements=[dict(requirement_id='BACKEND-READBACK',source_locator='User request: 继续完成后上交',description='Each native backend must save and reopen actual data',required_artifacts=['data','project','check'],acceptance_checks=['native-readback'],confidence=1.0)],required_deliverables=['data','project','check'])
    plan['frozen_versions'].update(capabilities_sha256=fingerprint(capabilities),native_config_sha256=fingerprint(config))
    plan['method_plan'] = [dict(step_id='S'+str(i),depends_on=[] if i==1 else ['S'+str(i-1)],tool=name,tool_version=REGISTRY[name][1],parameters={'source_relative':'can_tmr.img'},dataset_ids=[manifest['dataset_id']],output_dir='artifacts/S'+str(i),timeout_seconds=180,implementation_kind='native',required_kinds=['data','check']+(['project'] if name.startswith('arcgis.') else [])) for i,name in enumerate(REGISTRY,1)]
    engine = Engine(runtime)
    try:
        engine.save_plan(plan,manifest,inputs)
        approval = engine.approve(plan['task_id'],1,'user-request-continue-and-submit')
        run = engine.create_run(plan['task_id'],1,approval,'real')
        (runtime/'integration-run.json').write_text(canonical(dict(run_id=run,approval_id=approval,plan_hash=fingerprint(plan),input_manifest_hash=fingerprint(manifest))),encoding='utf-8')
        with socket.socket() as listener:
            listener.bind(('127.0.0.1',0)); port=listener.getsockname()[1]
        service_log=(runtime/'mcp-service.log').open('ab')
        service=subprocess.Popen([sys.executable,'-m','orchestrator.mcp_server','--root',str(runtime),'--http','--port',str(port)],stdin=subprocess.DEVNULL,stdout=service_log,stderr=service_log,creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0)
        (runtime/'mcp-endpoint.json').write_text(canonical({'url':f'http://127.0.0.1:{port}/mcp','pid':service.pid}),encoding='utf-8')
        startup=time.monotonic()+20
        while True:
            try:
                with socket.create_connection(('127.0.0.1',port),timeout=.2):break
            except OSError:
                if time.monotonic()>startup:raise RuntimeError('MCP service startup failed; inspect local log')
                time.sleep(.1)
        client = McpWorker(f'http://127.0.0.1:{port}/mcp')
        deadline = time.monotonic()+600
        while True:
            status = engine.execute(run,client)
            print(json.dumps({'run_id':run,'state':status['state']}),flush=True)
            if status['state'] not in ('Paused','Executing','Preflight') or time.monotonic()>deadline:
                break
            time.sleep(2)
        output = dict(run_id=run,state=status['state'],plan_sha256=fingerprint(plan),input_manifest_hash=fingerprint(manifest),originals_unchanged=inventory(inputs,manifest['dataset_id'])==manifest,steps=[])
        for row in engine.store.db.execute('SELECT id,job,state,result FROM steps WHERE run=?',(run,)):
            result = json.loads(row['result']) if row['result'] else {}
            output['steps'].append(dict(step_id=row['id'],job_id=row['job'],state=row['state'],software=result.get('software'),checks=result.get('checks'),outputs=result.get('outputs'),error=result.get('error')))
        (runtime/'integration-summary.json').write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(output,ensure_ascii=False),flush=True)
        if status['state']!='Completed' or not output['originals_unchanged']:
            raise SystemExit(1)
    finally:
        engine.store.close()
        # Server has no lifetime dependency on each MCP client session. Keep it
        # running if work is uncertain; a later client can query the same job.
        if 'service' in locals() and 'status' in locals() and status['state']=='Completed':
            service.terminate();service.wait(timeout=15)
        if 'service_log' in locals():service_log.close()


if __name__ == '__main__':
    main()
