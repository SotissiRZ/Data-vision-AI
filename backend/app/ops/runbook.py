from __future__ import annotations

import argparse
import json

from app.services.backup_service import verify_backup_replications
from app.services.multi_cluster import cluster_topology_status, confirm_failover, create_failover_plan, list_failovers
from app.services.sre_operations import run_dr_drill, sre_status


def _print(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description="DataVision SRE executable runbooks")
    sub = parser.add_subparsers(dest="action", required=True)

    status = sub.add_parser("sre-status")
    status.add_argument("workspace_id")
    status.add_argument("--hours", type=int, default=24)

    topology = sub.add_parser("topology")
    topology.add_argument("workspace_id")

    history = sub.add_parser("failovers")
    history.add_argument("workspace_id")
    history.add_argument("--limit", type=int, default=50)

    plan = sub.add_parser("failover-plan")
    plan.add_argument("workspace_id")
    plan.add_argument("target_cluster_id")
    plan.add_argument("--actor-id", required=True)
    plan.add_argument("--reason", default="operator requested failover")

    confirm = sub.add_parser("failover-confirm")
    confirm.add_argument("workspace_id")
    confirm.add_argument("plan_id")
    confirm.add_argument("--actor-id", required=True)
    confirm.add_argument("--token", required=True)

    verify = sub.add_parser("verify-replications")
    verify.add_argument("backup_id")

    drill = sub.add_parser("dr-drill")
    drill.add_argument("workspace_id")
    drill.add_argument("--actor-id", required=True)
    drill.add_argument("--organization-id", default=None)
    drill.add_argument("--mode", choices=["continuity", "restore_only"], default="continuity")

    args = parser.parse_args()
    if args.action == "sre-status":
        _print(sre_status(args.workspace_id, hours=args.hours))
    elif args.action == "topology":
        _print(cluster_topology_status(args.workspace_id))
    elif args.action == "failovers":
        _print({"failovers": list_failovers(args.workspace_id, limit=args.limit)})
    elif args.action == "failover-plan":
        _print(create_failover_plan(args.actor_id, args.workspace_id, target_cluster_id=args.target_cluster_id, reason=args.reason))
    elif args.action == "failover-confirm":
        _print(confirm_failover(args.actor_id, args.workspace_id, plan_id=args.plan_id, confirmation_token=args.token))
    elif args.action == "verify-replications":
        _print(verify_backup_replications(args.backup_id))
    elif args.action == "dr-drill":
        _print(run_dr_drill(args.actor_id, args.workspace_id, organization_id=args.organization_id, mode=args.mode))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
