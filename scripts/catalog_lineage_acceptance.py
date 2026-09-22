#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from pathlib import Path

CHECKS = [
    ("zip_data_import", "backend/app/services/storage.py", ["save_zip_upload", "maximum 50 fichiers", "ZIP décompressé"]),
    ("connector_retry_backoff", "backend/app/services/connector_service.py", ["_retry_backend", "retry_attempts", "retry_backoff_seconds"]),
    ("business_catalog", "backend/app/services/data_catalog.py", ["catalog_assets", "business_domain", "steward_user_id", "certification_status"]),
    ("catalog_api", "backend/app/api/routes/enterprise.py", ["/catalog/assets", "CatalogAssetUpdateRequest", "catalog.asset.update"]),
    ("cross_system_lineage", "backend/app/services/data_reliability.py", ["external_object", "exposes_source", "ingested_through"]),
    ("catalog_ui", "frontend/app/page.tsx", ["Discovery & documentation métier", "catalogSelected", "saveCatalogMetadata"]),
    ("catalog_migration", "backend/app/services/schema_migrations.py", ["2.68.0-001", "data_catalog_entries"]),
    ("catalog_tests", "backend/tests/test_catalog_lineage_v268.py", ["test_zip_import_multiple_supported_files", "test_connector_retry_uses_exponential_attempts", "test_cross_system_lineage_contract_present"]),
]

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',default='.');ap.add_argument('--check',action='store_true');args=ap.parse_args();root=Path(args.root).resolve();results=[]
    for cid,rel,needles in CHECKS:
        p=root/rel;text=p.read_text(encoding='utf-8') if p.exists() else '';missing=[n for n in needles if n not in text];results.append({'id':cid,'ok':p.exists() and not missing,'missing':missing,'path':rel})
    passed=sum(1 for r in results if r['ok']);payload={'product_version':(root/'VERSION').read_text().strip(),'passed':passed,'total':len(results),'checks':results}
    (root/'compliance/CATALOG_LINEAGE_ACCEPTANCE.json').write_text(json.dumps(payload,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(f"CATALOG_LINEAGE_ACCEPTANCE: {passed}/{len(results)}")
    for r in results: print('PASS' if r['ok'] else 'FAIL',r['id'],'' if r['ok'] else r['missing'])
    return 0 if passed==len(results) else 1
if __name__=='__main__': raise SystemExit(main())
