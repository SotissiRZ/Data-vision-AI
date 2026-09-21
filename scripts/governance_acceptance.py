#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,os,subprocess,sys
from pathlib import Path
EXPECTED_IDS=["unified_control_plane","effective_role_matrix","fail_closed_scope","publication_readiness","audit_digest","governance_snapshots","ai_model_governance","control_plane_ui"]
def inspect(root:Path)->dict:
    errors=[]; path=root/'compliance/GOVERNANCE_ACCEPTANCE.json'
    if not path.is_file(): return {'status':'fail','errors':['Missing compliance/GOVERNANCE_ACCEPTANCE.json']}
    payload=json.loads(path.read_text(encoding='utf-8')); version=(root/'VERSION').read_text().strip()
    if payload.get('product_version')!=version: errors.append('manifest version mismatch')
    items=payload.get('items') or []
    if [x.get('id') for x in items]!=EXPECTED_IDS: errors.append('Governance acceptance items do not match v2.55 contract')
    for item in items:
        for field in ('evidence','tests'):
            vals=item.get(field) or []
            if not vals: errors.append(f"{item.get('id')}: no {field}")
            for rel in vals:
                if not (root/rel).is_file(): errors.append(f"{item.get('id')}: missing {rel}")
    return {'product':payload.get('product'),'version':version,'items':len(items),'status':'pass' if not errors else 'fail','errors':errors}
def run_tests(root:Path):
    env=dict(os.environ);env['PYTHONPATH']=str(root/'backend')
    cmd=[sys.executable,'-m','pytest','-q','tests/test_governance_control_v2550.py','tests/test_frontend_governance_v2550.py']
    done=subprocess.run(cmd,cwd=root/'backend',env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    return done.returncode,done.stdout
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',default='.');ap.add_argument('--check',action='store_true');ap.add_argument('--json',action='store_true');args=ap.parse_args();root=Path(args.root).resolve();result=inspect(root);output=''
    if args.check and result['status']=='pass':
        code,output=run_tests(root);result['runtime_test']='pass' if code==0 else 'fail'
        if code: result['status']='fail';result['errors'].append('Executable governance tests failed')
    if args.json: print(json.dumps(result,ensure_ascii=False,indent=2))
    else:
        print(f"Governance acceptance: {result['status'].upper()} ({result.get('items',0)}/8 items)")
        for e in result.get('errors',[]): print('- '+e)
        if output: print(output.rstrip())
    return 0 if result['status']=='pass' else 1
if __name__=='__main__': raise SystemExit(main())
