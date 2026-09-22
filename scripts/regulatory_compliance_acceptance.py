#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from pathlib import Path

CHECKS = [
    ("control_catalog", "backend/app/services/regulatory_compliance.py", ["CATALOG_VERSION", "nist-csf-2.0", "iso27001-2022", "soc2-security", "certification_claim"]),
    ("posture_history", "backend/app/services/regulatory_compliance.py", ["capture_posture_snapshot", "posture_history", "compliant_percent", "managed_percent"]),
    ("governed_exceptions", "backend/app/services/regulatory_compliance.py", ["create_exception", "decide_exception", "expires_at", "compensating_controls"]),
    ("assisted_remediation", "backend/app/services/regulatory_compliance.py", ["remediation_plan", "proposal_only", "requires_human_approval"]),
    ("exportable_evidence", "backend/app/services/regulatory_compliance.py", ["datavision-regulatory-evidence-v2", "ZipFile", "controls.csv", "sha256"]),
    ("enterprise_api", "backend/app/api/routes/enterprise.py", ["/regulatory/posture", "/regulatory/exceptions", "/regulatory/evidence-pack", "FileResponse"]),
    ("governance_ui", "frontend/components/RegulatoryCompliancePanel.tsx", ["Conformité stricte", "Exceptions gouvernées", "Remédiation assistée", "Télécharger"]),
    ("schema_and_tests", "backend/tests/test_regulatory_compliance_v2650.py", ["excepted", "proposal_only", "manifest.json", "controls.csv"]),
]

def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument('--root',default='.'); ap.add_argument('--check',action='store_true'); args=ap.parse_args()
    root=Path(args.root).resolve(); results=[]
    for name, rel, needles in CHECKS:
        path=root/rel; text=path.read_text(encoding='utf-8') if path.exists() else ''; missing=[n for n in needles if n not in text]
        results.append({'id':name,'ok':path.exists() and not missing,'missing':missing,'path':rel})
    passed=sum(1 for r in results if r['ok'])
    print(f"REGULATORY_COMPLIANCE_ACCEPTANCE: {passed}/{len(results)}")
    for r in results: print(('PASS' if r['ok'] else 'FAIL'),r['id'],'' if r['ok'] else r['missing'])
    manifest=root/'compliance/REGULATORY_COMPLIANCE_ACCEPTANCE.json'
    manifest.write_text(json.dumps({'product_version':(root/'VERSION').read_text().strip(),'passed':passed,'total':len(results),'checks':results},indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    return 0 if passed==len(results) else 1

if __name__=='__main__': raise SystemExit(main())
