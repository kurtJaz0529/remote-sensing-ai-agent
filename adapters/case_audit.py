"""Fixed-case scientific checks. Evaluation is diagnostic, never held-out accuracy."""
import csv
import hashlib
import re
from pathlib import Path
import numpy as np

CLASS_NAMES = ['耕地','有林地','建设用地','水域','裸地','其他']
INPUT_HASH = '121f1268c855ace06edd642ff191ff04da74499df3ff70c69c8b8bcee11345e5'
HEADER_HASH = '01298e3ea14ded47c21c99f657be3105d74263bbcf1b2457e08f091e99d882ef'
TRAIN_HASH = '413f9ecb1b3073eac4de1b2e166a4ecf41ef3aa38799337fc304c8850d3f736b'
TEST_HASH = 'fbc9327e912011f1658c717840720b73f9cbcf34ff304b908043a79becaa3fdd'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_cube(path):
    path = Path(path)
    if digest(path)!=INPUT_HASH or digest(path.with_suffix('.hdr'))!=HEADER_HASH:
        raise ValueError('Registered image/header mismatch')
    return np.fromfile(path,dtype=np.uint8).reshape(6,400,640).transpose(1,2,0)


def read_samples(path, width, height, training):
    rows=[];seen=set()
    with Path(path).open(encoding='utf-8-sig',newline='') as stream:
        for row in csv.DictReader(stream):
            c,x,y=int(row['class_id']),int(row['column']),int(row['row'])
            if not (1<=c<=6 and 1<=x<=width and 1<=y<=height):
                raise ValueError('Sample class/coordinate out of bounds')
            if row['class_name']!=CLASS_NAMES[c-1] or (x,y) in seen:
                raise ValueError('Class mapping conflict or duplicate coordinate')
            seen.add((x,y))
            rows.append((c,x-1,y-1,int(row['region_id']) if training else 0))
            if training and rows[-1][3]<=0:
                raise ValueError('Training region IDs must be positive')
    if not rows or set(r[0] for r in rows)!=set(range(1,7)):
        raise ValueError('Every class needs registered samples')
    return np.asarray(rows,dtype=np.int64)


def audit_samples(train, test, width, height, buffer=5):
    # Validate caller-created arrays as well as CSV intake.
    for arr in (train,test):
        if arr.ndim!=2 or arr.shape[1]!=4 or arr.dtype.kind not in 'iu' or np.any(arr[:,0]<1) or np.any(arr[:,0]>6) or np.any(arr[:,1]<0) or np.any(arr[:,1]>=width) or np.any(arr[:,2]<0) or np.any(arr[:,2]>=height):
            raise ValueError('Invalid sample array')
        if len(np.unique(arr[:,1:3],axis=0))!=len(arr):
            raise ValueError('Duplicate sample coordinates')
    violations=0
    for _,x,y,_ in test:
        violations+=int(np.count_nonzero((np.abs(train[:,1]-x)<=buffer)&(np.abs(train[:,2]-y)<=buffer)))
    if violations:
        raise ValueError('Training enters the evaluation exclusion buffer')
    counts=[int(np.count_nonzero(train[:,0]==c)) for c in range(1,7)]
    regions=[len(np.unique(train[train[:,0]==c,3])) for c in range(1,7)]
    if min(counts)<100 or min(regions)<8:
        raise ValueError('Insufficient training pixels/regions')
    return dict(training_pixels=counts,training_regions=regions,test_pixels=[int(np.count_nonzero(test[:,0]==c)) for c in range(1,7)],buffer_chebyshev_pixels=buffer,buffer_violations=0,classification_units='stored uint8 values; no calibrated reflectance claim',crs='unknown',area_unit='pixel squared',nodata='not declared; zero is not automatically masked',evaluation_kind='diagnostic_reassessment',warnings=['Existing test labels have already been inspected in earlier work; not an independent holdout.','Training semantic labels still require independent image interpretation.'])


def training_statistics(cube, train):
    means=[];covariances=[];regularization=[]
    for c in range(1,7):
        points=train[train[:,0]==c]
        pixels=cube[points[:,2],points[:,1],:].astype(np.float64)
        cov=np.cov(pixels,rowvar=False,ddof=1)
        reg=max(1e-6,float(np.trace(cov))/cube.shape[2]*1e-4)
        means.append(pixels.mean(axis=0));covariances.append(cov+np.eye(cube.shape[2])*reg);regularization.append(reg)
    return np.asarray(means),np.asarray(covariances),regularization


