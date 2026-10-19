"""Evidence-gated execution. Unknown side effects are reconciled, never replayed."""
import json
import re
from pathlib import Path
from uuid import uuid4
from datetime import datetime
from jsonschema import Draft202012Validator
from contracts import VERSION, canonical, fingerprint, sha256, validate, within
from .intake import check_inputs, validate_plan
from .store import Store, now

class Engine:
    def __init__(self, root):
        self.store = Store(root)

    def _validate_tools(self, plan, mode):
        if mode=="mock":
            from .examples import mock_tool
            tools=[mock_tool()]
        else:
            path=self.store.root/"capabilities.json"
            if not path.is_file():
                raise ValueError("real execution needs local T01/T08 capabilities.json")
            catalog=validate("capabilities",json.loads(path.read_text(encoding="utf-8")))
            if plan["frozen_versions"].get("capabilities_sha256")!=fingerprint(catalog):
                raise ValueError("capability snapshot must be frozen in plan")
            tools=[c["tool"] for c in catalog["tools"] if c["status"]=="available" and c["verification_run_ids"]]
        by_name={}
        for tool in tools:
            validate("tool",tool)
            Draft202012Validator.check_schema(tool["parameters"])
            by_name[(tool["name"],tool["version"])]=tool
        for step in plan["method_plan"]:
            tool=by_name.get((step["tool"],step["tool_version"]))
            if not tool or tool["implementation_kind"]!=step["implementation_kind"]:
                raise ValueError("tool/version/implementation lacks verified capability")
            Draft202012Validator(tool["parameters"]).validate(step["parameters"])

    def save_plan(self, plan, manifest, input_root):
        validate("task", plan)
        validate("input_manifest", manifest)
        if not re.fullmatch(r"[A-Za-z0-9_-]+", plan["task_id"]):
            raise ValueError("nonportable task ID")
        if fingerprint(manifest) != plan["input_manifest_hash"]:
            raise ValueError("manifest hash mismatch")
        check_inputs(input_root, manifest)
        old = self.store.db.execute("SELECT hash FROM plans WHERE task=? AND revision=?",(plan["task_id"],plan["revision"])).fetchone()
        if old:
            if old[0] == fingerprint(plan):
                return old[0]
            raise ValueError("revision immutable; increment revision")
        latest = self.store.db.execute("SELECT MAX(revision) FROM plans WHERE task=?", (plan["task_id"],)).fetchone()[0]
        if latest is not None and plan["revision"] <= latest:
            raise ValueError("revision must increase")
        with self.store.db:
            self.store.db.execute("INSERT INTO plans VALUES(?,?,?,?,?,?)", (plan["task_id"],plan["revision"],fingerprint(plan),canonical(plan),canonical(manifest),str(Path(input_root).resolve())))
        return fingerprint(plan)

    def _plan(self, task, revision):
        row = self.store.db.execute("SELECT * FROM plans WHERE task=? AND revision=?", (task,revision)).fetchone()
        if row is None:
            raise ValueError("unknown plan revision")
        return dict(row), json.loads(row["body"]), json.loads(row["manifest"])

    def approve(self, task, revision, actor):
        row, plan, manifest = self._plan(task,revision)
        validate_plan(plan)
        check_inputs(row["input_root"],manifest)
        if not actor.strip():
            raise ValueError("approval actor required")
        approval = "APR-"+uuid4().hex
        with self.store.db:
            self.store.db.execute("INSERT INTO approvals VALUES(?,?,?,?,?,?,?)",(approval,task,revision,row["hash"],fingerprint(manifest),actor,now()))
        return approval

    def create_run(self, task, revision, approval, mode="real"):
        if mode not in ("real","mock"):
            raise ValueError("unknown mode")
        row, plan, manifest = self._plan(task,revision)
        validate_plan(plan)
        self._validate_tools(plan,mode)
        approved = self.store.db.execute("SELECT * FROM approvals WHERE id=?",(approval,)).fetchone()
        if approved is None or (approved["task"],approved["revision"],approved["plan_hash"],approved["manifest_hash"]) != (task,revision,row["hash"],fingerprint(manifest)):
            raise ValueError("approval does not match plan and inputs")
        check_inputs(row["input_root"],manifest)
        for step in plan["method_plan"]:
            if step["dataset_ids"] != [manifest["dataset_id"]]:
                raise ValueError("unregistered dataset")
            if (step["implementation_kind"] == "mock") != (mode == "mock"):
                raise ValueError("mock/real execution cannot be mixed")
        existing=self.store.db.execute("SELECT id FROM runs WHERE approval=? AND mode=?",(approval,mode)).fetchone()
        if existing:
            return existing[0]
        run = "RUN-"+uuid4().hex
        run_root = self.store.root / "runs" / run
        if run_root.is_relative_to(Path(row["input_root"])):
            raise ValueError("run directory cannot be inside original inputs")
        for directory in ("contract","environment","events","work","artifacts","evidence","checks","report","handoff"):
            (run_root / directory).mkdir(parents=True,exist_ok=True)
        (run_root/"contract"/"plan.json").write_text(canonical(plan),encoding="utf-8")
        (run_root/"contract"/"input_manifest.json").write_text(canonical(manifest),encoding="utf-8")
        with self.store.db:
            self.store.db.execute("INSERT INTO runs(id,task,revision,approval,state,mode,created) VALUES(?,?,?,?,?,?,?)",(run,task,revision,approval,"Preflight",mode,now()))
            self.store.event(run,"run.created",{"plan_hash":row["hash"],"approval_id":approval,"mode":mode})
        return run

    def _preflight(self, run):
        row, plan, manifest = self._plan(run["task"],run["revision"])
        self._validate_tools(plan,run["mode"])
        check_inputs(row["input_root"],manifest)
        run_root = self.store.root/"runs"/run["id"]
        if fingerprint(json.loads((run_root/"contract"/"plan.json").read_text(encoding="utf-8"))) != row["hash"]:
            raise ValueError("frozen plan changed")
        return plan, manifest, run_root

    def _artifacts(self, result, job, root, required):
        validate("result", result)
        for key in ("job_id","run_id","step_id","input_manifest_hash","implementation_kind"):
            if result[key] != job[key]:
                raise ValueError("worker identity mismatch: "+key)
        if canonical(result["effective_parameters"]) != canonical(job["parameters"]):
            raise ValueError("effective parameters differ from approved plan")
        if result["status"] != "succeeded":
            return
        if not result["checks"] or not all(c["passed"] for c in result["checks"]) or result["error"] is not None:
            raise ValueError("worker checks failed or absent")
        if not result["outputs"]:
            raise ValueError("success without evidence")
        ids, paths, kinds = set(), set(), set()
        for artifact in result["outputs"]:
            if artifact["run_id"] != job["run_id"] or artifact["step_id"] != job["step_id"] or not artifact["verified"]:
                raise ValueError("unverified or stale artifact")
            if artifact["artifact_id"] in ids or artifact["relative_path"] in paths:
                raise ValueError("duplicate artifact identity/path")
            ids.add(artifact["artifact_id"]); paths.add(artifact["relative_path"])
            path = within(root,artifact["relative_path"])
            output = within(root,job["output_dir"])
            if not path.is_relative_to(output) or not path.is_file():
                raise ValueError("artifact missing or outside step output")
            if path.stat().st_size != artifact["size"] or sha256(path) != artifact["sha256"]:
                raise ValueError("artifact hash/size mismatch")
            if artifact["kind"]=="screenshot":
                capture=artifact.get("capture")
                if not capture or datetime.fromisoformat(capture["captured_at"]) < datetime.fromisoformat(self.store.run(job["run_id"])["created"]):
                    raise ValueError("missing or stale screenshot identity metadata")
                linked=list(result["outputs"])
                for old in self.store.db.execute("SELECT result FROM steps WHERE run=? AND state='succeeded'",(job["run_id"],)):
                    linked.extend(json.loads(old[0])["outputs"])
                if not any(a["artifact_id"]==capture["displayed_artifact_id"] and a["sha256"]==capture["displayed_artifact_sha256"] and a["kind"]!="screenshot" for a in linked):
                    raise ValueError("screenshot does not identify a current run artifact")
                with path.open("rb") as stream: signature=stream.read(1024)
                if not signature.startswith(b"\x89PNG\r\n\x1a\n"):
                    raise ValueError("screenshot must be an actual PNG; visual review remains local T16")
            if artifact["kind"]=="pdf":
                with path.open("rb") as stream: signature=stream.read(1024)
                if not signature.lstrip().startswith(b"%PDF-"):
                    raise ValueError("PDF content signature missing")
            if artifact["kind"]=="docx":
                from zipfile import ZipFile
                with ZipFile(path) as document:
                    if "word/document.xml" not in document.namelist() or document.testzip():
                        raise ValueError("invalid DOCX package")
            kinds.add(artifact["kind"])
        if not set(required) <= kinds:
            raise ValueError("required step artifacts missing")

    def execute(self, run_id, worker):
        with self.store.coordinator_lock():
            return self._execute(run_id,worker)

    def _execute(self, run_id, worker):
        run = self.store.run(run_id)
        if run["state"] in ("Completed","Cancelled","Failed"):
            return self.status(run_id)
        try:
            plan, manifest, root = self._preflight(run)
        except Exception as error:
            with self.store.db:
                self.store.state(run_id,"Blocked",str(error))
            return self.status(run_id)
        with self.store.db:
            self.store.state(run_id,"Executing")
        pending = {s["step_id"]:s for s in plan["method_plan"]}
        done = set()
        while pending:
            eligible = [s for s in pending.values() if set(s["depends_on"]) <= done]
            if not eligible:
                raise ValueError("invalid dependency graph")
            step = eligible[0]; sid = step["step_id"]
            existing = self.store.db.execute("SELECT * FROM steps WHERE run=? AND id=?", (run_id,sid)).fetchone()
            if existing and existing["state"] == "succeeded":
                try:
                    self._artifacts(json.loads(existing["result"]), json.loads(existing["body"]), root, step["required_kinds"])
                except Exception as error:
                    with self.store.db:
                        self.store.state(run_id,"Blocked",str(error))
                    return self.status(run_id)
                done.add(sid); del pending[sid]; continue
            if existing and existing["state"] in ("failed","cancelled"):
                with self.store.db:
                    self.store.state(run_id,"Failed","worker has terminal failed/cancelled step; new revision required")
                return self.status(run_id)
            try:
                if existing:
                    job=json.loads(existing["body"])
                    # Even a crash immediately before submit remains uncertain.
                    result=worker.status(job["job_id"])
                else:
                    calls = self.store.run(run_id)["calls"]
                    if calls >= plan["budget"]["max_tool_calls"]:
                        with self.store.db:
                            self.store.state(run_id,"Blocked","tool call budget exhausted")
                        return self.status(run_id)
                    key=fingerprint(dict(run=run_id,plan=fingerprint(plan),step=step))
                    job=dict(schema_revision=VERSION,job_id="JOB-"+key[:32],project_id=plan["task_id"],run_id=run_id,step_id=sid,plan_revision=plan["revision"],approval_id=run["approval"],tool=step["tool"],tool_version=step["tool_version"],parameters=step["parameters"],dataset_ids=step["dataset_ids"],input_manifest_hash=fingerprint(manifest),output_dir=step["output_dir"],timeout_seconds=step["timeout_seconds"],idempotency_key=key,implementation_kind=step["implementation_kind"])
                    validate("job",job)
                    within(root,job["output_dir"]).mkdir(parents=True,exist_ok=True)
                    with self.store.db:
                        self.store.db.execute("INSERT INTO steps VALUES(?,?,?,?,?,?,?,?)",(run_id,sid,job["job_id"],key,"uncertain",canonical(job),None,None))
                        self.store.db.execute("UPDATE runs SET calls=calls+1 WHERE id=?",(run_id,))
                        self.store.event(run_id,"job.dispatch_intent",job,sid)
                    result=worker.submit(job)
                self._artifacts(result,job,root,step["required_kinds"])
            except Exception as error:
                # Preserve job identity. No retry until remote state is known.
                with self.store.db:
                    self.store.event(run_id,"job.needs_reconciliation",{"error_type":type(error).__name__},sid)
                    self.store.state(run_id,"Blocked","worker reply/evidence requires reconciliation")
                return self.status(run_id)
            state=result["status"]
            with self.store.db:
                self.store.db.execute("UPDATE steps SET state=?,result=? WHERE run=? AND id=?",(state,canonical(result),run_id,sid))
                self.store.event(run_id,"job."+state,result,sid)
            if state != "succeeded":
                with self.store.db:
                    self.store.state(run_id,"Failed" if state in ("failed","cancelled") else "Paused",state)
                return self.status(run_id)
            done.add(sid); del pending[sid]
        with self.store.db:
            self.store.state(run_id,"Verifying")
        artifacts=[]
        for row in self.store.db.execute("SELECT result FROM steps WHERE run=?",(run_id,)):
            artifacts.extend(json.loads(row[0])["outputs"])
        kinds={a["kind"] for a in artifacts}
        passed_checks=set()
        for row in self.store.db.execute("SELECT result FROM steps WHERE run=?",(run_id,)):
            passed_checks.update(c["check_id"] for c in json.loads(row[0])["checks"] if c["passed"])
        required_checks={check for req in plan["requirements"] for check in req["acceptance_checks"]}
        state="Completed" if set(plan["required_deliverables"]) <= kinds and required_checks<=passed_checks else "Blocked"
        with self.store.db:
            self.store.state(run_id,"Reporting")
            self.store.state(run_id,state,"required artifacts verified" if state=="Completed" else "required delivery missing")
        self.export(run_id)
        return self.status(run_id)

    def pause(self, run_id):
        with self.store.coordinator_lock(), self.store.db:
            run=self.store.run(run_id)
            if run["state"] not in ("Completed","Failed","Cancelled"):
                self.store.state(run_id,"Paused","operator pause")

    def cancel(self, run_id, worker):
        with self.store.coordinator_lock():
            run=self.store.run(run_id)
            if run["state"] in ("Completed","Failed","Cancelled"):
                return self.status(run_id)
            for step in self.store.db.execute("SELECT * FROM steps WHERE run=?",(run_id,)).fetchall():
                if step["state"] not in ("succeeded","failed","cancelled"):
                    try:
                        response=worker.cancel(step["job"])
                        if response.get("status") not in ("cancelled","succeeded","failed"):
                            raise ValueError("cancellation not acknowledged")
                    except Exception:
                        with self.store.db:
                            self.store.state(run_id,"Blocked","cancel pending; worker/process state unknown")
                        return self.status(run_id)
            with self.store.db:
                self.store.state(run_id,"Cancelled","worker terminal or no pending job; evidence retained")
            return self.status(run_id)

    def status(self, run_id):
        result=self.store.run(run_id)
        result["steps"]=[dict(row) for row in self.store.db.execute("SELECT id,job,state,error FROM steps WHERE run=?",(run_id,))]
        result["validation_scope"]="mock_only" if result["mode"]=="mock" else "worker_report_plus_file_hash_checks; independent/local validation still required"
        return result

    def export(self, run_id):
        run=self.store.run(run_id)
        root=self.store.root/"runs"/run_id
        events=[]
        for row in self.store.db.execute("SELECT * FROM events WHERE run=? ORDER BY seq",(run_id,)):
            event=dict(schema_revision=VERSION,event_id="EVT-"+str(row["seq"]),run_id=run_id,step_id=row["step"],timestamp=row["timestamp"],event_type=row["type"],payload=json.loads(row["body"]))
            validate("event",event); events.append(canonical(event))
        (root/"events"/"events.jsonl").write_text("\n".join(events)+"\n",encoding="utf-8")
        summary=self.status(run_id)
        (root/"handoff"/"run_summary.json").write_text(canonical(summary),encoding="utf-8")
        entries=[]
        for p in sorted(root.rglob("*")):
            if p.is_file() and p.name!="manifest.json":
                entries.append(dict(relative_path=p.relative_to(root).as_posix(),size=p.stat().st_size,sha256=sha256(p)))
        (root/"manifest.json").write_text(canonical({"schema_revision":VERSION,"run_id":run_id,"files":entries}),encoding="utf-8")
        return str(root)
