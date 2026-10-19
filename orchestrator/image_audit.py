"""Read-only registered PNG structural audit; no image classification or editing."""
import json
import struct
import zlib
from pathlib import Path
from contracts import fingerprint, within
from .engine import Engine
from .intake import check_inputs


def png_structure(path):
    data=Path(path).read_bytes()
    if not data.startswith(b'\x89PNG\r\n\x1a\n'):
        return {'status':'invalid','reason':'PNG signature missing','size':len(data)}
    offset=8;first=True;has_data=False;ended=False;metadata={}
    try:
        while offset<len(data):
            length=struct.unpack_from('>I',data,offset)[0]
            kind=data[offset+4:offset+8];end=offset+12+length
            if len(kind)!=4 or end>len(data):raise ValueError('Truncated PNG chunk')
            payload=data[offset+8:offset+8+length]
            crc=struct.unpack_from('>I',data,offset+8+length)[0]
            if zlib.crc32(kind+payload)&0xffffffff!=crc:raise ValueError('PNG CRC mismatch')
            if first:
                if kind!=b'IHDR' or length!=13:raise ValueError('Missing IHDR')
                w,h,depth,color,compression,filtering,interlace=struct.unpack('>IIBBBBB',payload)
                if not w or not h or compression or filtering or interlace not in (0,1):raise ValueError('Invalid IHDR')
                metadata=dict(width=w,height=h,bit_depth=depth,color_type=color)
                first=False
            if kind==b'IDAT':has_data=True
            if kind==b'IEND':
                if length or end!=len(data):raise ValueError('Invalid IEND or trailing content')
                ended=True;break
            offset=end
        if not ended or not has_data:raise ValueError('Missing pixel data or IEND')
    except (ValueError,struct.error) as error:
        return dict(status='invalid',reason=str(error),size=len(data))
    return dict(status='structure_verified',**metadata,size=len(data),scope='PNG chunks and CRC only; pixel decoding, geographic metadata and semantic reference still require review')


def registered_image_audit(runtime,task_id,revision,approval_id):
    engine=Engine(runtime)
    try:
        row,plan,manifest=engine._plan(task_id,revision)
        approval=engine.store.db.execute('SELECT * FROM approvals WHERE id=?',(approval_id,)).fetchone()
        if approval is None or (approval['task'],approval['revision'],approval['plan_hash'],approval['manifest_hash'])!=(task_id,revision,fingerprint(plan),fingerprint(manifest)) or row['hash']!=fingerprint(plan):
            raise ValueError('Input audit confirmation mismatch')
        if not any(step['tool']=='local.registered_input_audit' and step['parameters']=={} and step['dataset_ids']==[manifest['dataset_id']] for step in plan['method_plan']):
            raise ValueError('Read-only input audit is not in confirmed plan')
        check_inputs(row['input_root'],manifest)
        pngs=[];repeated_image=[]
        known='121f1268c855ace06edd642ff191ff04da74499df3ff70c69c8b8bcee11345e5'
        for entry in manifest['files']:
            if entry['sha256']==known:repeated_image.append(entry['relative_path'])
            if entry['relative_path'].lower().endswith('.png'):
                pngs.append(dict(relative_path=entry['relative_path'],sha256=entry['sha256'],**png_structure(within(row['input_root'],entry['relative_path']))))
        return dict(task_id=task_id,plan_revision=revision,input_manifest_hash=fingerprint(manifest),registered_files=len(manifest['files']),png_count=len(pngs),invalid_png_count=sum(p['status']=='invalid' for p in pngs),pngs=pngs,repeated_canon_city_image_paths=repeated_image,scope='registered file structure audit only; no untouched holdout or new accuracy claim',warnings=['Previously processed files are not automatically independent holdouts.','RGB PNGs do not establish spectral band calibration or CRS.'])
    finally:engine.store.close()
