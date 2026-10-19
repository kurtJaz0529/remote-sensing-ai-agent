"""Native ENVI ML + smoothing; frozen existing samples and independent recomputation."""
import argparse
import json
from pathlib import Path
import numpy as np
from case_audit import CLASS_NAMES,TRAIN_HASH,TEST_HASH,digest,read_cube,read_samples,audit_samples,training_statistics,gaussian_reference,confusion_metrics,read_classification,separability


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--input',required=True)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    source=Path(args.input);out=Path(args.output)
    train_path=source.parent/'train_roi.csv';test_path=source.parent/'test_roi.csv'
    if out.exists() or digest(train_path)!=TRAIN_HASH or digest(test_path)!=TEST_HASH:
        raise ValueError('Output exists or frozen sample files differ')
    cube=read_cube(source)
    train=read_samples(train_path,640,400,True);test=read_samples(test_path,640,400,False)
    audit=audit_samples(train,test,640,400)
    means,covs,reg=training_statistics(cube,train)
    separation=separability(means,covs)
    audit['separability']=separation
    if not separation['all_guide_jm_qualified']:
        audit['warnings'].append('Some training class pairs do not meet the guide JM>1.9 criterion. Formal training acceptance is not passed; this run remains diagnostic.')
    predicted=gaussian_reference(cube,means,covs)
    out.mkdir(parents=True)
    (out/'sample-audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    from envipyengine import Engine
    engine=Engine('ENVI')
    task=engine.task('MaximumLikelihoodClassification')
    # IDL first dimension is band; JSON outer dimension represents class.
    params=dict(INPUT_RASTER=dict(factory='URLRaster',url=str(source)),MEAN=means.tolist(),COVARIANCE=covs.tolist(),CLASS_NAMES=CLASS_NAMES,THRESHOLD_PROBABILITY=[0.0],OUTPUT_RASTER_URI=str(out/'maximum-likelihood.dat'),OUTPUT_RULE_RASTER_URI=str(out/'rules.dat'))
    (out/'effective-parameters.json').write_text(json.dumps(dict(threshold_probability=[0.0],prior='equal',regularization=reg,mean=means.tolist(),covariance=covs.tolist(),sample_covariance_ddof=1,implementation='native ENVI MaximumLikelihoodClassification'),ensure_ascii=False,indent=2),encoding='utf-8')
    task.execute(params)
    labels=read_classification(out/'maximum-likelihood.dat',(400,640))
    differences=int(np.count_nonzero(labels!=predicted))
    (out/'native-reference-check.json').write_text(json.dumps({'pixel_differences':differences,'total_pixels':labels.size,'reference':'independent Gaussian discriminant, same frozen moments; not independent ground truth'}),encoding='utf-8')
    if differences:
        raise ValueError('Native output differs from independent reference; do not tune on test labels')
    smooth=engine.task('ClassificationSmoothing')
    smooth.execute(dict(INPUT_RASTER=dict(factory='URLRaster',url=str(out/'maximum-likelihood.dat')),KERNEL_SIZE=3,OUTPUT_RASTER_URI=str(out/'majority.dat')))
    majority=read_classification(out/'majority.dat',(400,640))
    metrics={}
    for name,raster in [('maximum_likelihood',labels),('majority_3x3',majority)]:
        metric=confusion_metrics(test[:,0],raster[test[:,2],test[:,1]])
        metric['all_image_unclassified_rate']=float(np.mean(raster==0))
        metric['class_pixel_counts']=[int(np.count_nonzero(raster==c)) for c in range(7)]
        metrics[name]=metric
    (out/'diagnostic-metrics.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2),encoding='utf-8')
    if digest(train_path)!=TRAIN_HASH or digest(test_path)!=TEST_HASH:
        raise ValueError('Samples changed')
    read_cube(source)
    summary=dict(software='ENVI',version='5.6',readback_equal=True,scope='native classification and smoothing with reused diagnostic test points; no new independent accuracy',native_reference_differences=differences,training_pixels=audit['training_pixels'],test_pixels=audit['test_pixels'],classification_codes=list(range(7)),smoothing_kernel=3,checks=[{'check_id':name,'passed':True} for name in ['native-readback','sample-buffer','native-gaussian-match','diagnostic-matrix']])
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':main()
