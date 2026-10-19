"""Supervise only a fixed registered native child; keep uncertain jobs locked."""
import json
import os
import subprocess
import time
from contracts import fingerprint, sha256, within
from .engine import Engine
from .native import REGISTRY, command, configuration, source_path
from .store import now


def execute_native(worker, job, run_root):
    engine = Engine(worker.root)
    try:
        row, plan, manifest = engine._plan(job['project_id'], job['plan_revision'])
        config = configuration(worker.root, plan)
        source = source_path(job, manifest, row['input_root'])
    finally:
        engine.store.close()
    output = within(run_root, job['output_dir'] + '/native')
    args = command(config, job['tool'], source, output)
    env = os.environ.copy()
    if job['tool'].startswith('envi.'):
        env['ENVI_ENGINE'] = config['envi_engine']
    with within(run_root, 'events/native-' + job['step_id'] + '.log').open('ab') as log:
        child = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=log, stderr=log, env=env, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        started = time.monotonic()
        try:
            while child.poll() is None:
                cancelled = worker.db.execute('SELECT cancel FROM jobs WHERE id=?', (job['job_id'],)).fetchone()[0]
                timeout = time.monotonic() - started > job['timeout_seconds']
                if cancelled or timeout:
                    stopped = False
                    if os.name == 'nt':
                        stopped = subprocess.run(['taskkill','/PID',str(child.pid),'/T','/F'],capture_output=True,timeout=15).returncode == 0
                    else:
                        child.terminate()
                    try:
                        child.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        stopped = False
                    worker.finish(job['job_id'], 'cancelled' if cancelled and stopped else 'failed' if stopped else 'unknown', {'code':'CANCELLED' if cancelled else 'TIMEOUT'}, release=stopped)
                    return
                with worker.db:
                    worker.db.execute('UPDATE jobs SET heartbeat=? WHERE id=?', (now(), job['job_id']))
                    worker.db.execute('UPDATE locks SET heartbeat=? WHERE owner=?', (now(), job['job_id']))
                time.sleep(.1)
        except BaseException:
            # Never release locks while the child/descendants may still be executing.
            worker.finish(job['job_id'], 'unknown', {'code':'SUPERVISION_INTERRUPTED'}, release=False)
            return
    if child.returncode:
        raise ValueError('Native process failed; see local log')
    summary = json.loads((output/'summary.json').read_text(encoding='utf-8'))
    software, version, _ = REGISTRY[job['tool']]
    if not summary.get('readback_equal') or summary['software'] != software or summary['version'].split(' ')[0] != version:
        raise ValueError('Native version/readback mismatch')
    worker.authorize(job)
    artifacts = []
    for path in sorted(output.rglob('*')):
        if path.is_symlink():
            raise ValueError('Native output link rejected')
        if not path.is_file():
            continue
        kind = 'project' if path.suffix == '.aprx' else 'check' if path.name == 'summary.json' else 'data'
        artifacts.append(dict(artifact_id='ART-'+fingerprint(str(path.relative_to(run_root)))[:24],run_id=job['run_id'],step_id=job['step_id'],kind=kind,relative_path=path.relative_to(run_root).as_posix(),sha256=sha256(path),size=path.stat().st_size,verified=True))
    worker.finish(job['job_id'], 'succeeded', outputs=artifacts)
