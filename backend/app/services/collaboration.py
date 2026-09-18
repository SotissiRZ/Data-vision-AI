from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from app.services.auth_service import has_permission, workspace_role
from app.services.metadata_store import execute, fetch_all, fetch_one, json_dumps, json_loads, utcnow

RESOURCE_TYPES = {"dataset", "semantic_metric", "analysis", "dashboard", "report", "model", "visualization"}
STATUSES = {"draft", "in_review", "changes_requested", "approved", "archived"}
PRIORITIES = {"low", "normal", "high", "critical"}


def _member(workspace_id: str, user_id: str | None) -> dict[str, Any] | None:
    if not user_id:
        return None
    return fetch_one(
        """
        SELECT u.id,u.email,u.display_name,wm.role
        FROM workspace_members wm JOIN users u ON u.id=wm.user_id
        WHERE wm.workspace_id=:ws AND u.id=:user
        """,
        {"ws": workspace_id, "user": user_id},
    )


def _workspace_org(workspace_id: str) -> str | None:
    row = fetch_one("SELECT organization_id FROM workspaces WHERE id=:ws", {"ws": workspace_id})
    return row["organization_id"] if row else None


def _require_member(user_id: str, workspace_id: str) -> str:
    role = workspace_role(user_id, workspace_id)
    if not role:
        raise PermissionError("Accès au workspace refusé.")
    return role


def _require_permission(user_id: str, workspace_id: str, permission: str) -> None:
    if not has_permission(user_id, workspace_id, permission):
        raise PermissionError(f"Permission insuffisante: {permission}.")


def _notify(workspace_id: str, user_id: str | None, review_id: str | None, kind: str, message: str) -> None:
    if not user_id:
        return
    execute(
        """
        INSERT INTO collaboration_notifications(id,workspace_id,user_id,review_id,notification_type,message,is_read,created_at)
        VALUES(:id,:ws,:user,:review,:kind,:message,0,:created)
        """,
        {"id": str(uuid.uuid4()), "ws": workspace_id, "user": user_id, "review": review_id, "kind": kind, "message": message[:500], "created": utcnow()},
    )


def _event(review_id: str, workspace_id: str, actor_user_id: str, action: str, from_status: str | None = None, to_status: str | None = None, payload: dict[str, Any] | None = None) -> None:
    execute(
        """
        INSERT INTO review_events(id,review_id,workspace_id,actor_user_id,action,from_status,to_status,payload_json,created_at)
        VALUES(:id,:review,:ws,:actor,:action,:from_status,:to_status,:payload,:created)
        """,
        {
            "id": str(uuid.uuid4()), "review": review_id, "ws": workspace_id, "actor": actor_user_id,
            "action": action, "from_status": from_status, "to_status": to_status,
            "payload": json_dumps(payload or {}), "created": utcnow(),
        },
    )


def _hydrate_review(row: dict[str, Any]) -> dict[str, Any]:
    row = dict(row)
    row["snapshot"] = json_loads(row.pop("snapshot_json", "{}"), {})
    row["owner"] = _member(row["workspace_id"], row.get("owner_user_id"))
    row["reviewer"] = _member(row["workspace_id"], row.get("reviewer_user_id"))
    creator = _member(row["workspace_id"], row.get("created_by"))
    row["created_by_user"] = creator
    row["comment_count"] = int((fetch_one("SELECT COUNT(*) AS n FROM review_comments WHERE review_id=:id", {"id": row["id"]}) or {"n": 0})["n"])
    row["unresolved_comment_count"] = int((fetch_one("SELECT COUNT(*) AS n FROM review_comments WHERE review_id=:id AND resolved=0", {"id": row["id"]}) or {"n": 0})["n"])
    return row


