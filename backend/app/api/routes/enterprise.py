from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.config import get_settings

from app.services.auth_service import bootstrap, decode_token, get_user, login, session_payload, has_permission, workspace_role
from app.services.audit_service import list_events, record_event
from app.services.job_service import get_job, list_jobs, request_cancel, submit_job, queue_status
from app.services.metadata_store import metadata_backend, fetch_one
from app.services.collaboration import (
    add_comment, assign_review, create_review, get_review, list_notifications, list_reviews,
    mark_notification_read, resolve_comment, review_summary, transition_review,
    certify_review, list_certifications, revoke_certification,
)
from app.services.connector_service import (
    create_connector, update_connector, get_connector, list_connectors, delete_connector, test_connector, discover_connector,
    create_source, get_source, list_sources, delete_source, preview_source, refresh_source,
    save_schedule, list_schedules, get_refresh_runs, workspace_refresh_health,
)
from app.services.workspace_service import (
    bind_dataset,
    create_workspace,
    get_workspace,
    list_members,
    list_policies,
    list_workspace_datasets,
    save_access_policy,
    upsert_member,
    policies_for_access, apply_access_policies,
)

router = APIRouter(tags=["enterprise"])


class BootstrapRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=200)
    display_name: str = Field(default="Administrateur", min_length=1, max_length=120)
    organization_name: str = Field(default="Mon organisation", min_length=1, max_length=160)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=200)


class WorkspaceCreateRequest(BaseModel):
    organization_id: str
    name: str = Field(min_length=1, max_length=160)


class MemberRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    role: str = Field(pattern="^(owner|admin|data_scientist|analyst|viewer)$")
    display_name: str | None = Field(default=None, max_length=120)
    password: str | None = Field(default=None, min_length=8, max_length=200)


class BindDatasetRequest(BaseModel):
    dataset_id: str


class PolicyRequest(BaseModel):
    policy_id: str | None = None
    dataset_id: str
    name: str = Field(min_length=1, max_length=160)
    allowed_columns: list[str] = []
    row_filters: list[dict[str, Any]] = []
    applies_to_role: str | None = Field(default=None, pattern="^(owner|admin|data_scientist|analyst|viewer)$")


class JobSubmitRequest(BaseModel):
    workspace_id: str | None = None
    organization_id: str | None = None
    job_type: str = Field(pattern="^(automl|ai_analysis|forecast|report|proactive_scan|connector_refresh)$")
    dataset_id: str | None = None
    payload: dict[str, Any] = {}


class ReviewCreateRequest(BaseModel):
    resource_type: str = Field(pattern="^(dataset|semantic_metric|analysis|dashboard|report|model|visualization)$")
    resource_id: str = Field(min_length=1, max_length=240)
    title: str = Field(min_length=1, max_length=220)
    description: str = Field(default="", max_length=4000)
    dataset_id: str | None = None
    resource_version: str | None = Field(default=None, max_length=120)
    priority: str = Field(default="normal", pattern="^(low|normal|high|critical)$")
    owner_user_id: str | None = None
    reviewer_user_id: str | None = None
    due_at: str | None = None
    snapshot: dict[str, Any] = {}


class ReviewAssignRequest(BaseModel):
    owner_user_id: str | None = None
    reviewer_user_id: str | None = None
    due_at: str | None = None
    priority: str | None = Field(default=None, pattern="^(low|normal|high|critical)$")


class ReviewTransitionRequest(BaseModel):
    action: str = Field(pattern="^(submit|approve|request_changes|reopen|archive)$")
    note: str = Field(default="", max_length=3000)


class ReviewCommentRequest(BaseModel):
    body: str = Field(min_length=1, max_length=6000)
    mention_user_ids: list[str] = []


class ReviewCommentResolveRequest(BaseModel):
    resolved: bool = True


class CertificationRequest(BaseModel):
    valid_until: str | None = None
    notes: str = Field(default="", max_length=2000)


class CertificationRevokeRequest(BaseModel):
    note: str = Field(default="", max_length=2000)


class ConnectorCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    connector_type: str = Field(pattern="^(postgresql|mysql)$")
    host: str = Field(min_length=1, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    database: str = Field(min_length=1, max_length=255)
    username: str = Field(min_length=1, max_length=255)
    password: str = Field(default="", max_length=2000)
    ssl_mode: str = Field(default="prefer", pattern="^(disable|prefer|require)$")
    options: dict[str, Any] = {}


class ConnectorUpdateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=160)
    host: str | None = Field(default=None, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    database: str | None = Field(default=None, max_length=255)
    username: str | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, max_length=2000)
    ssl_mode: str | None = Field(default=None, pattern="^(disable|prefer|require)$")
    options: dict[str, Any] | None = None


