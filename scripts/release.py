#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import zipfile

from verify_release import verify_archive

EXCLUDED_DIRS = {
    '.git', '.pytest_cache', '__pycache__',
    'node_modules', '.next', 'playwright-report', 'test-results',
    'dist', 'data',
}
EXCLUDED_FILES = {'.env', 'RELEASE_MANIFEST.json'}
FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def iter_files(root: Path):
    for path in sorted(root.rglob('*')):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(part in EXCLUDED_DIRS for part in rel.parts):
            continue
        if path.name in EXCLUDED_FILES or path.suffix in {'.pyc', '.tsbuildinfo'}:
            continue
        yield path, rel


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', default='.')
    parser.add_argument('--output', default='dist')
    args = parser.parse_args()

    root = Path(args.root).resolve()
    out = Path(args.output).resolve()
    out.mkdir(parents=True, exist_ok=True)
    version = (root / 'VERSION').read_text(encoding='utf-8').strip()
    name = f'datavision-ai-v{version}-complet'
    archive = out / f'{name}.zip'

    file_rows = []
    for path, rel in iter_files(root):
        file_rows.append({
            'path': rel.as_posix(),
            'sha256': sha256(path),
            'size': path.stat().st_size,
        })

    release_manifest = {
        'product': 'DataVision AI',
        'version': version,
        'format': 'reproducible-source-archive-v1',
        'files': file_rows,
    }
    manifest_bytes = (
        json.dumps(release_manifest, indent=2, ensure_ascii=False, sort_keys=True)
        + '\n'
    ).encode('utf-8')

    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path, rel in iter_files(root):
            info = zipfile.ZipInfo(f'{name}/{rel.as_posix()}', FIXED_ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, path.read_bytes())
        info = zipfile.ZipInfo(f'{name}/RELEASE_MANIFEST.json', FIXED_ZIP_TIME)
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o644 << 16
        zf.writestr(info, manifest_bytes)

    digest = sha256(archive)
    (out / f'{archive.name}.sha256').write_text(
        f'{digest}  {archive.name}\n', encoding='utf-8'
    )
    (out / 'release-manifest.json').write_bytes(manifest_bytes)
    verify_archive(archive, out / f'{archive.name}.sha256')
    print(archive)
    print(digest)


if __name__ == '__main__':
    main()
