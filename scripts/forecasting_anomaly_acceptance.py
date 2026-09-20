#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, os, subprocess, sys
from pathlib import Path
EXPECTED_IDS=["rolling_origin_backtest","forecast_model_benchmark","empirical_intervals","series_diagnostics","missing_period_governance","multi_method_anomaly","consensus_anomaly","assistant_forecast_anomaly"]
def inspect(root:Path)->dict:
    errors=[]; path=root/'compliance/FORECASTING_ANOMALY_ACCEPTANCE.json'
    if not path.is_file(): return {'status':'fail','errors':['Missing compliance/FORECASTING_ANOMALY_ACCEPTANCE.json']}
    payload=json.loads(path.read_text(encoding='utf-8')); version=(root/'VERSION').read_text(encoding='utf-8').strip()
    if payload.get('product_version')!=version: errors.append(f"manifest version={payload.get('product_version')!r}, VERSION={version!r}")
    items=payload.get('items') or []
    if [x.get('id') for x in items]!=EXPECTED_IDS: errors.append('Forecasting/Anomaly acceptance items do not match v2.53 contract')
    for item in items:
        for field in ('evidence','tests'):
            vals=item.get(field) or []
            if not vals: errors.append(f"{item.get('id')}: no {field}")
            for rel in vals:
                if not (root/rel).is_file(): errors.append(f"{item.get('id')}: missing {rel}")
    return {'product':payload.get('product'),'version':version,'items':len(items),'status':'pass' if not errors else 'fail','errors':errors}
def run_tests(root:Path):
    env=dict(os.environ); env['PYTHONPATH']=str(root/'backend')
    c=subprocess.run([sys.executable,'-m','pytest','-q','tests/test_forecasting_anomaly_v2530.py','test_foundation.py::test_v08_forecasting_anomalies_and_xai'],cwd=root/'backend',env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    return c.returncode,c.stdout
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--root',default='.'); ap.add_argument('--check',action='store_true'); ap.add_argument('--json',action='store_true'); a=ap.parse_args(); root=Path(a.root).resolve(); r=inspect(root); out=''
    if a.check and r['status']=='pass':
        code,out=run_tests(root); r['runtime_test']='pass' if code==0 else 'fail'
        if code: r['status']='fail'; r['errors'].append('Executable forecasting/anomaly tests failed')
    if a.json: print(json.dumps(r,ensure_ascii=False,indent=2))
    else:
        print(f"Forecasting/Anomaly acceptance: {r['status'].upper()} ({r.get('items',0)}/8 items)")
        for e in r.get('errors',[]): print('- '+e)
        if out: print(out.rstrip())
    return 0 if r['status']=='pass' else 1
if __name__=='__main__': raise SystemExit(main())
