import io
import zipfile

from app.core.config import get_settings
from app.services.storage import save_zip_upload, get_meta
from app.services.connector_service import _retry_backend


def test_zip_import_multiple_supported_files(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)
    monkeypatch.setattr(settings, "max_upload_mb", 5)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("sales.csv", "id,amount\n1,10\n")
        zf.writestr("nested/customers.json", '[{"id":1,"name":"A"}]')
        zf.writestr("README.md", "ignored")
    items = save_zip_upload("bundle.zip", buf.getvalue())
    assert len(items) == 2
    assert {x["extension"] for x in items} == {".csv", ".json"}
    assert all(get_meta(x["id"])["archive"]["name"] == "bundle.zip" for x in items)


def test_zip_import_rejects_empty_supported_bundle(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)
    monkeypatch.setattr(settings, "max_upload_mb", 5)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("notes.md", "no data")
    try:
        save_zip_upload("bundle.zip", buf.getvalue())
    except ValueError as exc:
        assert "aucun fichier de données" in str(exc)
    else:
        raise AssertionError("ZIP without supported data should fail")


def test_connector_retry_uses_exponential_attempts(monkeypatch):
    connector = {"options": {"retry_attempts": 3, "retry_backoff_seconds": 0}}
    calls = {"n": 0}
    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("temporary")
        return {"ok": True}
    value, attempts = _retry_backend(connector, "test", flaky)
    assert value["ok"] is True
    assert attempts == 3
    assert calls["n"] == 3



def test_business_catalog_persists_metadata(tmp_path, monkeypatch):
    import app.services.metadata_store as metadata_store
    import app.services.data_catalog as data_catalog
    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'metadata.db'}")
    monkeypatch.setattr(settings, "metadata_fallback_sqlite", True)
    metadata_store._ENGINES.clear(); metadata_store._SELECTED_BACKENDS.clear()
    meta = __import__('app.services.storage', fromlist=['save_upload']).save_upload('sales.csv', b'id,amount\n1,10\n')
    metadata_store.execute("INSERT INTO workspace_datasets(workspace_id,dataset_id,bound_by,created_at) VALUES(:ws,:ds,:user,:at)", {"ws":"ws-1","ds":meta["id"],"user":"u-1","at":metadata_store.utcnow()})
    saved = data_catalog.save_catalog_entry('u-1','ws-1','dataset',meta['id'], title='Ventes certifiées', description='Dataset métier ventes', business_domain='Finance', tags=['ventes','finance'], certification_status='certified')
    assert saved['certification_status'] == 'certified'
    found = data_catalog.catalog_assets('ws-1', query='finance')
    assert found['count'] == 1
    assert found['assets'][0]['title'] == 'Ventes certifiées'
    assert found['assets'][0]['lineage']['downstream'] >= 0

def test_catalog_frontend_contract_present():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    api = (root / "frontend/lib/api.ts").read_text(encoding="utf-8")
    page = (root / "frontend/app/page.tsx").read_text(encoding="utf-8")
    assert "getDataCatalogAssets" in api
    assert "Discovery & documentation métier" in page
    assert "saveDataCatalogAsset" in page


def test_cross_system_lineage_contract_present():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    rel = (root / "backend/app/services/data_reliability.py").read_text(encoding="utf-8")
    assert '"connector"' in rel
    assert '"external_object"' in rel
    assert '"exposes_source"' in rel
    assert '"ingested_through"' in rel
