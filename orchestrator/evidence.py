"""Integrity review of handoff bundles; no claim of scientific correctness."""
import json
from pathlib import Path
from contracts import sha256, within

def audit_bundle(root):
    root=Path(root).resolve()
    manifest_path=root/"manifest.json"
    manifest=json.loads(manifest_path.read_text(encoding="utf-8"))
    paths=set()
    if not manifest.get("files"):
        raise ValueError("empty evidence manifest")
    for entry in manifest["files"]:
        relative=entry["relative_path"]
        if relative in paths:
            raise ValueError("duplicate manifest path")
        paths.add(relative)
        path=within(root,relative)
        if not path.is_file() or path.stat().st_size!=entry["size"] or sha256(path)!=entry["sha256"]:
            raise ValueError("bundle integrity failed: "+relative)
    if "handoff/run_summary.json" not in paths or "contract/plan.json" not in paths:
        raise ValueError("bundle lacks frozen plan or run summary")
    summary=json.loads((root/"handoff/run_summary.json").read_text(encoding="utf-8"))
    if summary["id"]!=manifest["run_id"]:
        raise ValueError("bundle run identity mismatch")
    return {"run_id":manifest["run_id"],"mode":summary["mode"],"passed":summary["state"]=="Completed","evidence_manifest_sha256":sha256(manifest_path),"file_count":len(paths),"scope":"file_integrity_only; local software and scientific correctness need independent review"}

def load_reviewed_evidence(paths):
    """Caller supplies evidence roots after local/independent review; hash all files."""
    result={}
    for path in paths:
        proof=audit_bundle(path)
        if proof["mode"]!="real" or not proof["passed"]:
            raise ValueError("mock/incomplete evidence cannot support published knowledge")
        result[proof["run_id"]]=proof
    return result
