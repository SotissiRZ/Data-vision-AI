#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def check(root: Path) -> list[tuple[str, bool]]:
    engine=(root/'backend/app/services/automl_engine.py').read_text(encoding='utf-8')
    routes=(root/'backend/app/api/routes/datasets.py').read_text(encoding='utf-8')
    contracts=(root/'backend/app/assistant/contracts.py').read_text(encoding='utf-8')
    page=(root/'frontend/app/page.tsx').read_text(encoding='utf-8')
    tests=root/'backend/tests/test_automl_forecast_anomaly_v270.py'
    return [
        ('forecasting AutoML branch', 'task == "forecasting"' in engine and 'forecasting_automl' in engine),
        ('anomaly AutoML branch', 'task == "anomaly_detection"' in engine and 'anomaly_automl' in engine),
        ('rolling-origin validation', 'rolling_origin' in engine and 'selection_uses_future' in engine),
        ('unsupervised robustness selection', 'unsupervised_stability_agreement' in engine and 'ground_truth_used' in engine),
        ('API unified tasks', 'forecasting|anomaly_detection' in routes and 'quality_score' in routes),
        ('assistant unified contract', '"forecasting", "anomaly_detection"' in contracts),
        ('frontend unified workflow', 'Forecasting temporel' in page and 'Détection d’anomalies' in page and 'Score qualité' in page),
        ('integration tests present', tests.is_file()),
    ]


def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument('--root',default='.'); ap.add_argument('--check',action='store_true')
    args=ap.parse_args(); root=Path(args.root).resolve()
    rows=check(root)
    checks=[{"id": name.lower().replace(" ", "_"), "ok": ok} for name,ok in rows]
    passed=sum(ok for _,ok in rows)
    payload={"product_version":(root/"VERSION").read_text(encoding="utf-8").strip(),"passed":passed,"total":len(rows),"checks":checks}
    (root/"compliance/AUTOML_UNIFIED_ACCEPTANCE.json").write_text(json.dumps(payload,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    for name,ok in rows: print(f"{'PASS' if ok else 'FAIL'} · {name}")
    print(f"AUTOML_UNIFIED_ACCEPTANCE {passed}/{len(rows)}")
    if args.check and passed != len(rows): return 2
    if args.check:
        proc=subprocess.run([sys.executable,'-m','pytest','-q','backend/tests/test_automl_forecast_anomaly_v270.py'],cwd=root,env={**__import__('os').environ,'PYTHONPATH':str(root/'backend')})
        return proc.returncode
    return 0

if __name__=='__main__': raise SystemExit(main())
