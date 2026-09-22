#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

ALLOWED_ROOT_FILES = {
    '.env.example',
    '.editorconfig',
    '.gitignore',
    '.dockerignore',
    'Makefile',
    'README.md',
    'RELEASE_MANIFEST.json',
    'SECURITY.md',
    'VERSION',
    'docker-compose.yml',
    'install-windows.ps1',
    'preflight-windows.ps1',
    'production-acceptance-windows.ps1',
    'rebuild-windows.ps1',
    'reset-docker.ps1',
    'start-datavision.ps1',
    'stop-datavision.ps1',
}
LEGACY_PATTERNS = ('MERGE_MANIFEST_V', 'MIGRATION_FROM_')


def check(root: Path) -> list[str]:
    errors: list[str] = []
    for path in root.iterdir():
        if not path.is_file():
            continue
        if path.name.startswith(LEGACY_PATTERNS):
            errors.append(f'Historical file must not live at repository root: {path.name}')
        elif path.name not in ALLOWED_ROOT_FILES:
            errors.append(f'Unexpected root file: {path.name}')

    manifests = root / 'docs' / 'history' / 'manifests'
    migrations = root / 'docs' / 'history' / 'migrations'
    if not manifests.is_dir():
        errors.append('Missing docs/history/manifests/')
    if not migrations.is_dir():
        errors.append('Missing docs/history/migrations/')
    if not (root / 'docs' / 'PROJECT_STRUCTURE.md').is_file():
        errors.append('Missing docs/PROJECT_STRUCTURE.md')
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description='Validate DataVision repository hygiene.')
    parser.add_argument('--root', default='.')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    root = Path(args.root).resolve()
    errors = check(root)
    if errors:
        print('Repository hygiene: FAIL')
        for error in errors:
            print(f'- {error}')
        return 1
    print('Repository hygiene: OK')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
