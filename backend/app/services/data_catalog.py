from __future__ import annotations

import uuid
from typing import Any

from app.services.data_reliability import build_lineage_graph
from app.services.metadata_store import execute, fetch_all, fetch_one, json_dumps, json_loads, utcnow
from app.services.storage import get_meta


def _ensure_tables() -> None:
    execute(
        """CREATE TABLE IF NOT EXISTS data_catalog_entries (
            id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            resource_type TEXT NOT NULL,
            resource_id TEXT NOT NULL,
            title TEXT,
            description TEXT,
            business_domain TEXT,
            owner_user_id TEXT,
            steward_user_id TEXT,
            tags_json TEXT,
            glossary_json TEXT,
            certification_status TEXT NOT NULL DEFAULT 'unreviewed',
            created_by TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(workspace_id, resource_type, resource_id)
        )"""
    )
    execute(
        """CREATE INDEX IF NOT EXISTS idx_data_catalog_workspace_type
           ON data_catalog_entries(workspace_id, resource_type, updated_at)"""
    )


def _overlay(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {}
    item = dict(row)
    item["tags"] = json_loads(item.pop("tags_json", None), [])
    item["glossary"] = json_loads(item.pop("glossary_json", None), {})
    return item


def get_catalog_entry(workspace_id: str, resource_type: str, resource_id: str) -> dict[str, Any] | None:
    _ensure_tables()
    row = fetch_one(
        """SELECT * FROM data_catalog_entries
           WHERE workspace_id=:ws AND resource_type=:type AND resource_id=:rid""",
        {"ws": workspace_id, "type": resource_type, "rid": resource_id},
    )
    return _overlay(row)


def save_catalog_entry(
    actor_id: str,
    workspace_id: str,
    resource_type: str,
    resource_id: str,
    *,
    title: str | None = None,
    description: str = "",
    business_domain: str = "",
    owner_user_id: str | None = None,
    steward_user_id: str | None = None,
    tags: list[str] | None = None,
    glossary: dict[str, str] | None = None,
    certification_status: str = "unreviewed",
) -> dict[str, Any]:
    _ensure_tables()
    certification_status = str(certification_status or "unreviewed").lower()
    if certification_status not in {"unreviewed", "draft", "certified", "deprecated"}:
        raise ValueError("certification_status invalide")
    now = utcnow()
    existing = fetch_one(
        """SELECT id,created_at,created_by FROM data_catalog_entries
           WHERE workspace_id=:ws AND resource_type=:type AND resource_id=:rid""",
        {"ws": workspace_id, "type": resource_type, "rid": resource_id},
    )
    entry_id = str(existing["id"]) if existing else str(uuid.uuid4())
    created_at = str(existing.get("created_at")) if existing else now
    created_by = str(existing.get("created_by")) if existing else actor_id
    clean_tags = sorted({str(x).strip() for x in (tags or []) if str(x).strip()})[:100]
    clean_glossary = {str(k).strip(): str(v).strip() for k, v in (glossary or {}).items() if str(k).strip()}
    if existing:
        execute(
            """UPDATE data_catalog_entries SET title=:title,description=:description,
               business_domain=:domain,owner_user_id=:owner,steward_user_id=:steward,
               tags_json=:tags,glossary_json=:glossary,certification_status=:status,
               updated_at=:updated WHERE id=:id""",
            {"id": entry_id, "title": (title or "").strip() or None, "description": description.strip()[:8000],
             "domain": business_domain.strip()[:500], "owner": owner_user_id, "steward": steward_user_id,
             "tags": json_dumps(clean_tags), "glossary": json_dumps(clean_glossary), "status": certification_status,
             "updated": now},
        )
    else:
        execute(
            """INSERT INTO data_catalog_entries(
               id,workspace_id,resource_type,resource_id,title,description,business_domain,
               owner_user_id,steward_user_id,tags_json,glossary_json,certification_status,
               created_by,created_at,updated_at
               ) VALUES(:id,:ws,:type,:rid,:title,:description,:domain,:owner,:steward,:tags,:glossary,
                        :status,:created_by,:created_at,:updated_at)""",
            {"id": entry_id, "ws": workspace_id, "type": resource_type, "rid": resource_id,
             "title": (title or "").strip() or None, "description": description.strip()[:8000],
             "domain": business_domain.strip()[:500], "owner": owner_user_id, "steward": steward_user_id,
             "tags": json_dumps(clean_tags), "glossary": json_dumps(clean_glossary), "status": certification_status,
             "created_by": created_by, "created_at": created_at, "updated_at": now},
        )
    return get_catalog_entry(workspace_id, resource_type, resource_id) or {}


def catalog_assets(
    workspace_id: str,
    *,
    query: str = "",
    resource_type: str | None = None,
    certification_status: str | None = None,
    limit: int = 250,
) -> dict[str, Any]:
    _ensure_tables()
    graph = build_lineage_graph(workspace_id)
    overlays = {
        (str(row["resource_type"]), str(row["resource_id"])): _overlay(row)
        for row in fetch_all("SELECT * FROM data_catalog_entries WHERE workspace_id=:ws", {"ws": workspace_id})
    }
    assets: list[dict[str, Any]] = []
    for node in graph.get("nodes", []):
        rtype = str(node.get("type") or "unknown")
        rid = str(node.get("resource_id") or str(node.get("id") or "").split(":", 1)[-1])
        if resource_type and rtype != resource_type:
            continue
        overlay = overlays.get((rtype, rid), {})
        asset = {
            "id": f"{rtype}:{rid}",
            "resource_type": rtype,
            "resource_id": rid,
            "technical_name": node.get("label") or rid,
            "title": overlay.get("title") or node.get("label") or rid,
            "description": overlay.get("description") or "",
            "business_domain": overlay.get("business_domain") or "",
            "owner_user_id": overlay.get("owner_user_id"),
            "steward_user_id": overlay.get("steward_user_id"),
            "tags": overlay.get("tags") or [],
            "glossary": overlay.get("glossary") or {},
            "certification_status": overlay.get("certification_status") or "unreviewed",
            "lineage": {
                "upstream": sum(1 for e in graph.get("edges", []) if e.get("target") == node.get("id")),
                "downstream": sum(1 for e in graph.get("edges", []) if e.get("source") == node.get("id")),
            },
            "technical": {k: v for k, v in node.items() if k not in {"id", "type", "resource_id", "label"}},
        }
        if rtype == "dataset":
            try:
                meta = get_meta(rid)
                asset["technical"]["schema"] = meta.get("schema") or {}
                asset["technical"]["version"] = meta.get("version", 1)
                asset["technical"]["source_name"] = meta.get("source_name") or meta.get("original_name")
                asset["technical"]["external_source"] = meta.get("external_source") or {}
            except Exception:
                pass
        if certification_status and asset["certification_status"] != certification_status:
            continue
        haystack = " ".join([
            str(asset.get("title") or ""), str(asset.get("technical_name") or ""),
            str(asset.get("description") or ""), str(asset.get("business_domain") or ""),
            " ".join(asset.get("tags") or []), " ".join((asset.get("glossary") or {}).keys()),
        ]).lower()
        if query.strip() and query.strip().lower() not in haystack:
            continue
        assets.append(asset)
    assets.sort(key=lambda x: (x.get("certification_status") != "certified", x.get("resource_type", ""), str(x.get("title", "")).lower()))
    assets = assets[: max(1, min(int(limit), 1000))]
    by_type: dict[str, int] = {}
    for asset in assets:
        by_type[asset["resource_type"]] = by_type.get(asset["resource_type"], 0) + 1
    return {"assets": assets, "count": len(assets), "by_type": by_type, "generated_at": utcnow()}


def catalog_summary(workspace_id: str) -> dict[str, Any]:
    data = catalog_assets(workspace_id, limit=1000)
    assets = data["assets"]
    return {
        "assets": len(assets),
        "by_type": data["by_type"],
        "certified": sum(1 for x in assets if x.get("certification_status") == "certified"),
        "documented": sum(1 for x in assets if x.get("description")),
        "owned": sum(1 for x in assets if x.get("owner_user_id") or x.get("steward_user_id")),
        "tagged": sum(1 for x in assets if x.get("tags")),
        "generated_at": utcnow(),
    }
