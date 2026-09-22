#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def check(root: Path) -> list[tuple[str, bool]]:
    service = (root / 'backend/app/services/storytelling.py').read_text(encoding='utf-8')
    report = (root / 'backend/app/services/report_builder.py').read_text(encoding='utf-8')
    routes = (root / 'backend/app/api/routes/datasets.py').read_text(encoding='utf-8')
    contracts = (root / 'backend/app/assistant/contracts.py').read_text(encoding='utf-8')
    api = (root / 'frontend/lib/api.ts').read_text(encoding='utf-8')
    page = (root / 'frontend/app/page.tsx').read_text(encoding='utf-8')
    tests = root / 'backend/tests/test_storytelling_v272.py'
    return [
        ('deterministic multi-page story engine', 'build_story_blueprint' in service and 'datavision_storytelling_v272' in service),
        ('claim evidence linking', 'evidence_ids' in service and 'proof_coverage' in service),
        ('audience objective tone controls', 'AUDIENCES' in service and 'TONES' in service and 'objective' in service),
        ('multi-format story rendering', 'kind == "story_page"' in report and "kind==\"story_page\"" in report),
        ('governed immutable publication', 'publish_report' in report and 'immutable_report' in report and 'publication_gate' in routes),
        ('story preview and publish API', '/storytelling/preview' in routes and '/reports/{report_id}/publish' in routes),
        ('assistant and frontend controls', 'story_audience' in contracts and 'previewStorytelling' in api and 'Data Storytelling avancé' in page),
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
        'product_version': (root / 'VERSION').read_text(encoding='utf-8').strip(),
        'passed': passed,
        'total': len(rows),
        'checks': checks,
    }
    (root / 'compliance/STORYTELLING_ACCEPTANCE.json').write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + '\n', encoding='utf-8'
    )
    for name, ok in rows:
        print(f"{'PASS' if ok else 'FAIL'} · {name}")
    print(f"STORYTELLING_ACCEPTANCE {passed}/{len(rows)}")
    if args.check and passed != len(rows):
        return 2
    if args.check:
        proc = subprocess.run(
            [sys.executable, '-m', 'pytest', '-q', 'backend/tests/test_storytelling_v272.py'],
            cwd=root,
            env={**os.environ, 'PYTHONPATH': str(root / 'backend')},
        )
        return proc.returncode
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