def gaussian_reference(cube, means, covariances):
    x=cube.reshape(-1,cube.shape[2]).astype(np.float64)
    scores=[]
    for mean,cov in zip(means,covariances):
        delta=x-mean
        sign,logdet=np.linalg.slogdet(cov)
        if sign<=0:raise ValueError('Non-positive covariance')
        # Explicit solve differs from the native ENVI implementation.
        scores.append(-.5*logdet-.5*np.sum(delta*np.linalg.solve(cov,delta.T).T,axis=1))
    return (np.argmax(scores,axis=0)+1).astype(np.uint8).reshape(cube.shape[:2])


def separability(means,covariances):
    pairs=[]
    for a in range(len(means)):
        for b in range(a+1,len(means)):
            ca,cb=covariances[a],covariances[b];avg=(ca+cb)/2;d=means[a]-means[b]
            bhattacharyya=float(d@np.linalg.solve(avg,d))/8+(.5*np.linalg.slogdet(avg)[1]-.25*(np.linalg.slogdet(ca)[1]+np.linalg.slogdet(cb)[1]))
            divergence=.5*float(np.trace((ca-cb)@(np.linalg.inv(cb)-np.linalg.inv(ca))))+.5*float(d@(np.linalg.solve(ca,d)+np.linalg.solve(cb,d)))
            jm=float(2*(-np.expm1(-max(bhattacharyya,0))));td=float(2*(-np.expm1(-max(divergence,0)/8)))
            pairs.append(dict(class_a=a+1,class_b=b+1,jm=jm,td=td,guide_jm_qualified=jm>1.9,guide_reselection_required=jm<1.8))
    return dict(pairs=pairs,all_guide_jm_qualified=all(p['guide_jm_qualified'] for p in pairs),minimum_jm=min(p['jm'] for p in pairs),scope='regularized sample moments in stored units; separability does not establish semantic label validity')


def confusion_metrics(reference,prediction):
    reference=np.asarray(reference);prediction=np.asarray(prediction)
    if reference.shape!=prediction.shape or reference.ndim!=1 or reference.size==0 or reference.dtype.kind not in 'iu' or prediction.dtype.kind not in 'iu' or np.any(reference<1) or np.any(reference>6) or np.any(prediction<0) or np.any(prediction>6):
        raise ValueError('Invalid reference or prediction labels')
    matrix=np.zeros((6,7),dtype=np.int64)
    np.add.at(matrix,(reference.astype(int)-1,prediction.astype(int)),1)
    n=int(matrix.sum());correct=int(sum(matrix[c-1,c] for c in range(1,7)))
    rows=matrix.sum(axis=1);columns=matrix.sum(axis=0)
    expected=float(sum(rows[c-1]*columns[c] for c in range(1,7)))/(n*n)
    pa=[float(matrix[c-1,c]/rows[c-1]) if rows[c-1] else None for c in range(1,7)]
    ua=[float(matrix[c-1,c]/columns[c]) if columns[c] else None for c in range(1,7)]
    return dict(matrix=matrix.tolist(),rows='reference class 1..6',columns='predicted class 0..6; 0=unclassified',n=n,overall_accuracy=correct/n,kappa=(correct/n-expected)/(1-expected) if expected<1 else None,producer_accuracy=pa,user_accuracy=ua,test_unclassified_rate=float(columns[0]/n),evaluation_kind='diagnostic_reassessment')


def read_classification(path,shape):
    path=Path(path);text=path.with_suffix('.hdr').read_text(encoding='utf-8')
    for key,value in [('samples',str(shape[1])),('lines',str(shape[0])),('bands','1'),('data type','1'),('header offset','0')]:
        if not re.search(r'^'+key+r'\s*=\s*'+value+r'\s*$',text,re.M|re.I):
            raise ValueError('Unexpected native classification header')
    labels=np.fromfile(path,dtype=np.uint8)
    if labels.size!=shape[0]*shape[1] or np.any(labels>6):
        raise ValueError('Native classification size/codes mismatch')
    return labels.reshape(shape)