def create_review(
    actor_id: str,
    workspace_id: str,
    *,
    resource_type: str,
    resource_id: str,
    title: str,
    description: str = "",
    dataset_id: str | None = None,
    resource_version: str | None = None,
    priority: str = "normal",
    owner_user_id: str | None = None,
    reviewer_user_id: str | None = None,
    due_at: str | None = None,
    snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _require_permission(actor_id, workspace_id, "review:submit")
    if resource_type not in RESOURCE_TYPES:
        raise ValueError("Type de ressource de revue invalide.")
    if priority not in PRIORITIES:
        raise ValueError("Priorité de revue invalide.")
    if not resource_id.strip():
        raise ValueError("resource_id est requis.")
    if owner_user_id and not _member(workspace_id, owner_user_id):
        raise ValueError("Propriétaire non membre du workspace.")
    if reviewer_user_id and not _member(workspace_id, reviewer_user_id):
        raise ValueError("Reviewer non membre du workspace.")
    rid = str(uuid.uuid4())
    now = utcnow()
    execute(
        """
        INSERT INTO review_items(
          id,workspace_id,organization_id,dataset_id,resource_type,resource_id,resource_version,title,description,priority,status,
          owner_user_id,reviewer_user_id,created_by,due_at,snapshot_json,created_at,updated_at
        ) VALUES(
          :id,:ws,:org,:dataset,:rtype,:rid,:rversion,:title,:description,:priority,'draft',
          :owner,:reviewer,:created_by,:due,:snapshot,:created,:updated
        )
        """,
        {
            "id": rid, "ws": workspace_id, "org": _workspace_org(workspace_id), "dataset": dataset_id,
            "rtype": resource_type, "rid": resource_id.strip(), "rversion": resource_version,
            "title": title.strip()[:220] or "Revue sans titre", "description": description.strip()[:4000],
            "priority": priority, "owner": owner_user_id or actor_id, "reviewer": reviewer_user_id,
            "created_by": actor_id, "due": due_at, "snapshot": json_dumps(snapshot or {}), "created": now, "updated": now,
        },
    )
    _event(rid, workspace_id, actor_id, "created", None, "draft", {"resource_type": resource_type, "resource_id": resource_id})
    if reviewer_user_id and reviewer_user_id != actor_id:
        _notify(workspace_id, reviewer_user_id, rid, "review_assigned", f"Nouvelle revue assignée : {title.strip()[:160]}")
    return get_review(actor_id, workspace_id, rid)


def list_reviews(user_id: str, workspace_id: str, *, status: str | None = None, scope: str = "all", limit: int = 200) -> list[dict[str, Any]]:
    _require_permission(user_id, workspace_id, "review:read")
    clauses = ["workspace_id=:ws"]
    params: dict[str, Any] = {"ws": workspace_id, "limit": max(1, min(limit, 500)), "user": user_id}
    if status and status != "all":
        if status not in STATUSES:
            raise ValueError("Statut de revue invalide.")
        clauses.append("status=:status"); params["status"] = status
    if scope == "assigned":
        clauses.append("reviewer_user_id=:user")
    elif scope == "owned":
        clauses.append("owner_user_id=:user")
    elif scope == "created":
        clauses.append("created_by=:user")
    elif scope != "all":
        raise ValueError("Scope de revue invalide.")
    rows = fetch_all(f"SELECT * FROM review_items WHERE {' AND '.join(clauses)} ORDER BY updated_at DESC LIMIT :limit", params)
    return [_hydrate_review(r) for r in rows]


def get_review(user_id: str, workspace_id: str, review_id: str) -> dict[str, Any]:
    _require_permission(user_id, workspace_id, "review:read")
    row = fetch_one("SELECT * FROM review_items WHERE id=:id AND workspace_id=:ws", {"id": review_id, "ws": workspace_id})
    if not row:
        raise KeyError("Revue introuvable.")
    review = _hydrate_review(row)
    comments = fetch_all(
        """
        SELECT c.*,u.display_name,u.email
        FROM review_comments c JOIN users u ON u.id=c.user_id
        WHERE c.review_id=:id ORDER BY c.created_at ASC
        """,
        {"id": review_id},
    )
    for c in comments:
        c["mentions"] = json_loads(c.pop("mentions_json", "[]"), [])
        c["resolved"] = bool(c.get("resolved"))
    events = fetch_all(
        """
        SELECT e.*,u.display_name,u.email
        FROM review_events e JOIN users u ON u.id=e.actor_user_id
        WHERE e.review_id=:id ORDER BY e.created_at ASC
        """,
        {"id": review_id},
    )
    for e in events:
        e["payload"] = json_loads(e.pop("payload_json", "{}"), {})
    review["comments"] = comments
    review["events"] = events
    return review


def assign_review(actor_id: str, workspace_id: str, review_id: str, *, owner_user_id: str | None = None, reviewer_user_id: str | None = None, due_at: str | None = None, priority: str | None = None) -> dict[str, Any]:
    _require_permission(actor_id, workspace_id, "review:manage")
    review = get_review(actor_id, workspace_id, review_id)
    if owner_user_id and not _member(workspace_id, owner_user_id):
        raise ValueError("Propriétaire non membre du workspace.")
    if reviewer_user_id and not _member(workspace_id, reviewer_user_id):
        raise ValueError("Reviewer non membre du workspace.")
    if priority and priority not in PRIORITIES:
        raise ValueError("Priorité invalide.")
    execute(
        """
        UPDATE review_items SET owner_user_id=:owner,reviewer_user_id=:reviewer,due_at=:due,priority=:priority,updated_at=:updated
        WHERE id=:id AND workspace_id=:ws
        """,
        {
            "owner": owner_user_id if owner_user_id is not None else review.get("owner_user_id"),
            "reviewer": reviewer_user_id if reviewer_user_id is not None else review.get("reviewer_user_id"),
            "due": due_at if due_at is not None else review.get("due_at"),
            "priority": priority or review.get("priority", "normal"),
            "updated": utcnow(), "id": review_id, "ws": workspace_id,
        },
    )
    _event(review_id, workspace_id, actor_id, "assigned", review["status"], review["status"], {"owner_user_id": owner_user_id, "reviewer_user_id": reviewer_user_id, "due_at": due_at, "priority": priority})
    if reviewer_user_id and reviewer_user_id != actor_id:
        _notify(workspace_id, reviewer_user_id, review_id, "review_assigned", f"Revue assignée : {review['title']}")
    return get_review(actor_id, workspace_id, review_id)


def transition_review(actor_id: str, workspace_id: str, review_id: str, action: str, note: str = "") -> dict[str, Any]:
    review = get_review(actor_id, workspace_id, review_id)
    current = review["status"]
    action = action.strip().lower()
    transitions = {
        "submit": ({"draft", "changes_requested"}, "in_review", "review:submit"),
        "approve": ({"in_review"}, "approved", "review:approve"),
        "request_changes": ({"in_review"}, "changes_requested", "review:approve"),
        "reopen": ({"approved", "changes_requested"}, "in_review", "review:submit"),
        "archive": ({"draft", "in_review", "changes_requested", "approved"}, "archived", "review:manage"),
    }
    if action not in transitions:
        raise ValueError("Action de workflow invalide.")
    allowed_from, target, permission = transitions[action]
    _require_permission(actor_id, workspace_id, permission)
    if current not in allowed_from:
        raise ValueError(f"Transition {action} impossible depuis {current}.")
    # An explicitly assigned reviewer owns the decision. Admin/owner can still override through review:manage.
    if action in {"approve", "request_changes"} and review.get("reviewer_user_id") and review["reviewer_user_id"] != actor_id:
        if not has_permission(actor_id, workspace_id, "review:manage"):
            raise PermissionError("Cette décision est réservée au reviewer assigné.")
    now = utcnow()
    submitted_at = now if action in {"submit", "reopen"} else review.get("submitted_at")
    decided_at = now if action in {"approve", "request_changes"} else None if action in {"submit", "reopen"} else review.get("decided_at")
    execute(
        """
        UPDATE review_items SET status=:status,decision_note=:note,submitted_at=:submitted,decided_at=:decided,updated_at=:updated
        WHERE id=:id AND workspace_id=:ws
        """,
        {"status": target, "note": note.strip()[:3000] or None, "submitted": submitted_at, "decided": decided_at, "updated": now, "id": review_id, "ws": workspace_id},
    )
    _event(review_id, workspace_id, actor_id, action, current, target, {"note": note.strip()[:1000]})
    recipients = {review.get("owner_user_id"), review.get("created_by"), review.get("reviewer_user_id")}
    recipients.discard(None); recipients.discard(actor_id)
    message = f"{review['title']} → {target.replace('_', ' ')}"
    for uid in recipients:
        _notify(workspace_id, uid, review_id, f"review_{action}", message)
    return get_review(actor_id, workspace_id, review_id)


def _resolve_mentions(workspace_id: str, body: str, explicit_ids: list[str] | None = None) -> list[str]:
    members = fetch_all(
        """SELECT u.id,u.email,u.display_name FROM workspace_members wm JOIN users u ON u.id=wm.user_id WHERE wm.workspace_id=:ws""",
        {"ws": workspace_id},
    )
    ids = {m["id"] for m in members}
    result = {uid for uid in (explicit_ids or []) if uid in ids}
    lower = body.lower()
    for m in members:
        email = str(m.get("email") or "").lower()
        handle = email.split("@", 1)[0]
        display = re.sub(r"\s+", "", str(m.get("display_name") or "")).lower()
        if email and f"@{email}" in lower:
            result.add(m["id"])
        elif handle and f"@{handle}" in lower:
            result.add(m["id"])
        elif display and f"@{display}" in re.sub(r"\s+", "", lower):
            result.add(m["id"])
    return sorted(result)


def add_comment(actor_id: str, workspace_id: str, review_id: str, body: str, mention_user_ids: list[str] | None = None) -> dict[str, Any]:
    _require_permission(actor_id, workspace_id, "review:comment")
    review = get_review(actor_id, workspace_id, review_id)
    text = body.strip()
    if not text:
        raise ValueError("Le commentaire est vide.")
    mentions = _resolve_mentions(workspace_id, text, mention_user_ids)
    cid = str(uuid.uuid4()); now = utcnow()
    execute(
        """
        INSERT INTO review_comments(id,review_id,workspace_id,user_id,body,mentions_json,resolved,created_at,updated_at)
        VALUES(:id,:review,:ws,:user,:body,:mentions,0,:created,:updated)
        """,
        {"id": cid, "review": review_id, "ws": workspace_id, "user": actor_id, "body": text[:6000], "mentions": json_dumps(mentions), "created": now, "updated": now},
    )
    execute("UPDATE review_items SET updated_at=:updated WHERE id=:id", {"updated": now, "id": review_id})
    _event(review_id, workspace_id, actor_id, "commented", review["status"], review["status"], {"comment_id": cid, "mentions": mentions})
    for uid in mentions:
        if uid != actor_id:
            _notify(workspace_id, uid, review_id, "mention", f"Vous avez été mentionné dans : {review['title']}")
    reviewer = review.get("reviewer_user_id")
    if reviewer and reviewer != actor_id and reviewer not in mentions:
        _notify(workspace_id, reviewer, review_id, "review_comment", f"Nouveau commentaire : {review['title']}")
    return get_review(actor_id, workspace_id, review_id)


def resolve_comment(actor_id: str, workspace_id: str, review_id: str, comment_id: str, resolved: bool = True) -> dict[str, Any]:
    _require_permission(actor_id, workspace_id, "review:comment")
    review = get_review(actor_id, workspace_id, review_id)
    comment = fetch_one("SELECT * FROM review_comments WHERE id=:id AND review_id=:review AND workspace_id=:ws", {"id": comment_id, "review": review_id, "ws": workspace_id})
    if not comment:
        raise KeyError("Commentaire introuvable.")
    # Comment author, assigned reviewer or review manager can resolve a thread.
    if comment["user_id"] != actor_id and review.get("reviewer_user_id") != actor_id and not has_permission(actor_id, workspace_id, "review:manage"):
        raise PermissionError("Vous ne pouvez pas résoudre ce commentaire.")
    now = utcnow()
    execute(
        "UPDATE review_comments SET resolved=:resolved,resolved_by=:by,resolved_at=:at,updated_at=:updated WHERE id=:id",
        {"resolved": 1 if resolved else 0, "by": actor_id if resolved else None, "at": now if resolved else None, "updated": now, "id": comment_id},
    )
    _event(review_id, workspace_id, actor_id, "comment_resolved" if resolved else "comment_reopened", review["status"], review["status"], {"comment_id": comment_id})
    return get_review(actor_id, workspace_id, review_id)


def review_summary(user_id: str, workspace_id: str) -> dict[str, Any]:
    _require_permission(user_id, workspace_id, "review:read")
    rows = fetch_all("SELECT status,priority,reviewer_user_id,owner_user_id,due_at FROM review_items WHERE workspace_id=:ws", {"ws": workspace_id})
    counts = {s: 0 for s in STATUSES}
    overdue = 0; mine = 0
    now = datetime.now(timezone.utc)
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
        if r.get("reviewer_user_id") == user_id and r["status"] == "in_review":
            mine += 1
        due = r.get("due_at")
        if due and r["status"] not in {"approved", "archived"}:
            try:
                dt = datetime.fromisoformat(str(due).replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                if dt < now:
                    overdue += 1
            except Exception:
                pass
    active_certifications = int((fetch_one("SELECT COUNT(*) AS n FROM resource_certifications WHERE workspace_id=:ws AND status='active'", {"ws": workspace_id}) or {"n": 0})["n"])
    unread = int((fetch_one("SELECT COUNT(*) AS n FROM collaboration_notifications WHERE workspace_id=:ws AND user_id=:user AND is_read=0", {"ws": workspace_id, "user": user_id}) or {"n": 0})["n"])
    return {"total": len(rows), "by_status": counts, "assigned_to_me": mine, "overdue": overdue, "unread_notifications": unread, "active_certifications": active_certifications}


def list_notifications(user_id: str, workspace_id: str, limit: int = 100) -> list[dict[str, Any]]:
    _require_member(user_id, workspace_id)
    return fetch_all(
        "SELECT * FROM collaboration_notifications WHERE workspace_id=:ws AND user_id=:user ORDER BY created_at DESC LIMIT :limit",
        {"ws": workspace_id, "user": user_id, "limit": max(1, min(limit, 300))},
    )


def mark_notification_read(user_id: str, workspace_id: str, notification_id: str) -> dict[str, Any]:
    _require_member(user_id, workspace_id)
    row = fetch_one("SELECT * FROM collaboration_notifications WHERE id=:id AND workspace_id=:ws AND user_id=:user", {"id": notification_id, "ws": workspace_id, "user": user_id})
    if not row:
        raise KeyError("Notification introuvable.")
    execute("UPDATE collaboration_notifications SET is_read=1,read_at=:read WHERE id=:id", {"read": utcnow(), "id": notification_id})
    return fetch_one("SELECT * FROM collaboration_notifications WHERE id=:id", {"id": notification_id}) or row



def certify_review(actor_id: str, workspace_id: str, review_id: str, *, valid_until: str | None = None, notes: str = "") -> dict[str, Any]:
    _require_permission(actor_id, workspace_id, "certify:manage")
    review = get_review(actor_id, workspace_id, review_id)
    if review["status"] != "approved":
        raise ValueError("La ressource doit être approuvée avant certification.")
    if review.get("dataset_id"):
        from app.services.data_reliability import publication_gate
        gate = publication_gate(workspace_id, str(review["dataset_id"]))
        if not gate.get("allowed", True):
            names = ", ".join(str(x.get("name") or x.get("contract_id")) for x in gate.get("blockers", []))
            raise ValueError(f"Certification bloquée par le Data Reliability Gate: {names or 'contrat critique en échec'}.")
    execute(
        "UPDATE resource_certifications SET status='revoked' WHERE workspace_id=:ws AND resource_type=:rtype AND resource_id=:rid AND status='active'",
        {"ws": workspace_id, "rtype": review["resource_type"], "rid": review["resource_id"]},
    )
    cid = str(uuid.uuid4()); now = utcnow()
    execute(
        """
        INSERT INTO resource_certifications(id,workspace_id,dataset_id,resource_type,resource_id,review_id,owner_user_id,certified_by,certified_at,valid_until,status,notes)
        VALUES(:id,:ws,:dataset,:rtype,:rid,:review,:owner,:by,:at,:valid,'active',:notes)
        """,
        {"id":cid,"ws":workspace_id,"dataset":review.get("dataset_id"),"rtype":review["resource_type"],"rid":review["resource_id"],"review":review_id,"owner":review.get("owner_user_id"),"by":actor_id,"at":now,"valid":valid_until,"notes":notes.strip()[:2000] or None},
    )
    _event(review_id, workspace_id, actor_id, "certified", review["status"], review["status"], {"certification_id":cid,"valid_until":valid_until})
    recipients={review.get("owner_user_id"),review.get("reviewer_user_id")};recipients.discard(None);recipients.discard(actor_id)
    for uid in recipients:_notify(workspace_id,uid,review_id,"resource_certified",f"Ressource certifiée : {review['title']}")
    return get_certification(actor_id, workspace_id, cid)


def get_certification(user_id: str, workspace_id: str, certification_id: str) -> dict[str, Any]:
    _require_permission(user_id, workspace_id, "review:read")
    row=fetch_one("SELECT * FROM resource_certifications WHERE id=:id AND workspace_id=:ws",{"id":certification_id,"ws":workspace_id})
    if not row: raise KeyError("Certification introuvable.")
    row=dict(row);row["owner"]=_member(workspace_id,row.get("owner_user_id"));row["certifier"]=_member(workspace_id,row.get("certified_by"))
    return row


def list_certifications(user_id: str, workspace_id: str, *, status: str = "active") -> list[dict[str, Any]]:
    _require_permission(user_id, workspace_id, "review:read")
    params={"ws":workspace_id};where="workspace_id=:ws"
    if status != "all": where+=" AND status=:status";params["status"]=status
    rows=fetch_all(f"SELECT * FROM resource_certifications WHERE {where} ORDER BY certified_at DESC",params)
    return [get_certification(user_id,workspace_id,r["id"]) for r in rows]


def revoke_certification(actor_id: str, workspace_id: str, certification_id: str, note: str = "") -> dict[str, Any]:
    _require_permission(actor_id, workspace_id, "certify:manage")
    cert=get_certification(actor_id,workspace_id,certification_id)
    execute("UPDATE resource_certifications SET status='revoked',notes=:notes WHERE id=:id",{"notes":note.strip()[:2000] or cert.get("notes"),"id":certification_id})
    _event(cert["review_id"],workspace_id,actor_id,"certification_revoked",None,None,{"certification_id":certification_id,"note":note[:1000]})
    return get_certification(actor_id,workspace_id,certification_id)
