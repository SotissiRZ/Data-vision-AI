#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, os, subprocess, sys
from pathlib import Path

EXPECTED_IDS = [
    "distributed_trace_context", "trace_query_api", "alertmanager_multichannel", "trace_export_pipeline",
    "verified_cross_region_replication", "multi_cluster_control_plane", "two_phase_failover", "executable_sre_runbooks",
]

def inspect(root: Path) -> dict:
    errors=[]; path=root/"compliance/DISTRIBUTED_OPS_ACCEPTANCE.json"
    if not path.is_file(): return {"status":"fail","errors":["Missing compliance/DISTRIBUTED_OPS_ACCEPTANCE.json"]}
    payload=json.loads(path.read_text(encoding="utf-8")); version=(root/"VERSION").read_text(encoding="utf-8").strip()
    if payload.get("product_version") != version: errors.append("manifest version mismatch")
    items=payload.get("items") or []
    if [item.get("id") for item in items] != EXPECTED_IDS: errors.append("Distributed ops acceptance items mismatch")
    for item in items:
        for field in ("evidence","tests"):
            values=item.get(field) or []
            if not values: errors.append(f"{item.get('id')}: no {field}")
            for rel in values:
                if not (root/rel).is_file(): errors.append(f"{item.get('id')}: missing {rel}")
    return {"product":payload.get("product"),"version":version,"items":len(items),"status":"pass" if not errors else "fail","errors":errors}

def main()->int:
    ap=argparse.ArgumentParser(); ap.add_argument("--root",default="."); ap.add_argument("--check",action="store_true"); ap.add_argument("--json",action="store_true"); args=ap.parse_args()
    root=Path(args.root).resolve(); result=inspect(root); output=""
    if args.check and result["status"]=="pass":
        env=dict(os.environ); env["PYTHONPATH"]=str(root/"backend")
        done=subprocess.run([sys.executable,"-m","pytest","-q","tests/test_distributed_operations_v2620.py"],cwd=root/"backend",env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        output=done.stdout
        if done.returncode: result["status"]="fail"; result["errors"].append("Executable distributed operations tests failed")
    if args.json: print(json.dumps(result,ensure_ascii=False,indent=2))
    else:
        print(f"Distributed ops acceptance: {result['status'].upper()} ({result.get('items',0)}/8 items)")
        for error in result.get("errors",[]): print("- "+error)
        if output: print(output.rstrip())
    return 0 if result["status"]=="pass" else 1
if __name__=="__main__": raise SystemExit(main())