class ConnectorSourceCreateRequest(BaseModel):
    connector_id: str
    name: str = Field(min_length=1, max_length=180)
    source_kind: str = Field(default="table", pattern="^(table|query)$")
    table_name: str | None = Field(default=None, max_length=500)
    query: str | None = Field(default=None, max_length=50000)
    refresh_mode: str = Field(default="full", pattern="^(full|incremental)$")
    incremental_column: str | None = Field(default=None, max_length=255)
    freshness_sla_minutes: int = Field(default=1440, ge=5, le=525600)
    schema_drift_policy: str = Field(default="warn", pattern="^(warn|fail)$")
    source_options: dict[str, Any] = {}


class ConnectorRefreshRequest(BaseModel):
    background: bool = True


class RefreshScheduleRequest(BaseModel):
    enabled: bool = True
    interval_minutes: int = Field(default=1440, ge=15, le=43200)


def current_user(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Authentification requise")
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = decode_token(token)
        user = get_user(payload["sub"])
        if not user or not user.get("is_active"):
            raise ValueError("Compte inactif")
        return user
    except Exception as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


def _workspace_permission(user_id: str, workspace_id: str, permission: str) -> None:
    if not has_permission(user_id, workspace_id, permission):
        raise HTTPException(status_code=403, detail=f"Permission requise: {permission}")


def _handle(exc: Exception):
    if isinstance(exc, HTTPException):
        raise exc
    if isinstance(exc, PermissionError):
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if isinstance(exc, KeyError):
        raise HTTPException(status_code=404, detail=str(exc).strip("'")) from exc
    raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/auth/bootstrap")
def auth_bootstrap(req: BootstrapRequest):
    try:
        out = bootstrap(req.email, req.password, req.display_name, req.organization_name)
        record_event("auth.bootstrap", user_id=out["user"]["id"], organization_id=out["organization_id"], workspace_id=out["workspace_id"], resource_type="user", resource_id=out["user"]["id"], payload={"email": req.email})
        return out
    except Exception as exc:
        _handle(exc)


@router.post("/auth/login")
def auth_login(req: LoginRequest):
    try:
        out = login(req.email, req.password)
        record_event("auth.login", user_id=out["user"]["id"], resource_type="user", resource_id=out["user"]["id"], payload={"email": req.email})
        return out
    except Exception as exc:
        _handle(exc)


@router.get("/auth/me")
def auth_me(user=Depends(current_user)):
    try:
        return session_payload(user["id"])
    except Exception as exc:
        _handle(exc)


@router.get("/enterprise/status")
def enterprise_status():
    try:
        return {
            "metadata": metadata_backend(),
            "auth": "local_bearer",
            "oidc": "planned",
            "rbac": "implemented_for_enterprise_resources",
            "row_column_policies": "policy_metadata_and_preview_ready",
            "async_jobs": "redis_worker",
            "collaboration_review": "implemented",
            "resource_certification": "implemented",
            "connectors": "postgresql_mysql_with_encrypted_credentials",
            "connector_secret_key": "dedicated" if bool(get_settings().connector_secret_key) else "auth_secret_fallback",
            "refresh_scheduler": "worker_polling_with_atomic_schedule_claim",
            "queue": queue_status(),
            "token_expiry_minutes": get_settings().access_token_minutes,
            "security_warning": "AUTH_SECRET doit être remplacé avant tout déploiement partagé." if get_settings().auth_secret.startswith("change-") else None,
        }
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces")
def workspace_create(req: WorkspaceCreateRequest, user=Depends(current_user)):
    try:
        ws = create_workspace(user["id"], req.organization_id, req.name)
        record_event("workspace.create", user_id=user["id"], organization_id=req.organization_id, workspace_id=ws["id"], resource_type="workspace", resource_id=ws["id"], payload={"name": ws["name"]})
        return {"workspace": ws}
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}")
def workspace_detail(workspace_id: str, user=Depends(current_user)):
    try:
        return {"workspace": get_workspace(user["id"], workspace_id), "members": list_members(user["id"], workspace_id), "datasets": list_workspace_datasets(user["id"], workspace_id), "policies": list_policies(user["id"], workspace_id)}
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/members")
def workspace_member(workspace_id: str, req: MemberRequest, user=Depends(current_user)):
    try:
        member = upsert_member(user["id"], workspace_id, req.email, req.role, display_name=req.display_name, password=req.password)
        ws = get_workspace(user["id"], workspace_id)
        record_event("workspace.member.upsert", user_id=user["id"], organization_id=ws["organization_id"], workspace_id=workspace_id, resource_type="user", resource_id=member["id"], payload={"role": req.role})
        return {"member": member}
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/datasets")
def workspace_dataset(workspace_id: str, req: BindDatasetRequest, user=Depends(current_user)):
    try:
        bound = bind_dataset(user["id"], workspace_id, req.dataset_id)
        ws = get_workspace(user["id"], workspace_id)
        record_event("workspace.dataset.bind", user_id=user["id"], organization_id=ws["organization_id"], workspace_id=workspace_id, resource_type="dataset", resource_id=req.dataset_id)
        return bound
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/policies")
def workspace_policies(workspace_id: str, user=Depends(current_user)):
    try:
        return {"policies": list_policies(user["id"], workspace_id)}
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/policies")
def workspace_policy_save(workspace_id: str, req: PolicyRequest, user=Depends(current_user)):
    try:
        policy = save_access_policy(user["id"], workspace_id, req.dataset_id, req.name, req.allowed_columns, req.row_filters, req.applies_to_role, req.policy_id)
        ws = get_workspace(user["id"], workspace_id)
        record_event("workspace.policy.save", user_id=user["id"], organization_id=ws["organization_id"], workspace_id=workspace_id, resource_type="access_policy", resource_id=policy["id"], payload={"dataset_id": req.dataset_id, "role": req.applies_to_role})
        return {"policy": policy}
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/datasets/{dataset_id}/governed-preview")
def governed_dataset_preview(workspace_id: str, dataset_id: str, limit: int = Query(default=50, ge=1, le=500), simulate_role: str | None = Query(default=None), user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "dataset:read")
        if simulate_role:
            if simulate_role not in {"owner","admin","data_scientist","analyst","viewer"}:
                raise ValueError("Rôle de simulation invalide")
            _workspace_permission(user["id"], workspace_id, "policies:manage")
        linked = fetch_one("SELECT dataset_id FROM workspace_datasets WHERE workspace_id=:ws AND dataset_id=:ds", {"ws":workspace_id,"ds":dataset_id})
        if not linked:
            raise KeyError("Dataset non lié à ce workspace")
        from app.services.storage import load_dataframe
        df = load_dataframe(dataset_id)
        effective_role = simulate_role or workspace_role(user["id"], workspace_id)
        policies = policies_for_access(user["id"], workspace_id, dataset_id, role_override=simulate_role)
        governed, applied = apply_access_policies(df, policies)
        rows = governed.head(limit).where(governed.head(limit).notna(), None).to_dict(orient="records")
        record_event("dataset.governed_preview", user_id=user["id"], workspace_id=workspace_id, resource_type="dataset", resource_id=dataset_id, payload={"rows_before":len(df),"rows_after":len(governed),"policies":len(policies),"effective_role":effective_role})
        return {"columns":[str(c) for c in governed.columns],"rows":rows,"returned_rows":len(rows),"total_rows":len(governed),"policies":policies,"applied":applied,"effective_role":effective_role}
    except Exception as exc:
        _handle(exc)


