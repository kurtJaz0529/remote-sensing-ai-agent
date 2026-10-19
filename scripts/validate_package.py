"""Run the release tests and produce a machine-readable evidence record."""
import argparse
import json
import platform
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from contracts import validate
import orchestrator

def ids(suite):
    result=[]
    for test in suite:
        result.extend(ids(test) if isinstance(test,unittest.TestSuite) else [test.id()])
    return result

if __name__=="__main__":
    parser=argparse.ArgumentParser(); parser.add_argument("--output",required=True); parser.add_argument("--source",required=True)
    args=parser.parse_args(); source=Path(args.source).resolve(); out=Path(args.output).resolve(); out.mkdir(parents=True,exist_ok=True)
    suite=unittest.defaultTestLoader.discover(str(source/"tests")); test_ids=ids(suite)
    start=time.monotonic()
    with (out/"tests.log").open("w",encoding="utf-8") as stream:
        result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    examples=[]
    for name in ("artifact","capabilities","event","experience","handoff","input_manifest","job","knowledge","result","source","task","tool"):
        validate(name,json.loads((source/"examples"/(name+".json")).read_text(encoding="utf-8"))); examples.append(name)
    for name in ("openai","deepseek"):
        validate("provider",json.loads((source/"examples"/(name+".provider.json")).read_text(encoding="utf-8"))); examples.append(name+".provider")
    body=dict(observed_at=datetime.now(timezone.utc).isoformat(),python=platform.python_version(),platform=platform.system(),package_import=str(Path(orchestrator.__file__).resolve()),tests_run=result.testsRun,failures=len(result.failures),errors=len(result.errors),skipped=len(result.skipped),passed=result.wasSuccessful(),duration_seconds=time.monotonic()-start,test_ids=test_ids,schema_examples=examples,scope="installed-wheel unit/mock/protocol validation; no real software/API or scientific experiment")
    (out/"test_results.json").write_text(json.dumps(body,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({k:body[k] for k in ("tests_run","failures","errors","passed","package_import")},indent=2))
    raise SystemExit(0 if result.wasSuccessful() else 1)
