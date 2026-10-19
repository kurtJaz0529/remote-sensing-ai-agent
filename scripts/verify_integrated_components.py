"""Read-only MCP comparison of candidate validators against a completed native run."""
import argparse
import json
import sys
from pathlib import Path
import numpy as np
from contracts import fingerprint, sha256
from orchestrator.engine import Engine
from orchestrator.archive import audit_bundle, pack, restore
from adapters.case_audit import read_cube, read_samples, read_classification, confusion_metrics
from verification.dataset_audit import audit_envi_dataset, audit_sample_split, CANONICAL_CLASS_SCHEMAS
from verification.classification_eval import evaluate_classification
from verification.fault_scenarios import run_all_fault_scenarios
from methods.spectral import compute_ndvi, compute_pca
from reports.report_builder import audit_report_payload
from retrieval.index import KnowledgeIndex
from scripts.evaluate_retrieval import evaluate

REPO = Path(__file__).resolve().parents[1]


def verify_case(runtime, output):
    engine = Engine(runtime)
    try:
        run_id = json.loads((Path(runtime)/'integration-summary.json').read_text(encoding='utf-8'))['run_id']
        run = engine.store.run(run_id)
        if run['state'] != 'Completed':
            raise ValueError('A completed native run is required')
        plan, manifest, run_root = engine._preflight(run)
        row, _, _ = engine._plan(run['task'], run['revision'])
        proof = audit_bundle(run_root)
        source_root = Path(row['input_root'])
        source = next(source_root.joinpath(e['relative_path']) for e in manifest['files'] if e['sha256'] == '121f1268c855ace06edd642ff191ff04da74499df3ff70c69c8b8bcee11345e5')
        cube = read_cube(source)
        train = read_samples(source.parent/'train_roi.csv',640,400,True)
        test = read_samples(source.parent/'test_roi.csv',640,400,False)
        native = run_root/'artifacts/S1/native'
        ml = read_classification(native/'maximum-likelihood.dat',(400,640))
        schema = CANONICAL_CLASS_SCHEMAS['matlab_archive']
        reference = test[:,0].tolist()
        predicted = ml[test[:,2],test[:,1]].tolist()
        metrics = evaluate_classification(reference,predicted,schema)
        independent = confusion_metrics(np.asarray(reference),np.asarray(predicted))
        reordered = np.asarray(independent['matrix'])[:,[1,2,3,4,5,6,0]].tolist()
        assert metrics['matrix'] == reordered
        assert abs(metrics['overall_accuracy']-independent['overall_accuracy']) < 1e-6
        assert abs(metrics['kappa']-independent['kappa']) < 1e-6
        meta = audit_envi_dataset(source.with_suffix('.hdr'),source)
        assert meta['passed'] and not meta['metadata']['has_crs'] and not meta['metadata']['has_verified_scale_factor']
        points = lambda arr: [dict(x=int(x),y=int(y),semantic_id=schema[int(c)]['semantic_id']) for c,x,y,_ in arr]
        split = audit_sample_split(points(train),points(test),claimed_evaluation_kind='diagnostic',is_diagnostic_revision=True)
        assert split['task_evaluation_kind']=='diagnostic' and split['buffer_violation_count']==0
        patch = cube[:16,:16,:].astype(float).transpose(2,0,1)
        ndvi = compute_ndvi(patch[3].tolist(),patch[2].tolist())
        denominator=patch[3]+patch[2]
        expected=np.full((16,16),-9999.0)
        np.divide(patch[3]-patch[2],denominator,out=expected,where=denominator!=0)
        assert np.allclose(ndvi['index_map'],expected,atol=5.1e-7,rtol=0)
        pca=compute_pca(patch.tolist(),fit_domain='full_image_unsupervised')
        eigenvalues=np.linalg.eigvalsh(np.cov(patch.reshape(6,-1),ddof=1))[::-1]
        assert np.allclose(pca['eigenvalues'],eigenvalues,atol=1e-5,rtol=1e-6)
        assert not audit_report_payload({'sections':{}},{})['passed']
        faults=run_all_fault_scenarios()
        assert faults['all_passed']
        sources=json.loads((REPO/'knowledge/sources/sources_catalog.json').read_text(encoding='utf-8'))
        cards=json.loads((REPO/'knowledge/candidates/knowledge_cards.json').read_text(encoding='utf-8'))
        index=KnowledgeIndex(Path(output)/'review-index.sqlite')
        try:
            index.ingest(cards,sources)
            retrieval=evaluate(index,json.loads((REPO/'tests/fixtures/public_retrieval_regression.json').read_text(encoding='utf-8')))
            retrieval['scope']='public_regression_only; exposed questions are not held-out acceptance'
            assert retrieval['passed']==retrieval['total']==12
            index.ingest(json.loads((REPO/'knowledge/candidates/local-codex-methods-20261019.json').read_text(encoding='utf-8')),json.loads((REPO/'knowledge/sources/local-codex-20261019.json').read_text(encoding='utf-8')))
            assert index.search('classification',software='ENVI',version='5.6',licenses=['ENVI'],input_format='ENVI')==[]
            snapshot_hash=index.snapshot(Path(output)/'candidate-snapshot.json')
        finally:index.close()
        recovery=[]
        for label, selected in [('classification',run_root),('second-rgb',Path(runtime).parent/'secondary-rgb-mcp-20261019-r2/runs/RUN-f1d775c028654d5f97914605d13edc06')]:
            archive=Path(output)/(label+'.zip')
            packed=pack(selected,archive)
            restored=restore(archive,Path(output)/(label+'-restored'),packed['archive_sha256'])
            assert restored['passed'] and restored['evidence_manifest_sha256']==packed['evidence_manifest_sha256']
            recovery.append(dict(case=label,**restored,archive_sha256=packed['archive_sha256']))
        result=dict(scope='read-only component integration; not independent experiment acceptance',run_id=run_id,plan_hash=fingerprint(plan),input_manifest_hash=fingerprint(manifest),
                    native_bundle_audit=proof,metadata_passed=meta['passed'],sample_evaluation=split['task_evaluation_kind'],minimum_sample_distance=split['min_chebyshev_distance'],
                    confusion_matrix_match=True,overall_accuracy_diagnostic=metrics['overall_accuracy'],kappa_diagnostic=metrics['kappa'],
                    ndvi_stored_value_arithmetic_match=True,pca_eigenvalues_match=True,spectral_scope='16x16 stored-value arithmetic; no calibrated reflectance claim; Python reimplementation',
                    formal_report_missing_evidence_blocked=True,fault_scenarios=faults,retrieval=retrieval,published_default_results=0,candidate_snapshot_hash=snapshot_hash,recovery=recovery,
                    component_hashes={p.relative_to(REPO).as_posix():sha256(p) for directory in ('methods','verification','reports','skills') for p in (REPO/directory).glob('*.py')})
        return result
    finally:engine.store.close()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--runtime',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--serve',action='store_true')
    args=parser.parse_args()
    output=Path(args.output).resolve()
    if args.serve:
        from mcp.server.fastmcp import FastMCP
        server=FastMCP('rsagent-component-review',log_level='WARNING')
        @server.tool()
        def verify_registered_case() -> dict:
            """Read frozen native output and registered inputs; no user-file writes or native resubmission."""
            try:
                return verify_case(args.runtime,output)
            except Exception as exc:
                return {'status':'failed','error_type':type(exc).__name__,'message':str(exc)[:500]}
        server.run()
    else:
        if output.exists():raise ValueError('Use a new review directory')
        output.mkdir(parents=True)
        from orchestrator.mcp_worker import McpWorker
        client=McpWorker([sys.executable,'-m','scripts.verify_integrated_components','--runtime',str(Path(args.runtime).resolve()),'--output',str(output),'--serve'],timeout=50)
        result=client.request('verify_registered_case',{})
        (output/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(result,ensure_ascii=False,indent=2))
        if result.get('status')=='failed':raise SystemExit(1)


if __name__=='__main__':main()
