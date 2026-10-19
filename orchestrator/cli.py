"""Explicit CLI: imported plans must be reviewed and approved separately."""
import argparse
import json
import sys
from pathlib import Path
from contracts import canonical, validate
from .engine import Engine
from .intake import inventory, extract
from .mock_worker import MockWorker
from .providers import Provider, ProviderError
from .worker import JsonWorker

def read(path): return json.loads(Path(path).read_text(encoding="utf-8"))
def output(value): print(json.dumps(value,ensure_ascii=False,indent=2))

def main():
    p=argparse.ArgumentParser(description="AI遥感 Agent 云端核心开发预览；mock不代表本机验收")
    p.add_argument("--root",default="local-data",help="runtime directory; must be outside inputs")
    sub=p.add_subparsers(dest="command",required=True)
    sub.add_parser("doctor")
    q=sub.add_parser("init"); q.add_argument("--input",required=True); q.add_argument("--dataset-id",required=True); q.add_argument("--output",required=True)
    q=sub.add_parser("intake"); q.add_argument("document"); q.add_argument("--output",required=True)
    q=sub.add_parser("plan"); q.add_argument("--file",required=True); q.add_argument("--manifest",required=True); q.add_argument("--input",required=True)
    q=sub.add_parser("approve"); q.add_argument("task_id"); q.add_argument("--revision",type=int,required=True); q.add_argument("--actor",required=True)
    q=sub.add_parser("run"); q.add_argument("task_id"); q.add_argument("--revision",type=int,required=True); q.add_argument("--approval-id",required=True); q.add_argument("--mock",action="store_true"); q.add_argument("--worker-config")
    for name in ("resume","cancel"):
        q=sub.add_parser(name); q.add_argument("run_id"); q.add_argument("--mock",action="store_true"); q.add_argument("--worker-config")
    for name in ("status","export","pause"):
        q=sub.add_parser(name); q.add_argument("run_id")
    q=sub.add_parser("validate"); q.add_argument("schema"); q.add_argument("file")
    q=sub.add_parser("probe-provider"); q.add_argument("config"); q.add_argument("--output",required=True)
    q=sub.add_parser("knowledge-import"); q.add_argument("snapshot"); q.add_argument("--index",required=True); q.add_argument("--reviewed-evidence-root",action="append",default=[])
    q=sub.add_parser("knowledge-search"); q.add_argument("query"); q.add_argument("--index",required=True); q.add_argument("--software",required=True); q.add_argument("--version",required=True); q.add_argument("--license",action="append",default=[]); q.add_argument("--product"); q.add_argument("--format"); q.add_argument("--candidates",action="store_true")
    q=sub.add_parser("audit-bundle"); q.add_argument("directory")
    args=p.parse_args()
    engine=None; resource=None
    try:
        if args.command=="doctor":
            output(dict(python=sys.version.split()[0],platform=sys.platform,scope="cloud_core_preview",software_capabilities="not_probed; local Codex T01 required",provider_keys="not_inspected; configure via environment",real_software_run_ids=[])); return
        if args.command=="init":
            destination=Path(args.output).resolve()
            if destination.is_relative_to(Path(args.input).resolve()):
                raise ValueError("manifest output must be outside input originals")
            destination.write_text(canonical(inventory(args.input,args.dataset_id)),encoding="utf-8"); output({"manifest":str(destination)}); return
        if args.command=="intake":
            if Path(args.document).resolve()==Path(args.output).resolve():
                raise ValueError("cannot overwrite requirement original")
            Path(args.output).write_text(canonical(extract(args.document)),encoding="utf-8"); output({"extraction":args.output,"status":"requires_review"}); return
        if args.command=="validate":
            validate(args.schema,read(args.file)); output({"valid":True}); return
        if args.command=="audit-bundle":
            from .evidence import audit_bundle
            output(audit_bundle(args.directory)); return
        if args.command.startswith("knowledge-"):
            from retrieval.index import KnowledgeIndex
            from .evidence import load_reviewed_evidence
            evidence=load_reviewed_evidence(args.reviewed_evidence_root) if args.command=="knowledge-import" else {}
            resource=KnowledgeIndex(args.index,evidence)
            if args.command=="knowledge-import":
                resource.restore(args.snapshot); output({"imported":True})
            else:
                output(resource.search(args.query,args.software,args.version,args.license,args.product,args.format,args.candidates))
            return
        engine=Engine(args.root)
        if args.command=="probe-provider":
            resource=Provider(read(args.config),engine.store)
            result=resource.probe(); Path(args.output).write_text(canonical(result),encoding="utf-8"); output(result); return
        if args.command=="plan":
            output({"plan_hash":engine.save_plan(read(args.file),read(args.manifest),args.input),"state":"AwaitingPlanApproval"}); return
        if args.command=="approve":
            output({"approval_id":engine.approve(args.task_id,args.revision,args.actor)}); return
        if args.command in ("status","export","pause"):
            result=engine.status(args.run_id) if args.command=="status" else {"directory":engine.export(args.run_id)} if args.command=="export" else engine.pause(args.run_id)
            output(result); return
        if args.mock and args.worker_config:
            raise ValueError("select mock or configured worker")
        if args.mock:
            resource=MockWorker(args.root)
        elif args.worker_config:
            config=read(args.worker_config); resource=JsonWorker(config["command"],config.get("timeout_seconds",30))
        else:
            raise ValueError("real execution requires an explicit local worker configuration")
        run_id=engine.create_run(args.task_id,args.revision,args.approval_id,"mock" if args.mock else "real") if args.command=="run" else args.run_id
        output(engine.cancel(run_id,resource) if args.command=="cancel" else engine.execute(run_id,resource))
    except Exception as error:
        # Expected errors are useful; never echo provider/worker raw response bodies.
        output({"error":str(error) if isinstance(error,(ValueError,ProviderError)) else type(error).__name__,"completed":False})
        raise SystemExit(2)
    finally:
        if resource and hasattr(resource,"close"): resource.close()
        if engine: engine.store.close()

if __name__=="__main__": main()
