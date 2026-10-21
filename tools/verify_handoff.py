#!/usr/bin/env python3
"""Verify the shared inputs and the configured June executable without running MOM6."""
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def main():
    baseline = json.loads((ROOT / 'provenance/baseline.json').read_text())
    errors = []
    for name, expected in baseline['inputs'].items():
        path = ROOT / name
        if not path.is_file() or sha256(path) != expected:
            errors.append('Missing or changed input: ' + name)
    match = re.search(r'^exe:\s*(.+?)\s*$', (ROOT / 'config.yaml').read_text(), re.M)
    if not match:
        errors.append('No executable configured in config.yaml')
    else:
        exe = Path(match.group(1).strip('\"\''))
        if not exe.is_absolute():
            exe = ROOT / exe
        if not exe.is_file() or sha256(exe) != baseline['executable']['sha256']:
            errors.append('Configured executable is missing, unreadable or differs from the June reference')
    for error in errors:
        print('FAIL: ' + error)
    if not errors:
        print('PASS: all {} input files and the configured executable match the June reference.'.format(len(baseline['inputs'])))
    return bool(errors)


if __name__ == '__main__':
    raise SystemExit(main())
