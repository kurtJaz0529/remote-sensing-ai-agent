"""Closed native registry and trusted environment configuration."""
import json
from pathlib import Path
from contracts import VERSION, fingerprint, sha256, within

REGISTRY = {
    'envi.subset_probe': ('ENVI','5.6','envi_probe.py'),
    'arcgis.copy_probe': ('ArcGIS Pro','3.6','arcpy_probe.py'),
    'matlab.mean_probe': ('MATLAB','9.12.0.1884302','matlab_probe.m'),
}


def tool(name):
    software, version, _ = REGISTRY[name]
    return dict(schema_revision=VERSION,name=name,version=version,description=software+' fixed registered Canon City verification only',side_effects=True,parameters={'type':'object','properties':{'source_relative':{'type':'string','minLength':1}},'required':['source_relative'],'additionalProperties':False},implementation_kind='native')


def configuration(root, plan):
    config = json.loads((Path(root)/'native-config.json').read_text(encoding='utf-8'))
    if plan['frozen_versions'].get('native_config_sha256') != fingerprint(config):
        raise ValueError('Native environment config not frozen in confirmation')
    for name, (_, _, filename) in REGISTRY.items():
        script = Path(__file__).resolve().parents[1]/'adapters'/filename
        if config['adapter_hashes'].get(filename) != sha256(script):
            raise ValueError('Adapter changed; new plan confirmation required')
    return config


def source_path(job, manifest, input_root):
    relative = job['parameters']['source_relative']
    registered = {f['relative_path']:f for f in manifest['files']}
    if relative not in registered or registered[relative]['sha256'] != '121f1268c855ace06edd642ff191ff04da74499df3ff70c69c8b8bcee11345e5':
        raise ValueError('Only registered fixed-case input is supported')
    path = within(input_root, relative)
    if sha256(path) != registered[relative]['sha256']:
        raise ValueError('Native input changed')
    # All file sidecars must also have been registered and checked by preflight.
    hdr = path.with_suffix('.hdr').relative_to(Path(input_root).resolve()).as_posix()
    if hdr not in registered or registered[hdr]['sha256'] != '01298e3ea14ded47c21c99f657be3105d74263bbcf1b2457e08f091e99d882ef':
        raise ValueError('Unknown or unregistered header')
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
