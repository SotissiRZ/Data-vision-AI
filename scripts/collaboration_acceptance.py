#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, os, subprocess, sys
from pathlib import Path

EXPECTED_IDS = [
    "workspace_teams", "review_workflow", "comments_mentions_notifications", "realtime_websocket",
    "version_diff", "decision_ledger", "governed_artifact_sharing", "outgoing_governed_events",
]


def inspect(root: Path) -> dict:
    errors: list[str] = []
    path = root / "compliance/COLLABORATION_ACCEPTANCE.json"
    if not path.is_file():
        return {"status":"fail","errors":["Missing compliance/COLLABORATION_ACCEPTANCE.json"]}
    payload = json.loads(path.read_text(encoding="utf-8"))
    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    if payload.get("product_version") != version:
        errors.append(f"manifest version={payload.get('product_version')!r}, VERSION={version!r}")
    items = payload.get("items") or []
    if [x.get("id") for x in items] != EXPECTED_IDS:
        errors.append("Collaboration acceptance items do not match v2.54 contract")
    for item in items:
        for field in ("evidence", "tests"):
            values = item.get(field) or []
            if not values:
                errors.append(f"{item.get('id')}: no {field}")
            for rel in values:
                if not (root / rel).is_file():
                    errors.append(f"{item.get('id')}: missing {rel}")
    return {"product":payload.get("product"),"version":version,"items":len(items),"status":"pass" if not errors else "fail","errors":errors}


def run_tests(root: Path):
    env = dict(os.environ); env["PYTHONPATH"] = str(root / "backend")
    cmd = [sys.executable,"-m","pytest","-q","tests/test_collaboration_v2540.py","tests/test_frontend_collaboration_v2540.py","test_foundation.py","-k","v254 or v260"]
    done = subprocess.run(cmd,cwd=root/"backend",env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    return done.returncode, done.stdout


def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument("--root",default="."); ap.add_argument("--check",action="store_true"); ap.add_argument("--json",action="store_true"); args=ap.parse_args()
    root=Path(args.root).resolve(); result=inspect(root); output=""
    if args.check and result["status"]=="pass":
        code,output=run_tests(root); result["runtime_test"]="pass" if code==0 else "fail"
        if code:
            result["status"]="fail"; result["errors"].append("Executable collaboration tests failed")
    if args.json: print(json.dumps(result,ensure_ascii=False,indent=2))
    else:
        print(f"Collaboration acceptance: {result['status'].upper()} ({result.get('items',0)}/8 items)")
        for err in result.get("errors",[]): print("- "+err)
        if output: print(output.rstrip())
    return 0 if result["status"]=="pass" else 1

if __name__=="__main__": raise SystemExit(main())
