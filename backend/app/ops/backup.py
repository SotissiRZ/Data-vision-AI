from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.services.backup_service import (
    create_backup,
    download_backup_from_object_store,
    inspect_backup,
    latest_backup_archive,
    restore_backup,
    run_restore_drill,
    upload_backup_to_object_store,
    replicate_backup_to_targets,
    list_backup_replications,
    replication_targets_status,
    verify_backup_replications,
)


def _print(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description="DataVision backup / restore / restore-drill utility")
    sub = parser.add_subparsers(dest="action", required=True)

    create = sub.add_parser("create")
    create.add_argument("--label", default="scheduled")

    inspect = sub.add_parser("inspect")
    inspect.add_argument("archive")

    upload = sub.add_parser("upload")
    upload.add_argument("archive")

    download = sub.add_parser("download")
    download.add_argument("object_key")

    replicate = sub.add_parser("replicate")
    replicate.add_argument("archive")
    replicate.add_argument("--backup-id", default=None)
    sub.add_parser("replication-status")
    repl_list = sub.add_parser("replications")
    repl_list.add_argument("--backup-id", default=None)
    repl_list.add_argument("--limit", type=int, default=100)
    repl_verify = sub.add_parser("verify-replications")
    repl_verify.add_argument("backup_id")

    drill = sub.add_parser("drill")
    drill.add_argument("archive")
    sub.add_parser("drill-latest")

    restore = sub.add_parser("restore")
    restore.add_argument("archive")
    restore.add_argument("--confirm", action="store_true")

    args = parser.parse_args()
    if args.action == "create":
        _print(create_backup(label=args.label))
    elif args.action == "inspect":
        _print(inspect_backup(Path(args.archive)))
    elif args.action == "upload":
        _print(upload_backup_to_object_store(Path(args.archive)))
    elif args.action == "download":
        _print({"archive": str(download_backup_from_object_store(args.object_key))})
    elif args.action == "replicate":
        _print(replicate_backup_to_targets(Path(args.archive), backup_id=args.backup_id))
    elif args.action == "replication-status":
        _print(replication_targets_status())
    elif args.action == "replications":
        _print({"replications": list_backup_replications(backup_id=args.backup_id, limit=args.limit)})
    elif args.action == "verify-replications":
        _print(verify_backup_replications(args.backup_id))
    elif args.action == "drill":
        _print(run_restore_drill(Path(args.archive)))
    elif args.action == "drill-latest":
        _print(run_restore_drill(latest_backup_archive()))
    elif args.action == "restore":
        _print(restore_backup(Path(args.archive), confirm=bool(args.confirm)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
