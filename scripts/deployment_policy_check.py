#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

REQUIRED = {
    'deploy/helm/datavision/templates/api.yaml': ['resources:', 'startupProbe:', 'readinessProbe:', 'livenessProbe:'],
    'deploy/helm/datavision/templates/web.yaml': ['resources:', 'startupProbe:', 'readinessProbe:', 'livenessProbe:'],
    'deploy/helm/datavision/values.yaml': ['existingSecret:', 'pullPolicy:', 'resources:'],
    'policies/kubernetes/datavision.rego': ['deny[msg]', 'resource limits', 'CHANGE_ME', 'LoadBalancer'],
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', default='.')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    root = Path(args.root).resolve()
    failures = []
    for rel, needles in REQUIRED.items():
        path = root / rel
        if not path.exists():
            failures.append(f'{rel}: missing')
            continue
        text = path.read_text(encoding='utf-8')
        for needle in needles:
            if needle not in text:
                failures.append(f'{rel}: missing {needle!r}')
    if failures:
        print('DEPLOYMENT_POLICY_CHECK: FAIL')
        for f in failures:
            print('-', f)
        return 1
    print('DEPLOYMENT_POLICY_CHECK: OK')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
