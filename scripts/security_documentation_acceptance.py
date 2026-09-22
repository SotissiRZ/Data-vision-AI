#!/usr/bin/env python3
from __future__ import annotations

import argparse, json
from pathlib import Path


def contains(path: Path, *needles: str) -> bool:
    if not path.is_file(): return False
    text = path.read_text(encoding='utf-8', errors='ignore')
    return all(n in text for n in needles)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default='.')
    ap.add_argument('--check', action='store_true')
    args = ap.parse_args()
    root = Path(args.root).resolve()
    version = (root/'VERSION').read_text().strip() if (root/'VERSION').is_file() else ''
    checks = [
        ('version_2816', version == '2.81.6'),
        ('auth_required_default', contains(root/'backend/app/core/config.py', 'auth_mode: str = "required"')),
        ('first_run_setup_local_only', contains(root/'backend/app/services/first_run_setup.py', 'local_first_run_allowed', 'COOKIE_NAME = "dv_first_run_setup"') and contains(root/'frontend/app/page.tsx', 'Inscription', 'Confirmer le mot de passe', 'registerEnterprise')), 
        ('local_dev_guarded', contains(root/'backend/app/services/tenant_access.py', 'settings.auth_mode == "local_dev"', 'settings.app_env.lower() != "production"')),
        ('browser_tokens_session_scoped', not contains(root/'frontend/app/page.tsx', "localStorage.setItem('dv_enterprise_token'") and contains(root/'frontend/app/page.tsx', "sessionStorage.setItem('dv_enterprise_token'")),
        ('api_docs_disabled_default', contains(root/'backend/app/core/config.py', 'api_docs_enabled: bool = False')),
        ('password_policy_configured', contains(root/'backend/app/core/config.py', 'password_min_length: int = 8', 'password_scrypt_n: int = 131072')),
        ('password_visibility_and_demo_account', contains(root/'frontend/app/page.tsx', 'password-eye', 'Se connecter avec le compte test') and contains(root/'backend/app/services/auth_service.py', 'demo_account_enabled', 'settings.app_env.lower() in {"development", "test"}') and contains(root/'.env.example', 'DEMO_ACCOUNT_ENABLED=true', 'DEMO_ACCOUNT_EMAIL=demo@datavision.local')),
        ('dependency_compatibility', contains(root/'backend/requirements.txt', 'boto3==1.42.22', 'redshift-connector==2.1.16')),
        ('rego_safe_capability_rule', contains(root/'policies/kubernetes/datavision.rego', 'drops_all_capabilities(c)') and not contains(root/'policies/kubernetes/datavision.rego', 'not c.securityContext.capabilities.drop[_] == "ALL"')),
        ('formal_documentation', all((root/p).is_file() for p in ['docs/RAPPORT_TECHNIQUE.md','docs/GUIDE_UTILISATEUR.md','docs/GUIDE_DEPLOIEMENT.md','docs/RAPPORT_SECURITE.md','docs/GUIDE_EXPLOITATION.md'])),
        ('security_hardening_audit', (root/'scripts/security_hardening_audit.py').is_file() and (root/'compliance'/'SECURITY_HARDENING_AUDIT.json').is_file()),
        ('container_least_privilege', contains(root/'backend/Dockerfile', 'USER 10001:10001') and contains(root/'frontend/Dockerfile', 'USER 10001:10001') and contains(root/'docker-compose.yml', 'cap_drop:', 'no-new-privileges:true')),
    ]
    passed = sum(bool(ok) for _,ok in checks)
    payload = {'gate':'SECURITY_DOCUMENTATION_ACCEPTANCE','version':version,'passed':passed,'total':len(checks),'status':'pass' if passed==len(checks) else 'fail','checks':[{'id':k,'passed':bool(v)} for k,v in checks]}
    out = root/'compliance'/'SECURITY_DOCUMENTATION_ACCEPTANCE.json'
    out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(payload,indent=2,ensure_ascii=False)+'\n')
    print(f"SECURITY_DOCUMENTATION_ACCEPTANCE: {payload['status'].upper()} {passed}/{len(checks)}")
    for k,v in checks: print(f"- {'PASS' if v else 'FAIL'} {k}")
    return 0 if payload['status']=='pass' else 1

if __name__ == '__main__': raise SystemExit(main())
