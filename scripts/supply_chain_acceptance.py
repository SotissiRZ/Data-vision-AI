#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from pathlib import Path

CHECKS = [
    ("provenance_generator", "scripts/generate_provenance.py", ["in-toto.io/Statement/v1", "slsa.dev/provenance/v1", "sbom-index.json"]),
    ("deployment_policy_rego", "policies/kubernetes/datavision.rego", ["deny[msg]", ":latest", "CHANGE_ME", "resource limits"]),
    ("policy_ci", ".github/workflows/ci.yml", ["deployment_policy_check.py", "policies/kubernetes"]),
    ("signed_release", ".github/workflows/release.yml", ["cosign", "sign-blob", "actions/attest@v4"]),
    ("signed_images", ".github/workflows/release.yml", ["docker/build-push-action", "cosign sign --yes", "provenance: mode=max"]),
    ("secret_rotation", "backend/app/services/operational_security.py", ["rotate_due_secrets", "eligible_for_automatic_rotation", "secret.auto_rotate"]),
    ("rollback_confirmation", "backend/app/services/operational_security.py", ["create_rollback_plan", "confirm_rollback", "confirmation_token_hash"]),
    ("helm_rotation_job", "deploy/helm/datavision/templates/secret-rotation-cronjob.yaml", ["concurrencyPolicy: Forbid", "rotate-secrets", "--confirm"]),
]

def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument('--root',default='.'); ap.add_argument('--check',action='store_true'); args=ap.parse_args()
    root=Path(args.root).resolve(); results=[]
    for name, rel, needles in CHECKS:
        path=root/rel; ok=path.exists(); missing=[]
        text=path.read_text(encoding='utf-8') if ok else ''
        for n in needles:
            if n not in text: missing.append(n)
        ok=ok and not missing
        results.append({'id':name,'ok':ok,'missing':missing,'path':rel})
    passed=sum(1 for r in results if r['ok'])
    print(f"SUPPLY_CHAIN_ACCEPTANCE: {passed}/{len(results)}")
    for r in results: print(('PASS' if r['ok'] else 'FAIL'), r['id'], '' if r['ok'] else r['missing'])
    manifest=root/'compliance/SUPPLY_CHAIN_ACCEPTANCE.json'
    manifest.write_text(json.dumps({'product_version':(root/'VERSION').read_text().strip(),'passed':passed,'total':len(results),'checks':results},indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    return 0 if passed==len(results) else 1

if __name__=='__main__': raise SystemExit(main())
