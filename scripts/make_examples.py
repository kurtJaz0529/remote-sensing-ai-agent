"""Generate only marked contract examples; no example is a real software result."""
import json
from pathlib import Path
from contracts import VERSION, canonical, fingerprint, validate
from orchestrator.examples import mock_plan, mock_tool

root=Path(__file__).resolve().parents[1]
examples=root/"examples"; examples.mkdir(exist_ok=True)
def save(name,body,schema_name=None):
    if schema_name: validate(schema_name,body)
    (examples/(name+".json")).write_text(json.dumps(body,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
manifest=dict(schema_revision=VERSION,dataset_id="SYNTHETIC-DATA",origin="user_provided",files=[dict(relative_path="fixture.txt",sha256="0"*64,size=1)])
save("input_manifest",manifest,"input_manifest")
save("task",mock_plan(manifest),"task")
save("tool",mock_tool(),"tool")
job=dict(schema_revision=VERSION,job_id="JOB-EXAMPLE",project_id="TASK-DEMO",run_id="RUN-EXAMPLE",step_id="S1",plan_revision=1,approval_id="APR-EXAMPLE-NOT-VALID",tool="mock.echo",tool_version=VERSION,parameters={"message":"synthetic"},dataset_ids=["SYNTHETIC-DATA"],input_manifest_hash=fingerprint(manifest),output_dir="artifacts/S1",timeout_seconds=30,idempotency_key="1"*64,implementation_kind="mock")
save("job",job,"job")
artifact=dict(schema_revision=VERSION,artifact_id="ART-EXAMPLE",run_id="RUN-EXAMPLE",step_id="S1",kind="data",relative_path="artifacts/S1/mock.txt",sha256="2"*64,size=1,verified=False)
save("artifact",artifact,"artifact")
output={k:v for k,v in artifact.items() if k!="schema_revision"}
result=dict(schema_revision=VERSION,job_id=job["job_id"],run_id=job["run_id"],step_id="S1",status="running",software={"name":"MOCK ONLY","version":VERSION},implementation_kind="mock",effective_parameters=job["parameters"],input_manifest_hash=job["input_manifest_hash"],outputs=[output],checks=[],warnings=["contract example; no real run"],error=None)
save("result",result,"result")
save("event",dict(schema_revision=VERSION,event_id="EVT-EXAMPLE",run_id="RUN-EXAMPLE",step_id="S1",timestamp="2026-10-19T00:00:00+00:00",event_type="example.only",payload={"scope":"mock_only"}),"event")
save("source",dict(schema_revision=VERSION,source_id="SRC-EXAMPLE",title="Contract placeholder; not a scientific reference",source_type="model_candidate",url="https://example.invalid/placeholder",locator="not available",software_version="5.6",retrieved_at="2026-10-19",access_scope="metadata",review_status="candidate",snapshot_sha256=None),"source")
save("knowledge",dict(schema_revision=VERSION,knowledge_id="KNOW-EXAMPLE",revision=1,kind="software_method",claim="契约占位示例；不得作为方法依据",source_ids=["SRC-EXAMPLE"],source_locator="未获取原文",software="ENVI",software_version_scope="==5.6.*",sensor_product_scope=[],required_licenses=["ENVI"],input_formats=["ENVI"],preconditions=[],limitations=["not executable knowledge"],implementation_kind="native",source_review_status="candidate",local_verification_status="not_run",verification_run_ids=[],conflicts_with=[],reviewer_role="cloud_codex",lifecycle="candidate"),"knowledge")
save("experience",dict(schema_revision=VERSION,experience_id="EXP-EXAMPLE",revision=1,phenomenon="合同字段示例",scope="not an enabled rule",evidence_run_ids=["RUN-REQUIRED-NOT-PROVIDED"],reproduction_run_ids=[],fix_comparison_run_ids=[],regression_run_ids=[],reviewer_role=None,author_role="cloud_codex",status="candidate",supersedes=None),"experience")
save("capabilities",dict(schema_revision=VERSION,environment_id="NOT-PROBED",verified_at="2026-10-19T00:00:00+00:00",tools=[dict(tool=mock_tool(),status="unknown",verification_run_ids=[],limitations=["example is not a real software capability"]) ]),"capabilities")
for provider,url,key in (("openai","https://api.openai.com/v1","OPENAI_API_KEY"),("deepseek","https://api.deepseek.com","DEEPSEEK_API_KEY")):
    save(provider+".provider",dict(schema_revision=VERSION,provider=provider,base_url=url,model="REPLACE_WITH_ACTUAL_SUPPORTED_MODEL",api_key_env=key,timeout_seconds=30,context_tokens=8192,tool_calling="unknown",vision="unknown",extra_body={},pricing=None),"provider")
save("worker",{"command":["REPLACE_WITH_SOFTWARE_PYTHON","-m","your_local_worker","--runtime-root","REPLACE_WITH_LOCAL_RUNTIME"],"timeout_seconds":30})
save("handoff",dict(schema_revision=VERSION,task_id="T03",from_role="cloud_codex",to_role="local_codex",status="ready_for_review",spec_revision="v1.1",base_version="0.1.0.dev1",artifact_manifest="releases/release_manifest.json",input_refs=[],changed_files=["contracts/","orchestrator/","retrieval/"],result_summary=["cloud core development preview"],validation={"static_or_mock":["evidence/clean-install/test_results.json"],"real_software_run_ids":[],"evidence_manifest":None},limitations=["real API and Windows software not verified"],open_questions=[],next_action="review public contracts and implement T08 worker"),"handoff")
