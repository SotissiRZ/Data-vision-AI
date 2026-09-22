from __future__ import annotations

import argparse
import json

from app.services.continuous_compliance import create_evidence_pack, run_compliance_scan
from app.services.metadata_store import fetch_all


def _print(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description="DataVision continuous compliance runbooks")
    sub = parser.add_subparsers(dest="action", required=True)

    scan = sub.add_parser("scan")
    scan.add_argument("--workspace-id", default=None)
    scan.add_argument("--all", action="store_true")
    scan.add_argument("--actor-id", default="system:continuous-compliance")

    evidence = sub.add_parser("evidence")
    evidence.add_argument("--workspace-id", default=None)
    evidence.add_argument("--actor-id", default="system:compliance-evidence")

    args = parser.parse_args()
    if args.action == "scan":
        if args.all:
            workspaces = [str(r["id"]) for r in fetch_all("SELECT id FROM workspaces ORDER BY id")]
            _print({"results": [run_compliance_scan(args.actor_id, workspace_id=ws) for ws in workspaces]})
        else:
            _print(run_compliance_scan(args.actor_id, workspace_id=args.workspace_id))
    elif args.action == "evidence":
        _print(create_evidence_pack(args.actor_id, workspace_id=args.workspace_id))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
