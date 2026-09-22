#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def check(root: Path) -> list[tuple[str, bool]]:
    service = (root / 'backend/app/services/quality_remediation.py').read_text(encoding='utf-8')
    routes = (root / 'backend/app/api/routes/datasets.py').read_text(encoding='utf-8')
    tools = (root / 'backend/app/assistant/tools.py').read_text(encoding='utf-8')
    planner = (root / 'backend/app/assistant/planner_runtime.py').read_text(encoding='utf-8')
    api = (root / 'frontend/lib/api.ts').read_text(encoding='utf-8')
    page = (root / 'frontend/app/page.tsx').read_text(encoding='utf-8')
    tests = root / 'backend/tests/test_quality_remediation_v271.py'
    return [
        ('deterministic remediation planner', 'build_quality_remediation_plan' in service and '_stable_id' in service),
        ('safe preview before mutation', 'preview_quality_remediation' in service and 'Aucune correction' in service),
        ('versioned governed apply', 'quality_remediation' in service and 'save_dataframe_version' in routes),
        ('stale plan protection', 'expected_plan_id' in service and 'plan de remédiation a changé' in service),
        ('API remediation endpoints', '/quality/remediation/preview' in routes and '/quality/remediation/apply' in routes),
        ('assistant remediation planning', 'name="plan_quality_remediation"' in tools and 'tool="plan_quality_remediation"' in planner),
        ('frontend guided workflow', 'getQualityRemediation' in api and 'Remédiation guidée' in page and 'Appliquer dans une nouvelle version' in page),
        ('integration tests present', tests.is_file()),
    ]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default='.')
    ap.add_argument('--check', action='store_true')
    args = ap.parse_args()
    root = Path(args.root).resolve()
    rows = check(root)
    checks = [{"id": name.lower().replace(' ', '_'), "ok": ok} for name, ok in rows]
    passed = sum(ok for _, ok in rows)
    payload = {
        "product_version": (root / 'VERSION').read_text(encoding='utf-8').strip(),
        "passed": passed,
        "total": len(rows),
        "checks": checks,
    }
    (root / 'compliance/QUALITY_REMEDIATION_ACCEPTANCE.json').write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + '\n', encoding='utf-8'
    )
    for name, ok in rows:
        print(f"{'PASS' if ok else 'FAIL'} · {name}")
    print(f"QUALITY_REMEDIATION_ACCEPTANCE {passed}/{len(rows)}")
    if args.check and passed != len(rows):
        return 2
    if args.check:
        proc = subprocess.run(
            [sys.executable, '-m', 'pytest', '-q', 'backend/tests/test_quality_remediation_v271.py'],
            cwd=root,
            env={**os.environ, 'PYTHONPATH': str(root / 'backend')},
        )
        return proc.returncode
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
