"""Manifest-bound archive and restore; refuses links, extras and overwrites."""
import json
import shutil
import stat
from pathlib import Path, PurePosixPath, PureWindowsPath
from zipfile import ZipFile, ZIP_DEFLATED
from contracts import sha256, within
from .evidence import audit_bundle


def pack(root, destination):
    root, destination = Path(root).resolve(), Path(destination).resolve()
    proof = audit_bundle(root)
    manifest = json.loads((root/'manifest.json').read_text(encoding='utf-8'))
    paths = ['manifest.json'] + [e['relative_path'] for e in manifest['files']]
    if destination.is_relative_to(root):
        raise ValueError('Archive must be outside the run')
    with destination.open('xb') as stream:
        with ZipFile(stream,'w',ZIP_DEFLATED) as archive:
            for relative in paths:
                path = root / relative
                if any(p.is_symlink() for p in [path,*path.parents]) or not path.is_file():
                    raise ValueError('Archive links rejected')
                archive.write(path,relative)
    return dict(**proof,archive_sha256=sha256(destination))


def restore(archive_path, destination, expected_sha256):
    archive_path, destination = Path(archive_path), Path(destination).absolute()
    if sha256(archive_path) != expected_sha256 or destination.exists():
        raise ValueError('Archive digest mismatch or target already exists')
    for parent in destination.parents:
        if parent.is_symlink():
            raise ValueError('Restore parent link rejected')
    with ZipFile(archive_path) as archive:
        entries = archive.infolist()
        names = [e.filename for e in entries]
        if len(names) != len(set(names)) or 'manifest.json' not in names:
            raise ValueError('Ambiguous archive')
        for entry in entries:
            path = PurePosixPath(entry.filename)
            reserved = {'CON','PRN','AUX','NUL'}|{'COM'+str(i) for i in range(1,10)}|{'LPT'+str(i) for i in range(1,10)}
            bad_component = any(':' in part or part.rstrip(' .')!=part or part.split('.')[0].upper() in reserved for part in path.parts)
            if path.as_posix()!=entry.filename or bad_component or path.is_absolute() or '..' in path.parts or '\\' in entry.filename or PureWindowsPath(entry.filename).drive or stat.S_ISLNK(entry.external_attr >> 16) or entry.is_dir():
                raise ValueError('Unsafe archive entry')
        if len({name.casefold() for name in names}) != len(names):
            raise ValueError('Case-colliding archive entries')
        manifest = json.loads(archive.read('manifest.json'))
        expected = {e['relative_path']:e for e in manifest['files']}
        if len(expected)!=len(manifest['files']) or set(names) != set(expected)|{'manifest.json'}:
            raise ValueError('Archive differs from manifest')
        if any(archive.getinfo(name).file_size != item['size'] for name,item in expected.items()):
            raise ValueError('Archive size mismatch')
        destination.mkdir(parents=True)
        for name in names:
            path = within(destination,name)
            path.parent.mkdir(parents=True,exist_ok=True)
            with archive.open(name) as source, path.open('xb') as output:
                shutil.copyfileobj(source,output,1024*1024)
    # Failed integrity leaves the new target for investigation; never overwrite/retry it.
    return audit_bundle(destination)
