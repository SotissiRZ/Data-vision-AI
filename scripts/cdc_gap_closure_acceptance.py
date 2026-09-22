#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def checks(root: Path):
    version = (root / 'VERSION').read_text(encoding='utf-8').strip()
    plans = (root / 'backend/app/services/product_plans.py').read_text(encoding='utf-8')
    enterprise = (root / 'backend/app/api/routes/enterprise.py').read_text(encoding='utf-8')
    assistant = (root / 'backend/app/assistant/router.py').read_text(encoding='utf-8')
    crypto = (root / 'backend/app/services/secret_crypto.py').read_text(encoding='utf-8')
    causal = (root / 'backend/app/services/causal_inference.py').read_text(encoding='utf-8')
    proactive = (root / 'backend/app/services/proactive_intelligence.py').read_text(encoding='utf-8')
    worker = (root / 'backend/app/worker.py').read_text(encoding='utf-8')
    migrations = (root / 'backend/app/services/schema_migrations.py').read_text(encoding='utf-8')
    helm = (root / 'deploy/helm/datavision/Chart.yaml').read_text(encoding='utf-8')
    matrix = json.loads((root / 'compliance/CDC_COVERAGE_MATRIX.json').read_text(encoding='utf-8'))
    statuses = {int(r['section']): r['status'] for r in matrix['requirements']}
    test = 'backend/tests/test_cdc_gap_closure_v278.py'
    doc = 'docs/compliance/CDC_GAP_CLOSURE_V2780.md'
    return [
        ('product plan catalog and persistent assignment', all(x in plans for x in ('PLAN_CATALOG', 'assign_organization_plan', 'organization_plan_assignments')), ['backend/app/services/product_plans.py'], [test]),
        ('runtime entitlement and quota enforcement', 'consume_daily_quota' in assistant and 'assert_plan_feature' in enterprise and 'plan_usage_daily' in plans, ['backend/app/assistant/router.py','backend/app/api/routes/enterprise.py','backend/app/services/product_plans.py'], [test]),
        ('native cloud kms envelope encryption', all(x in crypto for x in ('aws_kms','gcp_kms','azure_key_vault','AESGCM.generate_key','_cloud_wrap_key','_cloud_unwrap_key')), ['backend/app/services/secret_crypto.py','.env.example'], [test]),
        ('observational causal estimator with explicit guardrail', 'estimate_ate' in causal and 'causal_claim_allowed' in causal and 'Estimation observationnelle' in causal, ['backend/app/services/causal_inference.py','backend/app/api/routes/datasets.py'], [test]),
        ('persistent proactive scheduler and safe worker claim', 'proactive_scan_schedules' in migrations and 'claim_due_scan_schedules' in proactive and '_enqueue_due_proactive_scans' in worker, ['backend/app/services/proactive_intelligence.py','backend/app/worker.py','backend/app/services/schema_migrations.py'], [test]),
        ('enterprise v2 deployment evidence retained', f'version: {version}' in helm and (root/'backend/app/services/multi_cluster.py').is_file() and (root/'backend/app/assistant/agents.py').is_file(), ['deploy/helm/datavision/Chart.yaml','backend/app/services/multi_cluster.py','backend/app/assistant/agents.py'], [test]),
        ('cdc sections 46 66 70 closed', statuses.get(46)=='implemented' and statuses.get(66)=='implemented' and statuses.get(70)=='implemented', ['compliance/CDC_COVERAGE_MATRIX.json'], [test]),
        ('external acceptance boundaries remain explicit', statuses.get(71)=='partial' and statuses.get(74)=='partial' and (root/doc).is_file(), [doc,'compliance/CDC_COVERAGE_MATRIX.json'], [test]),
    ]


def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument('--root', default='.')
    parser.add_argument('--check', action='store_true')
    args=parser.parse_args()
    root=Path(args.root).resolve()
    rows=checks(root)
    version=(root/'VERSION').read_text(encoding='utf-8').strip()
    items=[{'id':n.lower().replace(' ','_'),'ok':bool(ok),'evidence':e,'tests':t} for n,ok,e,t in rows]
    payload={
        'product':'DataVision AI','product_version':version,
        'passed':sum(i['ok'] for i in items),'total':len(items),'items':items,
        'note':'Internal CDC gap-closure acceptance. Target-environment execution and signed business UAT remain external evidence and are intentionally not self-certified.'
    }
    (root/'compliance/CDC_GAP_CLOSURE_ACCEPTANCE.json').write_text(json.dumps(payload,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    for i in items: print(f"{'PASS' if i['ok'] else 'FAIL'} · {i['id']}")
    print(f"CDC_GAP_CLOSURE_ACCEPTANCE {payload['passed']}/{payload['total']}")
    if args.check and payload['passed'] != payload['total']: return 2
    if args.check:
        proc=subprocess.run([sys.executable,'-m','pytest','-q','backend/tests/test_cdc_gap_closure_v278.py'], cwd=root, env={**os.environ,'PYTHONPATH':str(root/'backend')})
        return proc.returncode
    return 0


if __name__=='__main__':
    raise SystemExit(main())
