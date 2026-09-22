#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
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
    'upgrade-windows.ps1',
}
LEGACY_PATTERNS = ('MERGE_MANIFEST_V', 'MIGRATION_FROM_')
LOCAL_ONLY_ROOT_FILES = {'.env'}


def _git_tracks(root: Path, name: str) -> bool:
    if not (root / '.git').exists():
        return False
    try:
        result = subprocess.run(
            ['git', '-C', str(root), 'ls-files', '--error-unmatch', '--', name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=5,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def check(root: Path) -> list[str]:
    errors: list[str] = []
    for path in root.iterdir():
        if not path.is_file():
            continue
        if path.name in LOCAL_ONLY_ROOT_FILES:
            if _git_tracks(root, path.name):
                errors.append(f'Sensitive local file must not be tracked: {path.name}')
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
    if not (root / 'docs' / 'development' / 'PROJECT_STRUCTURE.md').is_file():
        errors.append('Missing docs/development/PROJECT_STRUCTURE.md')
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
        legacy_names = {'manifest.json','pytest.ini','start.bat','MIGRATION_FROM_V212.md','MIGRATION_GUIDE.md','CDC_DataVision_AI.md'}
        if any(any(name in error for name in legacy_names) for error in errors):
            print(r'Remediation (Windows): powershell -ExecutionPolicy Bypass -File .\scripts\cleanup-legacy-root.ps1')
            print('Tip: extract each DataVision release into a clean directory; do not overlay archives.')
        return 1
    print('Repository hygiene: OK')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
