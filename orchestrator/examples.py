"""Synthetic protocol examples, excluded from scientific validation."""
from contracts import VERSION, fingerprint

def mock_tool():
    return dict(schema_revision=VERSION,name="mock.echo",version=VERSION,description="Write a synthetic protocol marker; no remote sensing computation",side_effects=True,parameters={"type":"object","properties":{"message":{"type":"string","minLength":1}},"required":["message"],"additionalProperties":False},implementation_kind="mock")

def mock_plan(manifest, task_id="TASK-DEMO", revision=1):
    return dict(schema_revision=VERSION,task_id=task_id,revision=revision,objective="MOCK ONLY: exercise confirmation, dispatch and evidence gates",input_manifest_hash=fingerprint(manifest),requirements=[dict(requirement_id="REQ-DEMO",source_locator="synthetic protocol fixture",description="Create a mock marker",required_artifacts=["data"],acceptance_checks=["mock-nonempty"],confidence=1.0)],method_plan=[dict(step_id="S1",depends_on=[],tool="mock.echo",tool_version=VERSION,parameters={"message":"protocol-test"},dataset_ids=[manifest["dataset_id"]],output_dir="artifacts/S1",timeout_seconds=30,implementation_kind="mock",required_kinds=["data"])],required_deliverables=["data"],assumptions=["No software or scientific result is being validated"],open_questions=[],conflicts=[],evaluation_kind="unknown",frozen_versions={"contracts":VERSION},budget=dict(max_tool_calls=3,max_identical_error_retries=1,model_cost_limit=None))
