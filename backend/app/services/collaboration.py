from __future__ import annotations

import hashlib
import re
import secrets
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
    if review.get("resource_type") == "model":
        from app.services.modeling import get_model_card
        try:
            card = get_model_card(str(review["resource_id"]))
        except FileNotFoundError as exc:
            raise ValueError("Certification impossible: Model Card introuvable.") from exc
        responsible = card.get("responsible_ai") or {}
        model_gate = responsible.get("publication_gate") or {}
        if model_gate and model_gate.get("allowed") is False:
            blockers = model_gate.get("blockers") or []
            codes = ", ".join(str(item.get("code") or "contrôle") for item in blockers[:8])
            raise ValueError(
                "Certification bloquée par le Responsible AI Gate: "
                + (codes or "contrôle Responsible AI en échec")
                + "."
            )
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

# ---------------------------------------------------------------------------
# Collaboration v2.54: teams, governed shares, decision ledger and diff feed.
# Shares are pointers only: they never grant permissions that the workspace/RBAC
# layer does not already grant to the recipient.
# ---------------------------------------------------------------------------

SHARE_PERMISSIONS = {"view", "comment", "review"}


def _hydrate_team(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    members = fetch_all(
        """SELECT u.id,u.email,u.display_name,wm.role,tm.created_at AS added_at
           FROM collaboration_team_members tm
           JOIN users u ON u.id=tm.user_id
           JOIN workspace_members wm ON wm.workspace_id=tm.workspace_id AND wm.user_id=tm.user_id
           WHERE tm.team_id=:team AND tm.workspace_id=:ws ORDER BY u.display_name,u.email""",
        {"team": item["id"], "ws": item["workspace_id"]},
    )
    item["members"] = members
    item["member_count"] = len(members)
    return item


def list_teams(user_id: str, workspace_id: str) -> list[dict[str, Any]]:
    _require_member(user_id, workspace_id)
    return [_hydrate_team(r) for r in fetch_all(
        "SELECT * FROM collaboration_teams WHERE workspace_id=:ws ORDER BY name",
        {"ws": workspace_id},
    )]


def create_team(actor_id: str, workspace_id: str, *, name: str, description: str = "", member_user_ids: list[str] | None = None) -> dict[str, Any]:
    _require_permission(actor_id, workspace_id, "members:manage")
    clean = name.strip()
    if not clean:
        raise ValueError("Le nom de l'équipe est requis.")
    if fetch_one("SELECT id FROM collaboration_teams WHERE workspace_id=:ws AND lower(name)=lower(:name)", {"ws": workspace_id, "name": clean}):
        raise ValueError("Une équipe portant ce nom existe déjà.")
    member_ids = list(dict.fromkeys(member_user_ids or []))
    for uid in member_ids:
        if not _member(workspace_id, uid):
            raise ValueError("Un membre de l'équipe n'appartient pas au workspace.")
    now = utcnow(); team_id = str(uuid.uuid4())
    execute(
        "INSERT INTO collaboration_teams(id,workspace_id,name,description,created_by,created_at,updated_at) VALUES(:id,:ws,:name,:description,:by,:now,:now)",
        {"id": team_id, "ws": workspace_id, "name": clean[:160], "description": description.strip()[:2000], "by": actor_id, "now": now},
    )
    for uid in member_ids:
        execute(
            "INSERT INTO collaboration_team_members(team_id,workspace_id,user_id,added_by,created_at) VALUES(:team,:ws,:user,:by,:now)",
            {"team": team_id, "ws": workspace_id, "user": uid, "by": actor_id, "now": now},
        )
    return _hydrate_team(fetch_one("SELECT * FROM collaboration_teams WHERE id=:id", {"id": team_id}) or {})


def set_team_member(actor_id: str, workspace_id: str, team_id: str, user_id: str, *, present: bool) -> dict[str, Any]:
    _require_permission(actor_id, workspace_id, "members:manage")
    team = fetch_one("SELECT * FROM collaboration_teams WHERE id=:id AND workspace_id=:ws", {"id": team_id, "ws": workspace_id})
    if not team:
        raise KeyError("Équipe introuvable.")
    if not _member(workspace_id, user_id):
        raise ValueError("Le membre n'appartient pas au workspace.")
    if present:
        exists = fetch_one("SELECT user_id FROM collaboration_team_members WHERE team_id=:team AND user_id=:user", {"team": team_id, "user": user_id})
        if not exists:
            execute(
                "INSERT INTO collaboration_team_members(team_id,workspace_id,user_id,added_by,created_at) VALUES(:team,:ws,:user,:by,:now)",
                {"team": team_id, "ws": workspace_id, "user": user_id, "by": actor_id, "now": utcnow()},
            )
    else:
        execute("DELETE FROM collaboration_team_members WHERE team_id=:team AND workspace_id=:ws AND user_id=:user", {"team": team_id, "ws": workspace_id, "user": user_id})
    execute("UPDATE collaboration_teams SET updated_at=:now WHERE id=:id", {"now": utcnow(), "id": team_id})
    return _hydrate_team(fetch_one("SELECT * FROM collaboration_teams WHERE id=:id", {"id": team_id}) or team)


def _share_recipients(workspace_id: str, *, recipient_user_id: str | None, recipient_team_id: str | None) -> list[str]:
    if bool(recipient_user_id) == bool(recipient_team_id):
        raise ValueError("Choisissez soit un membre, soit une équipe comme destinataire.")
    if recipient_user_id:
        if not _member(workspace_id, recipient_user_id):
            raise ValueError("Le destinataire n'appartient pas au workspace.")
        return [recipient_user_id]
    team = fetch_one("SELECT id FROM collaboration_teams WHERE id=:id AND workspace_id=:ws", {"id": recipient_team_id, "ws": workspace_id})
    if not team:
        raise ValueError("Équipe destinataire introuvable.")
    return [r["user_id"] for r in fetch_all("SELECT user_id FROM collaboration_team_members WHERE team_id=:team AND workspace_id=:ws", {"team": recipient_team_id, "ws": workspace_id})]


def create_artifact_share(
    actor_id: str, workspace_id: str, *, resource_type: str, resource_id: str, resource_version: str | None = None,
    recipient_user_id: str | None = None, recipient_team_id: str | None = None, permission: str = "view",
    note: str = "", expires_at: str | None = None,
) -> dict[str, Any]:
    _require_permission(actor_id, workspace_id, "publish:write")
    if resource_type not in RESOURCE_TYPES:
        raise ValueError("Type de ressource partagé invalide.")
    if permission not in SHARE_PERMISSIONS:
        raise ValueError("Permission de partage invalide.")
    if not resource_id.strip():
        raise ValueError("resource_id est requis.")
    recipients = _share_recipients(workspace_id, recipient_user_id=recipient_user_id, recipient_team_id=recipient_team_id)
    share_id = str(uuid.uuid4()); now = utcnow()
    execute(
        """INSERT INTO collaboration_artifact_shares(
             id,workspace_id,resource_type,resource_id,resource_version,recipient_user_id,recipient_team_id,permission,note,created_by,expires_at,revoked_at,created_at,updated_at
           ) VALUES(:id,:ws,:rtype,:rid,:version,:recipient,:team,:permission,:note,:by,:expires,NULL,:now,:now)""",
        {"id": share_id, "ws": workspace_id, "rtype": resource_type, "rid": resource_id.strip(), "version": resource_version,
         "recipient": recipient_user_id, "team": recipient_team_id, "permission": permission, "note": note.strip()[:2000], "by": actor_id,
         "expires": expires_at, "now": now},
    )
    for uid in recipients:
        if uid != actor_id:
            _notify(workspace_id, uid, None, "artifact_shared", f"Ressource partagée avec vous : {resource_type} · {resource_id[:120]}")
    return get_artifact_share(actor_id, workspace_id, share_id)


def _hydrate_share(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["created_by_user"] = _member(item["workspace_id"], item.get("created_by"))
    item["recipient_user"] = _member(item["workspace_id"], item.get("recipient_user_id")) if item.get("recipient_user_id") else None
    if item.get("recipient_team_id"):
        team = fetch_one("SELECT * FROM collaboration_teams WHERE id=:id AND workspace_id=:ws", {"id": item["recipient_team_id"], "ws": item["workspace_id"]})
        item["recipient_team"] = _hydrate_team(team) if team else None
    else:
        item["recipient_team"] = None
    item["active"] = not bool(item.get("revoked_at"))
    if item.get("expires_at"):
        try:
            exp = datetime.fromisoformat(str(item["expires_at"]).replace("Z", "+00:00"))
            if exp.tzinfo is None: exp = exp.replace(tzinfo=timezone.utc)
            item["active"] = item["active"] and exp > datetime.now(timezone.utc)
        except Exception:
            item["active"] = False
    return item


def get_artifact_share(user_id: str, workspace_id: str, share_id: str) -> dict[str, Any]:
    _require_member(user_id, workspace_id)
    row = fetch_one("SELECT * FROM collaboration_artifact_shares WHERE id=:id AND workspace_id=:ws", {"id": share_id, "ws": workspace_id})
    if not row:
        raise KeyError("Partage introuvable.")
    share = _hydrate_share(row)
    allowed = share.get("created_by") == user_id or share.get("recipient_user_id") == user_id
    if not allowed and share.get("recipient_team_id"):
        allowed = bool(fetch_one("SELECT user_id FROM collaboration_team_members WHERE team_id=:team AND user_id=:user", {"team": share["recipient_team_id"], "user": user_id}))
    if not allowed and not has_permission(user_id, workspace_id, "review:manage"):
        raise PermissionError("Ce partage ne vous est pas destiné.")
    return share


def list_artifact_shares(user_id: str, workspace_id: str, *, scope: str = "received", limit: int = 200) -> list[dict[str, Any]]:
    _require_member(user_id, workspace_id)
    rows = fetch_all("SELECT * FROM collaboration_artifact_shares WHERE workspace_id=:ws ORDER BY created_at DESC LIMIT :limit", {"ws": workspace_id, "limit": max(1, min(limit, 500))})
    result: list[dict[str, Any]] = []
    team_ids = {r["team_id"] for r in fetch_all("SELECT team_id FROM collaboration_team_members WHERE workspace_id=:ws AND user_id=:user", {"ws": workspace_id, "user": user_id})}
    for row in rows:
        if scope == "sent" and row.get("created_by") != user_id:
            continue
        if scope == "received" and row.get("recipient_user_id") != user_id and row.get("recipient_team_id") not in team_ids:
            continue
        if scope == "all" and not has_permission(user_id, workspace_id, "review:manage") and row.get("created_by") != user_id and row.get("recipient_user_id") != user_id and row.get("recipient_team_id") not in team_ids:
            continue
        if scope not in {"received", "sent", "all"}:
            raise ValueError("Scope de partage invalide.")
        result.append(_hydrate_share(row))
    return result


def revoke_artifact_share(actor_id: str, workspace_id: str, share_id: str) -> dict[str, Any]:
    share = get_artifact_share(actor_id, workspace_id, share_id)
    if share.get("created_by") != actor_id and not has_permission(actor_id, workspace_id, "review:manage"):
        raise PermissionError("Seul l'auteur du partage ou un manager peut le révoquer.")
    execute("UPDATE collaboration_artifact_shares SET revoked_at=:now,updated_at=:now WHERE id=:id", {"now": utcnow(), "id": share_id})
    return _hydrate_share(fetch_one("SELECT * FROM collaboration_artifact_shares WHERE id=:id", {"id": share_id}) or share)


def _flat_snapshot(value: Any, prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    if isinstance(value, dict):
        for key in sorted(value):
            child = f"{prefix}.{key}" if prefix else str(key)
            out.update(_flat_snapshot(value[key], child))
    elif isinstance(value, list):
        out[prefix or "$root"] = json_dumps(value)
    else:
        out[prefix or "$root"] = value
    return out


def review_snapshot_diff(user_id: str, workspace_id: str, review_id: str, *, against_review_id: str | None = None) -> dict[str, Any]:
    current = get_review(user_id, workspace_id, review_id)
    if against_review_id:
        baseline = get_review(user_id, workspace_id, against_review_id)
        if baseline["resource_type"] != current["resource_type"] or baseline["resource_id"] != current["resource_id"]:
            raise ValueError("Les deux revues ne concernent pas la même ressource.")
    else:
        row = fetch_one(
            """SELECT id FROM review_items WHERE workspace_id=:ws AND resource_type=:rtype AND resource_id=:rid AND id<>:id AND created_at<:created
               ORDER BY created_at DESC LIMIT 1""",
            {"ws": workspace_id, "rtype": current["resource_type"], "rid": current["resource_id"], "id": review_id, "created": current["created_at"]},
        )
        baseline = get_review(user_id, workspace_id, row["id"]) if row else None
    before_payload = {"resource_version": baseline.get("resource_version") if baseline else None, **((baseline or {}).get("snapshot") or {})}
    after_payload = {"resource_version": current.get("resource_version"), **(current.get("snapshot") or {})}
    before = _flat_snapshot(before_payload); after = _flat_snapshot(after_payload)
    changes = []
    for path in sorted(set(before) | set(after)):
        old, new = before.get(path), after.get(path)
        if old == new: continue
        kind = "added" if path not in before else "removed" if path not in after else "changed"
        changes.append({"path": path, "kind": kind, "before": old, "after": new})
    digest = hashlib.sha256(json_dumps(changes).encode("utf-8")).hexdigest()
    return {
        "review_id": review_id, "baseline_review_id": baseline.get("id") if baseline else None,
        "resource_type": current["resource_type"], "resource_id": current["resource_id"],
        "from_version": baseline.get("resource_version") if baseline else None, "to_version": current.get("resource_version"),
        "changed": bool(changes), "change_count": len(changes), "changes": changes[:500], "diff_sha256": digest,
    }


def decision_ledger(user_id: str, workspace_id: str, limit: int = 200) -> list[dict[str, Any]]:
    _require_permission(user_id, workspace_id, "review:read")
    rows = fetch_all(
        """SELECT e.*,r.title,r.resource_type,r.resource_id,r.resource_version,u.display_name,u.email
           FROM review_events e JOIN review_items r ON r.id=e.review_id JOIN users u ON u.id=e.actor_user_id
           WHERE e.workspace_id=:ws AND e.action IN ('approve','request_changes','certified','certification_revoked')
           ORDER BY e.created_at DESC LIMIT :limit""",
        {"ws": workspace_id, "limit": max(1, min(limit, 500))},
    )
    for row in rows:
        row["payload"] = json_loads(row.pop("payload_json", "{}"), {})
    return rows


def collaboration_activity(user_id: str, workspace_id: str, *, since: str | None = None, limit: int = 100) -> dict[str, Any]:
    _require_member(user_id, workspace_id)
    params: dict[str, Any] = {"ws": workspace_id, "limit": max(1, min(limit, 300))}
    clause = " AND created_at>:since" if since else ""
    if since: params["since"] = since
    events = fetch_all(f"SELECT id,review_id,actor_user_id AS user_id,action AS kind,created_at FROM review_events WHERE workspace_id=:ws{clause} ORDER BY created_at DESC LIMIT :limit", params)
    comments = fetch_all(f"SELECT id,review_id,user_id,'comment' AS kind,created_at FROM review_comments WHERE workspace_id=:ws{clause} ORDER BY created_at DESC LIMIT :limit", params)
    shares = fetch_all(f"SELECT id,NULL AS review_id,created_by AS user_id,'artifact_shared' AS kind,created_at FROM collaboration_artifact_shares WHERE workspace_id=:ws{clause} ORDER BY created_at DESC LIMIT :limit", params)
    items = sorted([*events, *comments, *shares], key=lambda x: str(x.get("created_at") or ""), reverse=True)[:params["limit"]]
    cursor = max([str(x.get("created_at") or "") for x in items], default=since or "")
    summary = review_summary(user_id, workspace_id) if has_permission(user_id, workspace_id, "review:read") else {"unread_notifications": 0}
    return {"items": items, "cursor": cursor, "summary": summary}


def mark_all_notifications_read(user_id: str, workspace_id: str) -> int:
    _require_member(user_id, workspace_id)
    unread = fetch_one("SELECT COUNT(*) AS n FROM collaboration_notifications WHERE workspace_id=:ws AND user_id=:user AND is_read=0", {"ws": workspace_id, "user": user_id}) or {"n": 0}
    execute("UPDATE collaboration_notifications SET is_read=1,read_at=:now WHERE workspace_id=:ws AND user_id=:user AND is_read=0", {"now": utcnow(), "ws": workspace_id, "user": user_id})
    return int(unread.get("n") or 0)


def create_realtime_ticket(user_id: str, workspace_id: str, ttl_seconds: int = 60) -> dict[str, Any]:
    _require_member(user_id, workspace_id)
    now = datetime.now(timezone.utc)
    expires = now.timestamp() + max(15, min(int(ttl_seconds), 120))
    expires_dt = datetime.fromtimestamp(expires, tz=timezone.utc).isoformat()
    ticket = secrets.token_urlsafe(36)
    # Opportunistic cleanup keeps this table bounded without a scheduler.
    execute("DELETE FROM collaboration_ws_tickets WHERE expires_at<:now OR used_at IS NOT NULL", {"now": now.isoformat()})
    execute(
        "INSERT INTO collaboration_ws_tickets(id,workspace_id,user_id,expires_at,used_at,created_at) VALUES(:id,:ws,:user,:expires,NULL,:created)",
        {"id": ticket, "ws": workspace_id, "user": user_id, "expires": expires_dt, "created": now.isoformat()},
    )
    return {"ticket": ticket, "expires_at": expires_dt}


def consume_realtime_ticket(ticket: str, workspace_id: str) -> dict[str, Any]:
    row = fetch_one("SELECT * FROM collaboration_ws_tickets WHERE id=:id AND workspace_id=:ws", {"id": ticket, "ws": workspace_id})
    if not row or row.get("used_at"):
        raise PermissionError("Ticket temps réel invalide ou déjà utilisé.")
    try:
        exp = datetime.fromisoformat(str(row["expires_at"]).replace("Z", "+00:00"))
        if exp.tzinfo is None: exp = exp.replace(tzinfo=timezone.utc)
    except Exception as exc:
        raise PermissionError("Ticket temps réel invalide.") from exc
    if exp <= datetime.now(timezone.utc):
        raise PermissionError("Ticket temps réel expiré.")
    if not _member(workspace_id, row.get("user_id")):
        raise PermissionError("Accès au workspace refusé.")
    execute("UPDATE collaboration_ws_tickets SET used_at=:now WHERE id=:id", {"now": utcnow(), "id": ticket})
    return row

