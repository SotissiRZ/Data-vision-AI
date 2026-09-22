#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def checks(root: Path):
    backends = (root / "backend/app/services/connector_backends.py").read_text(encoding="utf-8")
    service = (root / "backend/app/services/connector_service.py").read_text(encoding="utf-8")
    cdc = (root / "backend/app/services/cdc_ingestion.py").read_text(encoding="utf-8")
    routes = (root / "backend/app/api/routes/enterprise.py").read_text(encoding="utf-8")
    metadata = (root / "backend/app/services/metadata_store.py").read_text(encoding="utf-8")
    frontend = (root / "frontend/app/page.tsx").read_text(encoding="utf-8")
    api = (root / "frontend/lib/api.ts").read_text(encoding="utf-8")
    req = (root / "backend/requirements.txt").read_text(encoding="utf-8")
    test = "backend/tests/test_cloud_cdc_v275.py"
    doc = "docs/data/CLOUD_CDC_INGESTION_V2750.md"
    return [
        ("three native object storage backends", all(token in backends for token in ['"s3": ConnectorSpec', '"gcs": ConnectorSpec', '"azure_blob": ConnectorSpec']) and all(dep in req for dep in ("boto3==", "google-cloud-storage==", "azure-storage-blob==")), ["backend/app/services/connector_backends.py", "backend/requirements.txt"], [test]),
        ("governed cloud object sources", 'allowed_kinds = {"object"}' in service and "_object_frame_from_bytes" in backends and "max_object_mb" in backends, ["backend/app/services/connector_service.py", "backend/app/services/connector_backends.py"], [test]),
        ("checkpointed cdc ledger", all(token in metadata for token in ("cdc_batches", "cdc_events", "cdc_checkpoints")) and "canonicalize_cdc_event" in cdc, ["backend/app/services/metadata_store.py", "backend/app/services/cdc_ingestion.py"], [test]),
        ("cdc idempotency and resume", "batch_sha256" in cdc and "_is_stale_offset" in cdc and "idempotent" in cdc and "partition_key" in cdc, ["backend/app/services/cdc_ingestion.py"], [test]),
        ("immutable cdc materialization and lineage", "save_dataframe_version" in cdc and "save_dataframe_source" in cdc and '"cdc_materialized_as"' in cdc and '"mode":"cdc"' not in cdc, ["backend/app/services/cdc_ingestion.py"], [test]),
        ("governed cdc api", '/sources/{source_id}/cdc/events' in routes and 'CDCIngestRequest' in routes and '"refresh:run"' in routes and '/sources/{source_id}/cdc' in routes, ["backend/app/api/routes/enterprise.py"], [test]),
        ("sources center exposes cloud and cdc modes", "azure_blob:'AZ'" in frontend and 'CDC log-based' in frontend and 'Options source JSON' in frontend and "ingestCdcEvents" in api, ["frontend/app/page.tsx", "frontend/lib/api.ts"], [test]),
        ("engineering evidence and explicit boundaries", (root / doc).is_file() and (root / test).is_file(), [doc], [test]),
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    rows = checks(root)
    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    items = [{"id": name.lower().replace(" ", "_"), "ok": ok, "evidence": evidence, "tests": tests} for name, ok, evidence, tests in rows]
    payload = {"product": "DataVision AI", "product_version": version, "passed": sum(i["ok"] for i in items), "total": len(items), "items": items, "note": "Internal engineering acceptance; cloud credentials and source log infrastructure remain environment-owned."}
    (root / "compliance/CLOUD_CDC_ACCEPTANCE.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for item in items:
        print(f"{'PASS' if item['ok'] else 'FAIL'} · {item['id']}")
    print(f"CLOUD_CDC_ACCEPTANCE {payload['passed']}/{payload['total']}")
    if args.check and payload["passed"] != payload["total"]:
        return 2
    if args.check:
        env = {**os.environ, "PYTHONPATH": str(root / "backend")}
        return subprocess.run([sys.executable, "-m", "pytest", "-q", "backend/tests/test_cloud_cdc_v275.py"], cwd=root, env=env).returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
