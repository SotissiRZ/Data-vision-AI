from __future__ import annotations

import argparse
import json

from app.services.operational_security import (
    confirm_rollback,
    create_rollback_plan,
    rollback_drill,
    rotate_due_secrets,
    secret_rotation_status,
)


def _print(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description="DataVision operational security runbooks")
    sub = parser.add_subparsers(dest="action", required=True)

    rotation_status = sub.add_parser("rotation-status")
    rotation_status.add_argument("--workspace-id", default=None)

    rotate = sub.add_parser("rotate-secrets")
    rotate.add_argument("--workspace-id", default=None)
    rotate.add_argument("--actor-id", default="system:secret-rotation")
    rotate.add_argument("--confirm", action="store_true")

    plan = sub.add_parser("rollback-plan")
    plan.add_argument("target_version")
    plan.add_argument("--actor-id", required=True)
    plan.add_argument("--reason", required=True)
    plan.add_argument("--artifact-sha256", default="")

    confirm = sub.add_parser("rollback-confirm")
    confirm.add_argument("plan_id")
    confirm.add_argument("--actor-id", required=True)
    confirm.add_argument("--token", required=True)

    drill = sub.add_parser("rollback-drill")
    drill.add_argument("target_version")
    drill.add_argument("--actor-id", required=True)
    drill.add_argument("--artifact-sha256", default="")

    args = parser.parse_args()
    if args.action == "rotation-status":
        _print(secret_rotation_status(args.workspace_id))
    elif args.action == "rotate-secrets":
        _print(rotate_due_secrets(args.actor_id, workspace_id=args.workspace_id, confirm=args.confirm))
    elif args.action == "rollback-plan":
        _print(create_rollback_plan(args.actor_id, target_version=args.target_version, reason=args.reason, artifact_sha256=args.artifact_sha256))
    elif args.action == "rollback-confirm":
        _print(confirm_rollback(args.actor_id, plan_id=args.plan_id, confirmation_token=args.token))
    elif args.action == "rollback-drill":
        _print(rollback_drill(args.actor_id, target_version=args.target_version, artifact_sha256=args.artifact_sha256))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
