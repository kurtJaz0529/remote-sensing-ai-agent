"""Verify every tracked file before installation/handoff; never extracts archives."""
import json
from pathlib import Path
from contracts import sha256, within

def verify(root):
    root=Path(root).resolve()
    manifest=json.loads((root/"releases/release_manifest.json").read_text(encoding="utf-8"))
    seen=set()
    for file in manifest["files"]:
        if file["relative_path"] in seen: raise ValueError("duplicate release file")
        seen.add(file["relative_path"])
        path=within(root,file["relative_path"])
        if path.stat().st_size!=file["size"] or sha256(path)!=file["sha256"]:
            raise ValueError("release mismatch: "+file["relative_path"])
    return dict(version=manifest["version"],verified_files=len(seen),scope=manifest["scope"])

if __name__=="__main__": print(json.dumps(verify(Path(__file__).resolve().parents[1]),indent=2))