@router.get("/audit")
def audit_list(workspace_id: str | None = Query(default=None), organization_id: str | None = Query(default=None), limit: int = Query(default=200, ge=1, le=1000), user=Depends(current_user)):
    if workspace_id:
        _workspace_permission(user["id"], workspace_id, "audit:read")
    elif organization_id:
        member = fetch_one("SELECT role FROM organization_members WHERE organization_id=:org AND user_id=:user", {"org":organization_id,"user":user["id"]})
        if not member or member["role"] not in {"owner","admin"}:
            raise HTTPException(status_code=403, detail="Permission audit organisation insuffisante")
    else:
        raise HTTPException(status_code=400, detail="workspace_id ou organization_id requis")
    return {"events": list_events(organization_id=organization_id, workspace_id=workspace_id, limit=limit)}


@router.post("/jobs")
def jobs_submit(req: JobSubmitRequest, user=Depends(current_user)):
    try:
        if req.workspace_id:
            perm = "model:run" if req.job_type == "automl" else "analysis:run"
            _workspace_permission(user["id"], req.workspace_id, perm)
        job = submit_job(user_id=user["id"], organization_id=req.organization_id, workspace_id=req.workspace_id, job_type=req.job_type, dataset_id=req.dataset_id, payload=req.payload)
        record_event("job.submit", user_id=user["id"], organization_id=req.organization_id, workspace_id=req.workspace_id, resource_type="job", resource_id=job["id"], payload={"job_type": req.job_type, "dataset_id": req.dataset_id})
        return {"job": job}
    except Exception as exc:
        _handle(exc)


