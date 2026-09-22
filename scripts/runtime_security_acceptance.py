#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from pathlib import Path

CHECKS = [
    ("continuous_compliance_service", "backend/app/services/continuous_compliance.py", ["run_compliance_scan", "create_evidence_pack", "sha256"]),
    ("runtime_event_ingestion", "backend/app/services/continuous_compliance.py", ["record_runtime_security_event", "runtime_security_events"]),
    ("admission_signature_policy", "deploy/helm/datavision/templates/admission-policy.yaml", ["verifyImages", "keyless", "validationFailureAction: Enforce"]),
    ("runtime_hardening", "deploy/helm/datavision/templates/api.yaml", ["runAsNonRoot", "readOnlyRootFilesystem", "allowPrivilegeEscalation", "ALL"]),
    ("falco_rules", "deploy/helm/datavision/templates/falco-rules.yaml", ["DataVision Shell Spawned", "Sensitive Path Write", "Package Manager Execution"]),
    ("continuous_scan_cron", "deploy/helm/datavision/templates/compliance-cronjob.yaml", ["concurrencyPolicy: Forbid", "app.ops.compliance", "--all"]),
    ("policy_as_code_runtime", "policies/kubernetes/datavision.rego", ["RuntimeDefault", "runAsNonRoot", "allowPrivilegeEscalation", "drop ALL capabilities"]),
    ("evidence_runbook", "backend/app/ops/compliance.py", ["scan", "evidence", "system:continuous-compliance"]),
]

def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument('--root',default='.'); ap.add_argument('--check',action='store_true'); args=ap.parse_args()
    root=Path(args.root).resolve(); results=[]
    for name, rel, needles in CHECKS:
        path=root/rel; ok=path.exists(); missing=[]; text=path.read_text(encoding='utf-8') if ok else ''
        for n in needles:
            if n not in text: missing.append(n)
        ok=ok and not missing
        results.append({'id':name,'ok':ok,'missing':missing,'path':rel})
    passed=sum(1 for r in results if r['ok'])
    print(f"RUNTIME_SECURITY_ACCEPTANCE: {passed}/{len(results)}")
    for r in results: print(('PASS' if r['ok'] else 'FAIL'), r['id'], '' if r['ok'] else r['missing'])
    manifest=root/'compliance/RUNTIME_SECURITY_ACCEPTANCE.json'
    manifest.write_text(json.dumps({'product_version':(root/'VERSION').read_text().strip(),'passed':passed,'total':len(results),'checks':results},indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    return 0 if passed==len(results) else 1

if __name__=='__main__': raise SystemExit(main())
