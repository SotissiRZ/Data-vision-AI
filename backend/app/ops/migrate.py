from __future__ import annotations

import argparse
import json

from app.core.config import get_settings
from app.services.metadata_store import get_engine
from app.services.schema_migrations import apply_pending_migrations, migration_status


def main() -> int:
    parser = argparse.ArgumentParser(description="DataVision schema migration utility")
    parser.add_argument("action", choices=("status", "apply"), nargs="?", default="status")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.action == "apply":
        engine = get_engine()
        with engine.begin() as conn:
            applied = apply_pending_migrations(conn)
        payload = {"applied_now": applied, **migration_status()}
    else:
        payload = migration_status()

    print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else payload)
    return 0 if payload.get("ready") else 2


if __name__ == "__main__":
    raise SystemExit(main())
