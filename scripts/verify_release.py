#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import zipfile


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('archive')
    parser.add_argument('--sha-file')
    args = parser.parse_args()
    archive = Path(args.archive)
    with zipfile.ZipFile(archive) as zf:
        bad = zf.testzip()
        if bad:
            raise SystemExit(f'Archive corrompue: {bad}')
    if args.sha_file:
        expected = Path(args.sha_file).read_text(encoding='utf-8').split()[0]
        actual = sha256(archive)
        if actual != expected:
            raise SystemExit(f'SHA256 invalide: {actual} != {expected}')
    print('release verification: OK')


if __name__ == '__main__':
    main()
