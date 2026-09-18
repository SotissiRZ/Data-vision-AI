from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.config import get_settings

from app.services.auth_service import bootstrap, decode_token, get_user, login, session_payload, has_permission, workspace_role
from app.services.audit_service import list_events, record_event
from app.services.job_service import get_job, list_jobs, request_cancel, submit_job, queue_status
from app.services.metadata_store import metadata_backend, fetch_one
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
    job_type: str = Field(pattern="^(automl|ai_analysis|forecast|report)$")
    dataset_id: str | None = None
    payload: dict[str, Any] = {}


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
