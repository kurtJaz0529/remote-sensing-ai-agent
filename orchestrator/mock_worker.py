"""Durable mock for protocol tests ONLY. Does not process remote-sensing data."""
import argparse
import json
import sqlite3
import sys
from pathlib import Path
from contracts import VERSION, canonical, fingerprint, sha256, validate, within

class MockWorker:
    def __init__(self, runtime_root, scenario="success"):
        self.root=Path(runtime_root).resolve(); self.root.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(self.root/"mock_jobs.sqlite")
        self.db.execute("CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, key TEXT UNIQUE, body TEXT, result TEXT, writes INTEGER)")
        self.scenario=scenario
        self.submissions=0

    def submit(self, job):
        validate("job",job)
        if job["implementation_kind"]!="mock" or job["tool"]!="mock.echo" or job["tool_version"]!=VERSION:
            raise ValueError("mock worker refuses non-mock tool")
        if set(job["parameters"])!={"message"} or not isinstance(job["parameters"]["message"],str):
            raise ValueError("invalid mock.echo parameters")
        old=self.db.execute("SELECT body,result FROM jobs WHERE id=? OR key=?",(job["job_id"],job["idempotency_key"])).fetchone()
        if old:
            if old[0]!=canonical(job):
                raise ValueError("idempotency key reused with different job")
            return json.loads(old[1])
        self.submissions+=1
        root=within(self.root,"runs/"+job["run_id"])
        path=within(root,job["output_dir"]+"/mock.txt")
        path.parent.mkdir(parents=True,exist_ok=True)
        if path.exists():
            raise ValueError("mock refuses to overwrite unregistered output")
        path.write_text("MOCK ONLY: "+job["parameters"]["message"],encoding="utf-8")
        artifact=dict(artifact_id="ART-"+job["idempotency_key"][:24],run_id=job["run_id"],step_id=job["step_id"],kind="data",relative_path=path.relative_to(root).as_posix(),sha256=sha256(path),size=path.stat().st_size,verified=True)
        result=dict(schema_revision=VERSION,job_id=job["job_id"],run_id=job["run_id"],step_id=job["step_id"],status="succeeded",software={"name":"MOCK ONLY","version":VERSION},implementation_kind="mock",effective_parameters=job["parameters"],input_manifest_hash=job["input_manifest_hash"],outputs=[artifact],checks=[{"check_id":"mock-nonempty","passed":True}],warnings=["Synthetic protocol evidence; not a software or scientific validation"],error=None)
        if self.scenario=="no_evidence": result["outputs"]=[]
        if self.scenario=="failed": result.update(status="failed",error={"code":"INJECTED"})
        if self.scenario=="running": result["status"]="running"
        with self.db:
            self.db.execute("INSERT INTO jobs VALUES(?,?,?,?,?)",(job["job_id"],job["idempotency_key"],canonical(job),canonical(result),1))
        if self.scenario=="lost_reply":
            raise TimeoutError("injected reply loss after durable write")
        return result

    def status(self, job_id):
        row=self.db.execute("SELECT result FROM jobs WHERE id=?",(job_id,)).fetchone()
        if row is None:
            raise ValueError("unknown mock job: manual reconciliation required")
        result=json.loads(row[0])
        if result["status"]=="running" and self.scenario!="running":
            result["status"]="succeeded"
            with self.db:
                self.db.execute("UPDATE jobs SET result=? WHERE id=?",(canonical(result),job_id))
        return result

    def cancel(self, job_id):
        result=self.status(job_id)
        if result["status"]=="running":
            result["status"]="cancelled"
            with self.db:
                self.db.execute("UPDATE jobs SET result=? WHERE id=?",(canonical(result),job_id))
        return result

    def close(self): self.db.close()

def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--root",required=True)
    args=parser.parse_args()
    request=json.loads(sys.stdin.readline())
    worker=MockWorker(args.root)
    method=request["method"]; params=request["params"]
    result=worker.submit(params) if method=="workflow.submit" else worker.status(params["job_id"]) if method=="run.status" else worker.cancel(params["job_id"]) if method=="run.cancel" else None
    print(canonical(dict(jsonrpc="2.0",id=request["id"],result=result)))
    worker.close()

if __name__=="__main__": main()
