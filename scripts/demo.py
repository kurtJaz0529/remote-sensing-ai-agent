"""Create a synthetic, explicitly approved protocol demonstration in a fresh dir."""
import argparse
import json
from pathlib import Path
from contracts import canonical
from orchestrator.engine import Engine
from orchestrator.examples import mock_plan
from orchestrator.intake import inventory
from orchestrator.mock_worker import MockWorker
from orchestrator.evidence import audit_bundle

def demo(destination):
    destination=Path(destination).resolve()
    if destination.exists():
        raise ValueError("demo destination must not already exist")
    inputs=destination/"synthetic-inputs"; inputs.mkdir(parents=True)
    (inputs/"fixture.txt").write_text("SYNTHETIC PROTOCOL FIXTURE; not remote sensing imagery",encoding="utf-8")
    manifest=inventory(inputs,"SYNTHETIC-DATA")
    plan=mock_plan(manifest)
    root=destination/"runtime"
    engine=Engine(root); worker=MockWorker(root,"lost_reply")
    try:
        engine.save_plan(plan,manifest,inputs)
        no_approval_blocked=False
        try: engine.create_run(plan["task_id"],1,"missing","mock")
        except ValueError: no_approval_blocked=True
        approval=engine.approve(plan["task_id"],1,"synthetic-protocol-test")
        run=engine.create_run(plan["task_id"],1,approval,"mock")
        after_loss=engine.execute(run,worker)
        worker.scenario="success"
        recovered=engine.execute(run,worker)
        exported=engine.export(run)
        proof=audit_bundle(exported)
        summary=dict(scope="mock_only",no_approval_blocked=no_approval_blocked,after_lost_reply=after_loss["state"],after_recovery=recovered["state"],submissions=worker.submissions,run_id=run,integrity=proof,input_preserved=inventory(inputs,"SYNTHETIC-DATA")==manifest)
        if not (no_approval_blocked and after_loss["state"]=="Blocked" and recovered["state"]=="Completed" and worker.submissions==1 and summary["input_preserved"]):
            raise ValueError("protocol demo failed")
        (destination/"demo_summary.json").write_text(canonical(summary),encoding="utf-8")
        (destination/"input_manifest.json").write_text(canonical(manifest),encoding="utf-8")
        (destination/"plan.json").write_text(canonical(plan),encoding="utf-8")
        return summary
    finally:
        worker.close(); engine.store.close()

if __name__=="__main__":
    parser=argparse.ArgumentParser(); parser.add_argument("--destination",required=True)
    args=parser.parse_args(); print(json.dumps(demo(args.destination),ensure_ascii=False,indent=2))
