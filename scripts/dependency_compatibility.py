#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path


def parse_pin(lines: list[str], package: str) -> tuple[int, ...] | None:
    rx = re.compile(rf"^{re.escape(package)}==([0-9]+(?:\.[0-9]+)*)$", re.I)
    for raw in lines:
        line = raw.strip()
        m = rx.match(line)
        if m:
            return tuple(int(x) for x in m.group(1).split('.'))
    return None


def check(root: Path) -> list[str]:
    errors: list[str] = []
    req = root / 'backend' / 'requirements.txt'
    if not req.is_file():
        return ['Missing backend/requirements.txt']
    lines = [x.strip() for x in req.read_text(encoding='utf-8').splitlines() if x.strip() and not x.lstrip().startswith('#')]
    if len(lines) != len(set(lines)):
        errors.append('Duplicate exact requirement lines detected')
    boto3 = parse_pin(lines, 'boto3')
    redshift = parse_pin(lines, 'redshift-connector')
    if redshift == (2, 1, 16):
        if boto3 is None:
            errors.append('redshift-connector 2.1.16 requires an explicit compatible boto3 pin')
        elif boto3 < (1, 42, 22):
            errors.append(f'boto3 {".".join(map(str,boto3))} conflicts with redshift-connector 2.1.16; require >=1.42.22')
    if boto3 is not None and boto3 >= (2, 0, 0):
        errors.append('redshift-connector 2.1.16 requires boto3 <2.0.0')
    return errors


def main() -> int:
    ap = argparse.ArgumentParser(description='Static compatibility checks for pinned DataVision dependencies.')
    ap.add_argument('--root', default='.')
    ap.add_argument('--check', action='store_true')
    args = ap.parse_args()
    errors = check(Path(args.root).resolve())
    if errors:
        print('Dependency compatibility: FAIL')
        for e in errors:
            print(f'- {e}')
        return 1
    print('Dependency compatibility: OK')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