@router.get("/jobs")
def jobs_list(workspace_id: str | None = Query(default=None), user=Depends(current_user)):
    if workspace_id and not workspace_role(user["id"], workspace_id):
        raise HTTPException(status_code=403, detail="Accès au workspace refusé")
    return {"jobs": list_jobs(user["id"], workspace_id)}


@router.get("/jobs/{job_id}")
def jobs_detail(job_id: str, user=Depends(current_user)):
    try:
        job = get_job(job_id)
        if job["user_id"] != user["id"] and (not job.get("workspace_id") or not has_permission(user["id"], job["workspace_id"], "jobs:manage")):
            raise PermissionError("Accès au job refusé")
        return {"job": job}
    except Exception as exc:
        _handle(exc)


@router.post("/jobs/{job_id}/cancel")
def jobs_cancel(job_id: str, user=Depends(current_user)):
    try:
        job = request_cancel(job_id, user["id"])
        record_event("job.cancel", user_id=user["id"], organization_id=job.get("organization_id"), workspace_id=job.get("workspace_id"), resource_type="job", resource_id=job_id)
        return {"job": job}
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/reviews/summary")
def reviews_summary(workspace_id: str, user=Depends(current_user)):
    try:
        return review_summary(user["id"], workspace_id)
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/reviews")
def reviews_list(workspace_id: str, status: str | None = Query(default=None), scope: str = Query(default="all"), limit: int = Query(default=200, ge=1, le=500), user=Depends(current_user)):
    try:
        return {"reviews": list_reviews(user["id"], workspace_id, status=status, scope=scope, limit=limit)}
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/reviews")
def reviews_create(workspace_id: str, req: ReviewCreateRequest, user=Depends(current_user)):
    try:
        review = create_review(
            user["id"], workspace_id, resource_type=req.resource_type, resource_id=req.resource_id, title=req.title,
            description=req.description, dataset_id=req.dataset_id, resource_version=req.resource_version, priority=req.priority,
            owner_user_id=req.owner_user_id, reviewer_user_id=req.reviewer_user_id, due_at=req.due_at, snapshot=req.snapshot,
        )
        ws = get_workspace(user["id"], workspace_id)
        record_event("review.create", user_id=user["id"], organization_id=ws["organization_id"], workspace_id=workspace_id, resource_type="review", resource_id=review["id"], payload={"resource_type":req.resource_type,"resource_id":req.resource_id})
        return {"review": review}
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/reviews/{review_id}")
def reviews_detail(workspace_id: str, review_id: str, user=Depends(current_user)):
    try:
        return {"review": get_review(user["id"], workspace_id, review_id)}
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/reviews/{review_id}/assign")
def reviews_assign(workspace_id: str, review_id: str, req: ReviewAssignRequest, user=Depends(current_user)):
    try:
        review = assign_review(user["id"], workspace_id, review_id, owner_user_id=req.owner_user_id, reviewer_user_id=req.reviewer_user_id, due_at=req.due_at, priority=req.priority)
        record_event("review.assign", user_id=user["id"], workspace_id=workspace_id, resource_type="review", resource_id=review_id, payload={"reviewer_user_id":req.reviewer_user_id,"owner_user_id":req.owner_user_id})
        return {"review": review}
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/reviews/{review_id}/transition")
def reviews_transition(workspace_id: str, review_id: str, req: ReviewTransitionRequest, user=Depends(current_user)):
    try:
        review = transition_review(user["id"], workspace_id, review_id, req.action, req.note)
        record_event(f"review.{req.action}", user_id=user["id"], workspace_id=workspace_id, resource_type="review", resource_id=review_id, payload={"status":review["status"]})
        return {"review": review}
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/reviews/{review_id}/comments")
def reviews_comment(workspace_id: str, review_id: str, req: ReviewCommentRequest, user=Depends(current_user)):
    try:
        review = add_comment(user["id"], workspace_id, review_id, req.body, req.mention_user_ids)
        record_event("review.comment", user_id=user["id"], workspace_id=workspace_id, resource_type="review", resource_id=review_id)
        return {"review": review}
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/reviews/{review_id}/comments/{comment_id}/resolve")
def reviews_comment_resolve(workspace_id: str, review_id: str, comment_id: str, req: ReviewCommentResolveRequest, user=Depends(current_user)):
    try:
        return {"review": resolve_comment(user["id"], workspace_id, review_id, comment_id, req.resolved)}
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/collaboration/notifications")
def collaboration_notifications(workspace_id: str, limit: int = Query(default=100, ge=1, le=300), user=Depends(current_user)):
    try:
        return {"notifications": list_notifications(user["id"], workspace_id, limit)}
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/collaboration/notifications/{notification_id}/read")
def collaboration_notification_read(workspace_id: str, notification_id: str, user=Depends(current_user)):
    try:
        return {"notification": mark_notification_read(user["id"], workspace_id, notification_id)}
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/certifications")
def certifications_list(workspace_id: str, status: str = Query(default="active"), user=Depends(current_user)):
    try:
        return {"certifications": list_certifications(user["id"], workspace_id, status=status)}
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/reviews/{review_id}/certify")
def reviews_certify(workspace_id: str, review_id: str, req: CertificationRequest, user=Depends(current_user)):
    try:
        cert = certify_review(user["id"], workspace_id, review_id, valid_until=req.valid_until, notes=req.notes)
        record_event("review.certify", user_id=user["id"], workspace_id=workspace_id, resource_type="certification", resource_id=cert["id"], payload={"review_id":review_id,"valid_until":req.valid_until})
        return {"certification": cert}
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/certifications/{certification_id}/revoke")
def certifications_revoke(workspace_id: str, certification_id: str, req: CertificationRevokeRequest, user=Depends(current_user)):
    try:
        return {"certification": revoke_certification(user["id"], workspace_id, certification_id, req.note)}
    except Exception as exc:
        _handle(exc)


