"""Regenerate standalone Draft 2020-12 contracts; no remote references."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "contracts"
S = {"type": "string", "minLength": 1}
H = {"type": "string", "pattern": "^[a-f0-9]{64}$"}
I = {"type": "integer", "minimum": 1}
B = {"type": "boolean"}
O = {"type": "object"}
def arr(item=S, minimum=0):
    return {"type": "array", "items": item, "minItems": minimum, "uniqueItems": True}
def enum(*values):
    return {"enum": list(values)}
def obj(props, optional=()):
    return {"type": "object", "properties": props, "required": [k for k in props if k not in optional], "additionalProperties": False}
def emit(name, props, optional=()):
    value = obj({"schema_revision": {"const": "0.1.0"}, **props}, optional)
    value["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    value["$id"] = "urn:rsagent:" + name + ":0.1.0"
    (ROOT / (name + ".schema.json")).write_text(json.dumps(value, ensure_ascii=False, indent=2)+"\n")

artifact = obj(dict(artifact_id=S, run_id=S, step_id=S, kind=enum("data","project","reproducible_package","screenshot","docx","pdf","log","check"), relative_path=S, sha256=H, size={"type":"integer","minimum":1}, verified=B))
artifact["properties"]["capture"] = obj(dict(software=S,software_version=S,window_title=S,process_id=I,layer_or_file=S,captured_at={"type":"string","format":"date-time"},displayed_artifact_id=S,displayed_artifact_sha256=H,identity_check={"const":"passed"},capture_kind=enum("operation","result_display")))
artifact["allOf"]=[{"if":{"properties":{"kind":{"const":"screenshot"}}},"then":{"required":["capture"]}}]
requirement = obj(dict(requirement_id=S, source_locator=S, description=S, required_artifacts=arr(), acceptance_checks=arr(), confidence={"type":"number","minimum":0,"maximum":1}))
step = obj(dict(step_id=S, depends_on=arr(), tool=S, tool_version=S, parameters=O, dataset_ids=arr(S,1), output_dir=S, timeout_seconds={"type":"number","exclusiveMinimum":0}, implementation_kind=enum("native","reimplementation","approximation","mock"), required_kinds=arr(S,1)))
emit("artifact", artifact["properties"],("capture",))
artifact_file=ROOT/"artifact.schema.json"
artifact_schema=json.loads(artifact_file.read_text())
artifact_schema["allOf"]=artifact["allOf"]
artifact_file.write_text(json.dumps(artifact_schema,ensure_ascii=False,indent=2)+"\n")
artifact["required"]=[k for k in artifact["properties"] if k!="capture"]
emit("input_manifest", dict(dataset_id=S, origin={"const":"user_provided"}, files=arr(obj(dict(relative_path=S, sha256=H, size={"type":"integer","minimum":0})),1)))
emit("task", dict(task_id=S, revision=I, objective=S, input_manifest_hash=H, requirements=arr(requirement,1), method_plan=arr(step,1), required_deliverables=arr(S,1), assumptions=arr(), open_questions=arr(), conflicts=arr(), evaluation_kind=enum("unknown","diagnostic","reference_agreement","independent"), frozen_versions=O, budget=obj(dict(max_tool_calls=I,max_identical_error_retries={"type":"integer","minimum":0,"maximum":1}, model_cost_limit={"type":["number","null"],"minimum":0}))))
emit("job", dict(job_id=S,project_id=S,run_id=S,step_id=S,plan_revision=I,approval_id=S,tool=S,tool_version=S,parameters=O,dataset_ids=arr(S,1),input_manifest_hash=H,output_dir=S,timeout_seconds={"type":"number","exclusiveMinimum":0},idempotency_key=H,implementation_kind=enum("native","reimplementation","approximation","mock")))
emit("result", dict(job_id=S,run_id=S,step_id=S,status=enum("queued","running","succeeded","failed","cancelled","unknown"),software=obj(dict(name=S,version=S)),implementation_kind=enum("native","reimplementation","approximation","mock"),effective_parameters=O,input_manifest_hash=H,outputs=arr(artifact),checks=arr(obj(dict(check_id=S,passed=B))),warnings=arr(),error={"type":["object","null"]}))
emit("event", dict(event_id=S,run_id=S,step_id={"type":["string","null"]},timestamp={"type":"string","format":"date-time"},event_type=S,payload=O))
emit("tool", dict(name=S,version=S,description=S,side_effects=B,parameters=O,implementation_kind=enum("native","reimplementation","approximation","mock")))
emit("knowledge", dict(knowledge_id=S,revision=I,kind=S,claim=S,source_ids=arr(S,1),source_locator=S,software=S,software_version_scope=S,sensor_product_scope=arr(),required_licenses=arr(),input_formats=arr(),preconditions=arr(),limitations=arr(),implementation_kind=enum("native","reimplementation","approximation"),source_review_status=enum("candidate","verified","rejected"),local_verification_status=enum("not_run","verified","invalid"),verification_run_ids=arr(),conflicts_with=arr(),reviewer_role=S,lifecycle=enum("candidate","published","withdrawn")))
emit("handoff", dict(task_id=S,from_role=enum("local_codex","cloud_codex","gemini_antigravity"),to_role=S,status=S,spec_revision=S,base_version=S,artifact_manifest=S,input_refs=arr(),changed_files=arr(),result_summary=arr(),validation=obj(dict(static_or_mock=arr(),real_software_run_ids=arr(),evidence_manifest={"type":["string","null"]})),limitations=arr(),open_questions=arr(),next_action=S))
emit("experience", dict(experience_id=S,revision=I,phenomenon=S,scope=S,evidence_run_ids=arr(S,1),reproduction_run_ids=arr(),fix_comparison_run_ids=arr(),regression_run_ids=arr(),reviewer_role={"type":["string","null"]},author_role=S,status=enum("candidate","reproduced","fix_verified","published","withdrawn"),supersedes={"type":["integer","null"],"minimum":1}))
emit("provider", dict(provider=enum("openai","deepseek"),base_url=S,model=S,api_key_env=S,timeout_seconds={"type":"number","exclusiveMinimum":0},context_tokens=I,tool_calling=enum("unknown","verified","unsupported"),vision=enum("unknown","verified","unsupported"),extra_body=O,pricing={"type":["object","null"]}))
emit("source", dict(source_id=S,title=S,source_type=enum("official","paper","community","local_observation","model_candidate"),url={"type":"string","format":"uri"},locator=S,software_version=S,retrieved_at={"type":"string","format":"date"},access_scope=enum("full_text","abstract","metadata","local_help"),review_status=enum("candidate","verified","rejected"),snapshot_sha256={"type":["string","null"],"pattern":"^[a-f0-9]{64}$"}))
emit("capabilities",dict(environment_id=S,verified_at={"type":"string","format":"date-time"},tools=arr(obj(dict(tool=O,status=enum("available","restricted","unavailable","unknown"),verification_run_ids=arr(),limitations=arr())),1)))
