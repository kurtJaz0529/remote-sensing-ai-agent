"""Versioned JSON contracts and canonical fingerprints."""
import hashlib
import json
from importlib.resources import files
from pathlib import Path, PurePosixPath, PureWindowsPath
from jsonschema import Draft202012Validator, FormatChecker

VERSION = "0.1.0"

def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)

def fingerprint(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()

def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def schema(name):
    return json.loads(files("contracts").joinpath(name + ".schema.json").read_text())

def validate(name, value):
    Draft202012Validator(schema(name), format_checker=FormatChecker()).validate(value)
    return value

def within(root, relative):
    """Resolve only portable relative paths, including Windows traversal guards."""
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ValueError("expected POSIX relative path")
    p, w = PurePosixPath(relative), PureWindowsPath(relative)
    if p.is_absolute() or w.drive or ".." in p.parts:
        raise ValueError("path escapes root")
    root = Path(root).resolve()
    result = (root / relative).resolve()
    if not result.is_relative_to(root):
        raise ValueError("symlink escapes root")
    return result
