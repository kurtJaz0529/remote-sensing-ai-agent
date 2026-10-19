"""Closed native registry and trusted environment configuration."""
import json
from pathlib import Path
from contracts import VERSION, fingerprint, sha256, within

REGISTRY = {
    'envi.subset_probe': ('ENVI','5.6','envi_probe.py'),
    'arcgis.copy_probe': ('ArcGIS Pro','3.6','arcpy_probe.py'),
    'matlab.mean_probe': ('MATLAB','9.12.0.1884302','matlab_probe.m'),
    'envi.classification_case': ('ENVI','5.6','envi_classification_case.py'),
    'envi.rgb_case': ('ENVI','5.6','envi_rgb_case.py'),
}
PROBE_NAMES = tuple(name for name in REGISTRY if name.endswith('_probe'))
AUXILIARY_FILES = ('case_audit.py','raster_io.py')


def validate_case_scope(job,plan):
    if job['tool']=='envi.classification_case' and plan['evaluation_kind']!='diagnostic':
        raise ValueError('Existing case labels permit diagnostic reassessment only, not independent accuracy')


def tool(name):
    software, version, _ = REGISTRY[name]
    return dict(schema_revision=VERSION,name=name,version=version,description=software+' fixed registered user case verification only',side_effects=True,parameters={'type':'object','properties':{'source_relative':{'type':'string','minLength':1}},'required':['source_relative'],'additionalProperties':False},implementation_kind='native')


def configuration(root, plan):
    config = json.loads((Path(root)/'native-config.json').read_text(encoding='utf-8'))
    if plan['frozen_versions'].get('native_config_sha256') != fingerprint(config):
        raise ValueError('Native environment config not frozen in confirmation')
    files = {entry[2] for entry in REGISTRY.values()} | set(AUXILIARY_FILES)
    for filename in files:
        script = Path(__file__).resolve().parents[1]/'adapters'/filename
        if config['adapter_hashes'].get(filename) != sha256(script):
            raise ValueError('Adapter changed; new plan confirmation required')
    return config


def source_path(job, manifest, input_root):
    relative = job['parameters']['source_relative']
    registered = {f['relative_path']:f for f in manifest['files']}
    if job.get('tool')=='envi.rgb_case':
        expected='47ab7191fa82b78795269082f1de33fd38cf6e20679dc90ed3e3a87c57f49688'
        if relative not in registered or registered[relative]['sha256']!=expected:
            raise ValueError('Unregistered second RGB case')
        path=within(input_root,relative)
        if sha256(path)!=expected:raise ValueError('Second RGB case changed')
        return path
    if relative not in registered or registered[relative]['sha256'] != '121f1268c855ace06edd642ff191ff04da74499df3ff70c69c8b8bcee11345e5':
        raise ValueError('Only registered fixed-case input is supported')
    path = within(input_root, relative)
    if sha256(path) != registered[relative]['sha256']:
        raise ValueError('Native input changed')
    # All file sidecars must also have been registered and checked by preflight.
    hdr = path.with_suffix('.hdr').relative_to(Path(input_root).resolve()).as_posix()
    if hdr not in registered or registered[hdr]['sha256'] != '01298e3ea14ded47c21c99f657be3105d74263bbcf1b2457e08f091e99d882ef':
        raise ValueError('Unknown or unregistered header')
    if job['tool']=='envi.classification_case':
        from adapters.case_audit import TRAIN_HASH, TEST_HASH
        for name,expected in [('train_roi.csv',TRAIN_HASH),('test_roi.csv',TEST_HASH)]:
            relative_sample = path.with_name(name).relative_to(Path(input_root).resolve()).as_posix()
            if relative_sample not in registered or registered[relative_sample]['sha256']!=expected or sha256(within(input_root,relative_sample))!=expected:
                raise ValueError('Unknown or changed training/evaluation samples')
    return path


def command(config, name, source, output):
    _, _, filename = REGISTRY[name]
    script = Path(__file__).resolve().parents[1]/'adapters'/filename
    if name == 'matlab.mean_probe':
        quote = lambda x: str(x).replace("'", "''")
        code = "addpath('%s');matlab_probe('%s','%s');" % (quote(script.parent),quote(source),quote(output))
        return [config['matlab_executable'],'-batch',code]
    args = [config['envi_python' if name.startswith('envi.') else 'arcgis_python'],str(script),'--input',str(source),'--output',str(output)]
    if name.startswith('arcgis.'):
        template = Path(config['arcgis_template'])
        if sha256(template) != config['arcgis_template_sha256']:
            raise ValueError('Project template changed')
        args += ['--template',str(template)]
    return args
