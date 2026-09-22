#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description='Generate DataVision release provenance and SBOM index')
    parser.add_argument('--root', default='.')
    parser.add_argument('--dist', default='dist')
    args = parser.parse_args()
    root = Path(args.root).resolve()
    dist = Path(args.dist).resolve()
    dist.mkdir(parents=True, exist_ok=True)
    version = (root / 'VERSION').read_text(encoding='utf-8').strip()
    archive = dist / f'datavision-ai-v{version}-complet.zip'
    if not archive.exists():
        raise SystemExit(f'Archive absente: {archive}')

    sboms = []
    for path in sorted(dist.glob('*')):
        if path.name.endswith(('.cdx.json', '.spdx.json')) and path.is_file():
            sboms.append({'name': path.name, 'sha256': sha256(path), 'size': path.stat().st_size})
    sbom_index = {
        'product': 'DataVision AI',
        'version': version,
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'sboms': sboms,
    }
    (dist / 'sbom-index.json').write_text(json.dumps(sbom_index, indent=2, sort_keys=True) + '\n', encoding='utf-8')

    subject = {'name': archive.name, 'digest': {'sha256': sha256(archive)}}
    statement = {
        '_type': 'https://in-toto.io/Statement/v1',
        'subject': [subject],
        'predicateType': 'https://slsa.dev/provenance/v1',
        'predicate': {
            'buildDefinition': {
                'buildType': 'https://github.com/datavision-ai/release/source-archive@v1',
                'externalParameters': {
                    'version': version,
                    'git_ref': os.getenv('GITHUB_REF', ''),
                    'git_sha': os.getenv('GITHUB_SHA', ''),
                    'repository': os.getenv('GITHUB_REPOSITORY', ''),
                },
                'resolvedDependencies': [],
            },
            'runDetails': {
                'builder': {'id': 'https://github.com/actions/runner'},
                'metadata': {
                    'invocationId': os.getenv('GITHUB_RUN_ID', ''),
                    'startedOn': datetime.now(timezone.utc).isoformat(),
                },
            },
        },
    }
    (dist / 'provenance.intoto.json').write_text(json.dumps(statement, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(dist / 'provenance.intoto.json')


if __name__ == '__main__':
    main()
