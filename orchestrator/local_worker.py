"""Durable local process boundary. Only explicitly registered handlers may execute."""
import argparse
import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from contracts import VERSION, canonical, fingerprint, sha256, validate, within
from .engine import Engine
from .store import now


class LocalWorker:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.root / 'local_jobs.sqlite', timeout=15)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, key TEXT UNIQUE, body TEXT,
          result TEXT, cancel INTEGER DEFAULT 0, pid INTEGER, heartbeat TEXT);
        CREATE TABLE IF NOT EXISTS locks(resource TEXT PRIMARY KEY, owner TEXT, pid INTEGER, heartbeat TEXT);
        ''')

    def close(self):
        self.db.close()

    def authorize(self, job):
        validate('job', job)
        engine = Engine(self.root)
        try:
            run = engine.store.run(job['run_id'])
            if run['state'] in ('Completed', 'Failed', 'Cancelled'):
                raise ValueError('run is terminal')
            row, plan, manifest = engine._plan(run['task'], run['revision'])
            approval = engine.store.db.execute('SELECT * FROM approvals WHERE id=?', (job['approval_id'],)).fetchone()
            if approval is None or (approval['task'], approval['revision'], approval['plan_hash'], approval['manifest_hash']) != (run['task'], run['revision'], row['hash'], fingerprint(manifest)) or run['approval'] != approval['id']:
                raise ValueError('untrusted confirmation')
            engine._preflight(run)
            intent = engine.store.db.execute('SELECT body FROM steps WHERE run=? AND id=?', (job['run_id'], job['step_id'])).fetchone()
            if intent is None or intent['body'] != canonical(job):
                raise ValueError('job differs from durable dispatch intent')
            step = next(s for s in plan['method_plan'] if s['step_id'] == job['step_id'])
            expected = fingerprint(dict(run=job['run_id'], plan=fingerprint(plan), step=step))
            if job['idempotency_key'] != expected or job['project_id'] != run['task'] or job['plan_revision'] != run['revision']:
                raise ValueError('job identity mismatch')
            if job['output_dir'] != 'artifacts/' + job['step_id']:
                raise ValueError('output must be the registered step directory')
            if run['mode'] == 'real':
                from .native import REGISTRY, configuration, source_path, validate_case_scope
                if job['tool'] not in REGISTRY or job['implementation_kind'] != 'native' or job['tool_version'] != REGISTRY[job['tool']][1]:
                    raise ValueError('no verified native handler')
                configuration(self.root, plan)
                validate_case_scope(job,plan)
                source_path(job, manifest, row['input_root'])
            elif job['tool'] != 'mock.echo' or job['tool_version'] != VERSION or job['implementation_kind'] != 'mock':
                raise ValueError('no verified mock handler')
            return within(self.root, 'runs/' + job['run_id'])
        finally:
            engine.store.close()

    @staticmethod
    def initial_result(job):
        from .native import REGISTRY
        software = REGISTRY[job['tool']][:2] if job['tool'] in REGISTRY else ('MOCK ONLY', VERSION)
        return dict(schema_revision=VERSION, job_id=job['job_id'], run_id=job['run_id'], step_id=job['step_id'], status='queued', software={'name': software[0], 'version': software[1]}, implementation_kind=job['implementation_kind'], effective_parameters=job['parameters'], input_manifest_hash=job['input_manifest_hash'], outputs=[], checks=[], warnings=['Fixed-case verification only; no classification accuracy claim'], error=None)

    def submit(self, job):
        validate('job', job)
        self.db.execute('BEGIN IMMEDIATE')
        try:
            old = self.db.execute('SELECT body,result FROM jobs WHERE id=? OR key=?', (job['job_id'], job['idempotency_key'])).fetchone()
            if old:
                if old['body'] != canonical(job):
                    raise ValueError('idempotency collision')
                self.db.commit()
                return json.loads(old['result'])
            run_root = self.authorize(job)
            result = self.initial_result(job)
            self.db.execute('INSERT INTO jobs(id,key,body,result,heartbeat) VALUES(?,?,?,?,?)', (job['job_id'], job['idempotency_key'], canonical(job), canonical(result), now()))
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise
        log = within(run_root, 'events/local-worker.log')
        try:
            with log.open('ab') as stream:
                flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
                subprocess.Popen([sys.executable, '-m', 'orchestrator.local_worker', '--root', str(self.root), '--execute', job['job_id']], stdin=subprocess.DEVNULL, stdout=stream, stderr=stream, close_fds=True, creationflags=flags, start_new_session=os.name != 'nt')
        except OSError:
            self.finish(job['job_id'], 'failed', {'code': 'PROCESS_START_FAILED'})
        return self.status(job['job_id'])

    def status(self, job_id):
        row = self.db.execute('SELECT result FROM jobs WHERE id=?', (job_id,)).fetchone()
        if row is None:
            raise ValueError('unknown job; reconcile manually, never resubmit automatically')
        return validate('result', json.loads(row['result']))

    def cancel(self, job_id):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            result = self.status(job_id)
            if result['status'] in ('queued', 'running'):
                self.db.execute('UPDATE jobs SET cancel=1 WHERE id=?', (job_id,))
                if result['status'] == 'queued':
                    result['status'] = 'cancelled'
                    self.db.execute('UPDATE jobs SET result=? WHERE id=?', (canonical(result), job_id))
            self.db.commit()
            return result
        except BaseException:
            self.db.rollback()
            raise

    def finish(self, job_id, status, error=None, outputs=None, release=True, checks=None):
        with self.db:
            result = self.status(job_id)
            check = 'mock-nonempty' if result['implementation_kind'] == 'mock' else 'native-readback'
            result.update(status=status, error=error, outputs=outputs or [], checks=(checks if checks is not None else [{'check_id': check, 'passed': True}]) if status == 'succeeded' else [])
            validate('result', result)
            self.db.execute('UPDATE jobs SET result=?,heartbeat=? WHERE id=?', (canonical(result), now(), job_id))
            if release:
                self.db.execute('DELETE FROM locks WHERE owner=?', (job_id,))

    def execute(self, job_id):
        self.db.execute('BEGIN IMMEDIATE')
        row = self.db.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()
        if row is None or json.loads(row['result'])['status'] != 'queued':
            self.db.rollback()
            return
        job = json.loads(row['body'])
        try:
            run_root = self.authorize(job)
            software = job['tool'].split('.')[0] if job['implementation_kind'] == 'native' else 'mock'
            for resource in ('software:' + software, 'project:' + job['project_id']):
                self.db.execute('INSERT INTO locks VALUES(?,?,?,?)', (resource, job_id, os.getpid(), now()))
            result = json.loads(row['result']); result['status'] = 'running'
            self.db.execute('UPDATE jobs SET result=?,pid=?,heartbeat=? WHERE id=?', (canonical(result), os.getpid(), now(), job_id))
            self.db.commit()
        except Exception as exc:
            self.db.rollback()
            self.finish(job_id, 'failed', {'code': 'PREFLIGHT_OR_LOCK_FAILED', 'type': type(exc).__name__})
            return
        try:
            if job['implementation_kind'] == 'native':
                from .native_process import execute_native
                execute_native(self, job, run_root)
                return
            started = time.monotonic()
            # Small cooperative execution window also permits cancellation tests.
            while time.monotonic() - started < 0.2:
                if self.db.execute('SELECT cancel FROM jobs WHERE id=?', (job_id,)).fetchone()[0]:
                    self.finish(job_id, 'cancelled'); return
                if time.monotonic() - started > job['timeout_seconds']:
                    self.finish(job_id, 'failed', {'code': 'TIMEOUT'}); return
                with self.db:
                    self.db.execute('UPDATE jobs SET heartbeat=? WHERE id=?', (now(), job_id))
                    self.db.execute('UPDATE locks SET heartbeat=? WHERE owner=?', (now(), job_id))
                time.sleep(0.02)
            path = within(run_root, job['output_dir'] + '/mock.txt')
            with path.open('x', encoding='utf-8') as stream:
                stream.write('MOCK ONLY: ' + job['parameters']['message'])
            artifact = dict(artifact_id='ART-' + job['idempotency_key'][:24], run_id=job['run_id'], step_id=job['step_id'], kind='data', relative_path=path.relative_to(run_root).as_posix(), sha256=sha256(path), size=path.stat().st_size, verified=True)
            self.finish(job_id, 'succeeded', outputs=[artifact])
        except Exception as exc:
            self.finish(job_id, 'failed', {'code': 'HANDLER_FAILED', 'type': type(exc).__name__})


def main():
    # JSON-RPC is UTF-8 regardless of the Windows console code page.
    sys.stdin.reconfigure(encoding='utf-8')
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', required=True)
    parser.add_argument('--execute')
    args = parser.parse_args()
    worker = LocalWorker(args.root)
    try:
        if args.execute:
            worker.execute(args.execute); return
        request = json.loads(sys.stdin.readline())
        methods = {'workflow.submit': lambda p: worker.submit(p), 'run.status': lambda p: worker.status(p['job_id']), 'run.cancel': lambda p: worker.cancel(p['job_id'])}
        try:
            if request['jsonrpc'] != '2.0':
                raise ValueError('protocol')
            result = methods[request['method']](request['params'])
            reply = dict(jsonrpc='2.0', id=request['id'], result=result)
        except Exception as exc:
            reply = dict(jsonrpc='2.0', id=request.get('id'), error={'code': -32000, 'message': type(exc).__name__})
        print(canonical(reply))
    finally:
        worker.close()


if __name__ == '__main__':
    main()
