"""Hash only an explicitly selected user dataset; never copy or alter inputs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat


def _reject_link(path):
    info = path.lstat()
    if path.is_symlink() or getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
        raise ValueError('Links and reparse points are not accepted')


def build_manifest(root, dataset_id):
    root = Path(root).absolute()
    for ancestor in [root, *root.parents]:
        _reject_link(ancestor)
    if not root.is_dir() or not dataset_id.strip():
        raise ValueError('A dataset directory and nonempty ID are required')
    files = []
    for current, dirs, names in os.walk(root, followlinks=False):
        for name in sorted(dirs + names):
            _reject_link(Path(current) / name)
        for name in sorted(names):
            path = Path(current) / name
            if not path.is_file():
                raise ValueError('Only regular files are supported')
            before = path.stat()
            digest = hashlib.sha256()
            with path.open('rb') as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                    digest.update(chunk)
            after = path.stat()
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise ValueError('Input changed during inventory')
            files.append(dict(relative_path=path.relative_to(root).as_posix(), sha256=digest.hexdigest(), size=after.st_size))
    if not files:
        raise ValueError('No registered input files found')
    return dict(schema_revision='0.1.0', dataset_id=dataset_id, origin='user_provided', files=sorted(files, key=lambda f: f['relative_path']))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True)
    parser.add_argument('--dataset-id', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args(argv)
    root, output = Path(args.root).resolve(), Path(args.output).resolve()
    if output.is_relative_to(root):
        raise ValueError('Manifest output must be outside input root')
    manifest = build_manifest(args.root, args.dataset_id)
    with output.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