def _connector_catalog_for_user(user_id: str, workspace_id: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    connectors = list_connectors(workspace_id)
    sources = list_sources(workspace_id)
    if has_permission(user_id, workspace_id, "connectors:manage"):
        return connectors, sources
    safe_connectors = []
    for c in connectors:
        safe_connectors.append({k:v for k,v in c.items() if k in {"id","workspace_id","name","connector_type","status","last_tested_at","last_error","ssl_mode","created_at","updated_at"}})
    safe_sources = []
    for src in sources:
        safe = dict(src)
        safe.pop("source_query", None)
        safe.pop("schema", None)
        safe_sources.append(safe)
    return safe_connectors, safe_sources


# ---------------------------- Data connectors & refresh v2.7 ----------------------------

@router.get("/workspaces/{workspace_id}/connectors/health")
def connectors_health(workspace_id: str, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "connectors:read")
        return workspace_refresh_health(workspace_id)
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/connectors")
def connectors_list(workspace_id: str, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "connectors:read")
        connectors, sources = _connector_catalog_for_user(user["id"], workspace_id)
        return {"connectors": connectors, "sources": sources, "schedules": list_schedules(workspace_id)}
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/connectors")
def connectors_create(workspace_id: str, req: ConnectorCreateRequest, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "connectors:manage")
        connector = create_connector(user["id"], workspace_id, name=req.name, connector_type=req.connector_type, host=req.host, port=req.port, database=req.database, username=req.username, password=req.password, ssl_mode=req.ssl_mode, options=req.options)
        record_event("connector.create", user_id=user["id"], workspace_id=workspace_id, resource_type="connector", resource_id=connector["id"], payload={"type":req.connector_type,"host":req.host,"database":req.database})
        return {"connector": connector}
    except Exception as exc:
        _handle(exc)


@router.patch("/workspaces/{workspace_id}/connectors/{connector_id}")
def connectors_update(workspace_id: str, connector_id: str, req: ConnectorUpdateRequest, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "connectors:manage")
        connector = update_connector(user["id"], workspace_id, connector_id, **req.model_dump())
        record_event("connector.update", user_id=user["id"], workspace_id=workspace_id, resource_type="connector", resource_id=connector_id)
        return {"connector": connector}
    except Exception as exc:
        _handle(exc)


@router.delete("/workspaces/{workspace_id}/connectors/{connector_id}")
def connectors_delete(workspace_id: str, connector_id: str, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "connectors:manage")
        delete_connector(workspace_id, connector_id)
        record_event("connector.delete", user_id=user["id"], workspace_id=workspace_id, resource_type="connector", resource_id=connector_id)
        return {"deleted": True, "connector_id": connector_id}
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/connectors/{connector_id}/test")
def connectors_test(workspace_id: str, connector_id: str, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "connectors:manage")
        result = test_connector(workspace_id, connector_id)
        record_event("connector.test", user_id=user["id"], workspace_id=workspace_id, resource_type="connector", resource_id=connector_id, outcome="success" if result.get("ok") else "failed", payload={"status":result.get("status")})
        return result
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/connectors/{connector_id}/discover")
def connectors_discover(workspace_id: str, connector_id: str, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "connectors:manage")
        return discover_connector(workspace_id, connector_id)
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/sources")
def connector_sources_list(workspace_id: str, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "connectors:read")
        _, sources = _connector_catalog_for_user(user["id"], workspace_id)
        return {"sources": sources, "health": workspace_refresh_health(workspace_id)}
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/sources")
def connector_sources_create(workspace_id: str, req: ConnectorSourceCreateRequest, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "connectors:manage")
        source = create_source(user["id"], workspace_id, connector_id=req.connector_id, name=req.name, source_kind=req.source_kind, table_name=req.table_name, query=req.query, refresh_mode=req.refresh_mode, incremental_column=req.incremental_column, freshness_sla_minutes=req.freshness_sla_minutes, schema_drift_policy=req.schema_drift_policy, source_options=req.source_options)
        record_event("connector.source.create", user_id=user["id"], workspace_id=workspace_id, resource_type="connector_source", resource_id=source["id"], payload={"connector_id":req.connector_id,"mode":req.refresh_mode})
        return {"source": source}
    except Exception as exc:
        _handle(exc)


@router.delete("/workspaces/{workspace_id}/sources/{source_id}")
def connector_sources_delete(workspace_id: str, source_id: str, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "connectors:manage")
        delete_source(workspace_id, source_id)
        record_event("connector.source.delete", user_id=user["id"], workspace_id=workspace_id, resource_type="connector_source", resource_id=source_id)
        return {"deleted": True, "source_id": source_id}
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/sources/{source_id}/preview")
def connector_source_preview(workspace_id: str, source_id: str, limit: int = Query(default=50, ge=1, le=500), user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "connectors:manage")
        return preview_source(workspace_id, source_id, limit)
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/sources/{source_id}/refresh")
def connector_source_refresh(workspace_id: str, source_id: str, req: ConnectorRefreshRequest, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "refresh:run")
        source = get_source(workspace_id, source_id)
        if req.background:
            ws = get_workspace(user["id"], workspace_id)
            job = submit_job(user_id=user["id"], organization_id=ws["organization_id"], workspace_id=workspace_id, job_type="connector_refresh", dataset_id=source.get("dataset_id"), payload={"source_id":source_id,"trigger":"manual"})
            record_event("connector.refresh.queued", user_id=user["id"], workspace_id=workspace_id, resource_type="connector_source", resource_id=source_id, payload={"job_id":job["id"]})
            return {"queued": True, "job": job}
        result = refresh_source(workspace_id, source_id, actor_id=user["id"], trigger="manual")
        record_event("connector.refresh.completed", user_id=user["id"], workspace_id=workspace_id, resource_type="connector_source", resource_id=source_id, payload={"dataset_id":result.get("dataset_id"),"rows":result.get("rows_fetched")})
        return {"queued": False, "refresh": result}
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/sources/{source_id}/schedule")
def connector_source_schedule(workspace_id: str, source_id: str, req: RefreshScheduleRequest, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "connectors:manage")
        schedule = save_schedule(workspace_id, source_id, enabled=req.enabled, interval_minutes=req.interval_minutes, actor_id=user["id"])
        record_event("connector.schedule.save", user_id=user["id"], workspace_id=workspace_id, resource_type="connector_source", resource_id=source_id, payload={"enabled":req.enabled,"interval_minutes":req.interval_minutes})
        return {"schedule": schedule}
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/refresh-runs")
def connector_refresh_runs(workspace_id: str, source_id: str | None = Query(default=None), limit: int = Query(default=100, ge=1, le=500), user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "connectors:read")
        return {"runs": get_refresh_runs(workspace_id, source_id, limit)}
    except Exception as exc:
        _handle(exc)
