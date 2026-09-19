from __future__ import annotations

import ipaddress
import os
import socket
import uuid
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, model_validator

from app.core.config import get_settings
from app.services.audit_service import record_event
from app.services.auth_service import has_permission
from app.services.identity_service import resolve_secret
from app.services.metadata_store import (
    execute,
    fetch_all,
    fetch_one,
    json_dumps,
    json_loads,
    utcnow,
)
from app.services.operational_intelligence import record_telemetry
from app.services.tenant_access import current_access_context

from .model_gateway import (
    ModelGateway,
    ModelProvider,
    ModelRequest,
    ModelResponse,
    ProviderCapabilities,
    ProviderDescriptor,
    ProviderRegistry,
    RoutingPolicy,
)
from .providers.ollama import OllamaProvider
from .providers.openai_compatible import OpenAICompatibleProvider

ScopeType = Literal["local", "workspace"]
ProviderType = Literal["ollama", "openai_compatible"]
ProviderLocation = Literal["local", "external"]

LOCAL_SCOPE_ID = "__local__"


class ExternalDataPolicy(BaseModel):
    include_column_names: bool = True
    include_sample_values: bool = False
    include_row_data: bool = False
    max_recent_events: int = Field(default=5, ge=0, le=50)


class AssistantAISettings(BaseModel):
    planner_mode: Literal["deterministic", "gateway"] = "deterministic"
    privacy_mode: Literal["local_only", "prefer_local", "allow_external"] = "local_only"
    allow_external_ai: bool = False
    allow_provider_fallback: bool = True
    fallback_to_deterministic: bool = True
    task_routes: dict[str, str | None] = Field(
        default_factory=lambda: {
            "planner": None,
            "explanation": None,
            "critic": None,
            "summarization": None,
        }
    )
    fallback_order: list[str] = Field(default_factory=list)
    monthly_budget_usd: float = Field(default=0.0, ge=0, le=1_000_000)
    deny_external_when_cost_unknown: bool = False
    external_data_policy: ExternalDataPolicy = Field(default_factory=ExternalDataPolicy)

    @model_validator(mode="after")
    def validate_external_mode(self):
        if self.privacy_mode == "local_only":
            self.allow_external_ai = False
        # These remain hard invariants. The settings UI cannot opt into raw rows.
        self.external_data_policy.include_sample_values = False
        self.external_data_policy.include_row_data = False
        return self


class ProviderProfileInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    provider_type: ProviderType
    location: ProviderLocation
    base_url: str = Field(min_length=1, max_length=500)
    model: str = Field(min_length=1, max_length=200)
    enabled: bool = True
    priority: int = Field(default=100, ge=1, le=10_000)
    structured_output: bool = True
    max_context_tokens: int | None = Field(default=None, ge=1024, le=10_000_000)
    secret_id: str | None = None
    api_key_env: str | None = Field(default=None, max_length=200)
    input_cost_per_million: float | None = Field(default=None, ge=0)
    output_cost_per_million: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_profile(self):
        self.name = self.name.strip()
        self.base_url = self.base_url.strip().rstrip("/")
        self.model = self.model.strip()
        if self.location == "external" and self.provider_type == "ollama":
            # Ollama may be remote, but it is still explicitly external.
            pass
        if self.secret_id:
            self.secret_id = self.secret_id.strip()
        if self.api_key_env:
            self.api_key_env = self.api_key_env.strip()
        return self


class ProviderProfile(ProviderProfileInput):
    id: str
    scope_type: ScopeType
    scope_id: str
    created_at: str
    updated_at: str


def _ensure_tables() -> None:
    execute(
        """CREATE TABLE IF NOT EXISTS assistant_ai_settings (
            scope_type TEXT NOT NULL,
            scope_id TEXT NOT NULL,
            config_json TEXT NOT NULL,
            updated_by TEXT,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (scope_type, scope_id)
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS assistant_model_providers (
            id TEXT PRIMARY KEY,
            scope_type TEXT NOT NULL,
            scope_id TEXT NOT NULL,
            name TEXT NOT NULL,
            provider_type TEXT NOT NULL,
            location TEXT NOT NULL,
            base_url TEXT NOT NULL,
            model TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            priority INTEGER NOT NULL DEFAULT 100,
            structured_output INTEGER NOT NULL DEFAULT 1,
            max_context_tokens INTEGER,
            secret_id TEXT,
            api_key_env TEXT,
            input_cost_per_million REAL,
            output_cost_per_million REAL,
            created_by TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )"""
    )


def scope_from_access(*, require_manage: bool = False) -> tuple[ScopeType, str, str | None]:
    access = current_access_context()
    if access is None:
        return "local", LOCAL_SCOPE_ID, None
    if require_manage and not has_permission(
        access.user_id,
        access.workspace_id,
        "workspace:manage",
    ):
        raise PermissionError("Permission insuffisante: workspace:manage.")
    return "workspace", access.workspace_id, access.user_id


def scope_for_context(workspace_id: str | None) -> tuple[ScopeType, str, str | None]:
    if not workspace_id:
        return "local", LOCAL_SCOPE_ID, None

    access = current_access_context()
    if access is None or str(access.workspace_id) != str(workspace_id):
        raise PermissionError(
            "Le contexte assistant ne correspond pas au workspace authentifié."
        )
    return "workspace", access.workspace_id, access.user_id


def get_ai_settings(scope_type: ScopeType, scope_id: str) -> AssistantAISettings:
    _ensure_tables()
    row = fetch_one(
        "SELECT config_json FROM assistant_ai_settings WHERE scope_type=:type AND scope_id=:id",
        {"type": scope_type, "id": scope_id},
    )
    if not row:
        return AssistantAISettings()
    return AssistantAISettings.model_validate(
        json_loads(row.get("config_json"), {})
    )


def save_ai_settings(
    scope_type: ScopeType,
    scope_id: str,
    settings: AssistantAISettings,
    *,
    actor_id: str | None,
) -> AssistantAISettings:
    _ensure_tables()
    now = utcnow()
    payload = json_dumps(settings.model_dump(mode="json"))
    existing = fetch_one(
        "SELECT scope_id FROM assistant_ai_settings WHERE scope_type=:type AND scope_id=:id",
        {"type": scope_type, "id": scope_id},
    )
    if existing:
        execute(
            """UPDATE assistant_ai_settings
               SET config_json=:config,updated_by=:user,updated_at=:now
               WHERE scope_type=:type AND scope_id=:id""",
            {
                "config": payload,
                "user": actor_id,
                "now": now,
                "type": scope_type,
                "id": scope_id,
            },
        )
    else:
        execute(
            """INSERT INTO assistant_ai_settings(
                scope_type,scope_id,config_json,updated_by,updated_at
               ) VALUES(:type,:id,:config,:user,:now)""",
            {
                "type": scope_type,
                "id": scope_id,
                "config": payload,
                "user": actor_id,
                "now": now,
            },
        )

    record_event(
        "assistant.ai_settings_update",
        user_id=actor_id,
        workspace_id=scope_id if scope_type == "workspace" else None,
        resource_type="assistant_ai_settings",
        resource_id=scope_id,
        payload={
            "planner_mode": settings.planner_mode,
            "privacy_mode": settings.privacy_mode,
            "allow_external_ai": settings.allow_external_ai,
        },
    )
    return settings


def _provider_from_row(row: dict[str, Any]) -> ProviderProfile:
    return ProviderProfile(
        id=str(row["id"]),
        scope_type=str(row["scope_type"]),
        scope_id=str(row["scope_id"]),
        name=str(row["name"]),
        provider_type=str(row["provider_type"]),
        location=str(row["location"]),
        base_url=str(row["base_url"]),
        model=str(row["model"]),
        enabled=bool(row.get("enabled")),
        priority=int(row.get("priority") or 100),
        structured_output=bool(row.get("structured_output")),
        max_context_tokens=(
            int(row["max_context_tokens"])
            if row.get("max_context_tokens") is not None
            else None
        ),
        secret_id=row.get("secret_id"),
        api_key_env=row.get("api_key_env"),
        input_cost_per_million=(
            float(row["input_cost_per_million"])
            if row.get("input_cost_per_million") is not None
            else None
        ),
        output_cost_per_million=(
            float(row["output_cost_per_million"])
            if row.get("output_cost_per_million") is not None
            else None
        ),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def list_provider_profiles(scope_type: ScopeType, scope_id: str) -> list[ProviderProfile]:
    _ensure_tables()
    return [
        _provider_from_row(row)
        for row in fetch_all(
            """SELECT * FROM assistant_model_providers
               WHERE scope_type=:type AND scope_id=:id
               ORDER BY priority,name""",
            {"type": scope_type, "id": scope_id},
        )
    ]


def get_provider_profile(
    scope_type: ScopeType,
    scope_id: str,
    provider_id: str,
) -> ProviderProfile:
    _ensure_tables()
    row = fetch_one(
        """SELECT * FROM assistant_model_providers
           WHERE id=:provider AND scope_type=:type AND scope_id=:id""",
        {"provider": provider_id, "type": scope_type, "id": scope_id},
    )
    if not row:
        raise KeyError("Provider introuvable.")
    return _provider_from_row(row)


def _validate_provider_url(profile: ProviderProfileInput, *, resolve_dns: bool = False) -> None:
    parsed = urlparse(profile.base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("URL provider invalide.")
    if parsed.username or parsed.password:
        raise ValueError("Credentials interdits dans l'URL provider.")

    if profile.location == "external" and parsed.scheme != "https":
        raise ValueError("HTTPS est obligatoire pour un provider externe.")

    if profile.location == "external" and resolve_dns:
        try:
            infos = socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise ValueError("DNS du provider externe introuvable.") from exc
        for info in infos:
            ip = ipaddress.ip_address(info[4][0])
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_reserved
                or ip.is_multicast
            ):
                raise ValueError(
                    "Provider externe refusé par la garde SSRF."
                )


def save_provider_profile(
    scope_type: ScopeType,
    scope_id: str,
    payload: ProviderProfileInput,
    *,
    actor_id: str | None,
    provider_id: str | None = None,
) -> ProviderProfile:
    _ensure_tables()
    _validate_provider_url(payload, resolve_dns=False)

    if scope_type == "workspace" and payload.api_key_env:
        raise ValueError(
            "En workspace Enterprise, utilisez un secret du Secret Vault plutôt qu'une variable locale."
        )
    if scope_type == "local" and payload.secret_id:
        raise ValueError(
            "Le Secret Vault est workspace-scoped. En mode local utilisez api_key_env."
        )

    now = utcnow()
    pid = provider_id or str(uuid.uuid4())
    existing = fetch_one(
        """SELECT id FROM assistant_model_providers
           WHERE id=:provider AND scope_type=:type AND scope_id=:id""",
        {"provider": pid, "type": scope_type, "id": scope_id},
    )

    values = {
        "provider": pid,
        "type": scope_type,
        "id": scope_id,
        "name": payload.name,
        "provider_type": payload.provider_type,
        "location": payload.location,
        "base_url": payload.base_url,
        "model": payload.model,
        "enabled": 1 if payload.enabled else 0,
        "priority": payload.priority,
        "structured": 1 if payload.structured_output else 0,
        "max_context": payload.max_context_tokens,
        "secret": payload.secret_id or None,
        "api_env": payload.api_key_env or None,
        "input_cost": payload.input_cost_per_million,
        "output_cost": payload.output_cost_per_million,
        "user": actor_id,
        "now": now,
    }

    if existing:
        execute(
            """UPDATE assistant_model_providers
               SET name=:name,provider_type=:provider_type,location=:location,
                   base_url=:base_url,model=:model,enabled=:enabled,
                   priority=:priority,structured_output=:structured,
                   max_context_tokens=:max_context,secret_id=:secret,
                   api_key_env=:api_env,input_cost_per_million=:input_cost,
                   output_cost_per_million=:output_cost,updated_at=:now
               WHERE id=:provider AND scope_type=:type AND scope_id=:id""",
            values,
        )
        event = "assistant.model_provider_update"
    else:
        execute(
            """INSERT INTO assistant_model_providers(
                id,scope_type,scope_id,name,provider_type,location,base_url,model,
                enabled,priority,structured_output,max_context_tokens,secret_id,
                api_key_env,input_cost_per_million,output_cost_per_million,
                created_by,created_at,updated_at
               ) VALUES(
                :provider,:type,:id,:name,:provider_type,:location,:base_url,:model,
                :enabled,:priority,:structured,:max_context,:secret,
                :api_env,:input_cost,:output_cost,:user,:now,:now
               )""",
            values,
        )
        event = "assistant.model_provider_create"

    record_event(
        event,
        user_id=actor_id,
        workspace_id=scope_id if scope_type == "workspace" else None,
        resource_type="assistant_model_provider",
        resource_id=pid,
        payload={
            "name": payload.name,
            "provider_type": payload.provider_type,
            "location": payload.location,
            "model": payload.model,
        },
    )
    return get_provider_profile(scope_type, scope_id, pid)


def delete_provider_profile(
    scope_type: ScopeType,
    scope_id: str,
    provider_id: str,
    *,
    actor_id: str | None,
) -> None:
    _ = get_provider_profile(scope_type, scope_id, provider_id)
    execute(
        """DELETE FROM assistant_model_providers
           WHERE id=:provider AND scope_type=:type AND scope_id=:id""",
        {"provider": provider_id, "type": scope_type, "id": scope_id},
    )
    record_event(
        "assistant.model_provider_delete",
        user_id=actor_id,
        workspace_id=scope_id if scope_type == "workspace" else None,
        resource_type="assistant_model_provider",
        resource_id=provider_id,
    )


def _resolve_api_key(
    profile: ProviderProfile,
    scope_type: ScopeType,
    scope_id: str,
) -> str | None:
    if profile.secret_id:
        if scope_type != "workspace":
            raise ValueError("Secret Vault indisponible hors workspace.")
        return resolve_secret(scope_id, profile.secret_id)

    if profile.api_key_env:
        value = os.getenv(profile.api_key_env)
        if value is None:
            raise RuntimeError(
                f"Variable d'environnement absente: {profile.api_key_env}"
            )
        return value

    return None


def _instantiate_provider(
    profile: ProviderProfile,
    scope_type: ScopeType,
    scope_id: str,
) -> ModelProvider:
    _validate_provider_url(profile, resolve_dns=profile.location == "external")
    kind = "local" if profile.location == "local" else "openai_compatible"
    descriptor = ProviderDescriptor(
        id=profile.id,
        kind=kind,
        model=profile.model,
        priority=profile.priority,
        enabled=profile.enabled,
        capabilities=ProviderCapabilities(
            structured_output=profile.structured_output,
            tools=False,
            streaming=False,
            max_context_tokens=profile.max_context_tokens,
        ),
        metadata={
            "profile_name": profile.name,
            "provider_type": profile.provider_type,
            "location": profile.location,
            "pricing": {
                "input_cost_per_million": profile.input_cost_per_million,
                "output_cost_per_million": profile.output_cost_per_million,
            },
        },
    )

    if profile.provider_type == "ollama":
        return OllamaProvider(
            descriptor=descriptor,
            base_url=profile.base_url,
        )

    return OpenAICompatibleProvider(
        descriptor=descriptor,
        base_url=profile.base_url,
        api_key=_resolve_api_key(profile, scope_type, scope_id),
    )


def monthly_usage(scope_type: ScopeType, scope_id: str) -> dict[str, Any]:
    first = datetime.now(timezone.utc).replace(
        day=1,
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    ).isoformat()

    if scope_type == "workspace":
        row = fetch_one(
            """SELECT
                 COALESCE(SUM(input_tokens),0) AS input_tokens,
                 COALESCE(SUM(output_tokens),0) AS output_tokens,
                 COALESCE(SUM(estimated_cost_usd),0) AS cost,
                 SUM(CASE WHEN estimated_cost_usd IS NULL THEN 1 ELSE 0 END) AS unknown_cost_calls,
                 COUNT(*) AS calls
               FROM telemetry_events
               WHERE event_kind='assistant_model'
                 AND workspace_id=:ws
                 AND created_at>=:since""",
            {"ws": scope_id, "since": first},
        ) or {}
    else:
        row = fetch_one(
            """SELECT
                 COALESCE(SUM(input_tokens),0) AS input_tokens,
                 COALESCE(SUM(output_tokens),0) AS output_tokens,
                 COALESCE(SUM(estimated_cost_usd),0) AS cost,
                 SUM(CASE WHEN estimated_cost_usd IS NULL THEN 1 ELSE 0 END) AS unknown_cost_calls,
                 COUNT(*) AS calls
               FROM telemetry_events
               WHERE event_kind='assistant_model'
                 AND workspace_id IS NULL
                 AND created_at>=:since""",
            {"since": first},
        ) or {}

    return {
        "month_start": first,
        "calls": int(row.get("calls") or 0),
        "input_tokens": int(row.get("input_tokens") or 0),
        "output_tokens": int(row.get("output_tokens") or 0),
        "estimated_cost_usd": round(float(row.get("cost") or 0.0), 8),
        "unknown_cost_calls": int(row.get("unknown_cost_calls") or 0),
    }


def _estimated_max_request_cost(provider: ModelProvider, request: ModelRequest) -> float | None:
    if provider.descriptor.kind == "local":
        return 0.0
    pricing = provider.descriptor.metadata.get("pricing") or {}
    input_rate = pricing.get("input_cost_per_million")
    output_rate = pricing.get("output_cost_per_million")
    if input_rate is None or output_rate is None:
        return None
    # Conservative, deterministic estimate without sending content anywhere.
    approximate_input_tokens = max(
        1,
        int((len(request.system) + len(request.user)) / 4),
    )
    return round(
        approximate_input_tokens / 1_000_000.0 * float(input_rate)
        + request.max_output_tokens / 1_000_000.0 * float(output_rate),
        8,
    )


def build_model_gateway_for_scope(
    scope_type: ScopeType,
    scope_id: str,
    *,
    actor_id: str | None = None,
) -> ModelGateway:
    settings = get_ai_settings(scope_type, scope_id)
    registry = ProviderRegistry()

    for profile in list_provider_profiles(scope_type, scope_id):
        if not profile.enabled:
            continue
        try:
            registry.register(
                _instantiate_provider(profile, scope_type, scope_id)
            )
        except Exception:
            # A broken provider configuration must not prevent other providers
            # from being available. Connection test exposes its exact error.
            continue

    def guard(provider: ModelProvider, request: ModelRequest) -> None:
        if provider.descriptor.kind == "local":
            return

        if not settings.allow_external_ai:
            raise PermissionError(
                "Les providers externes sont désactivés pour ce contexte."
            )

        usage = monthly_usage(scope_type, scope_id)
        budget = float(settings.monthly_budget_usd or 0.0)
        if budget <= 0:
            return

        spent = float(usage["estimated_cost_usd"])
        if spent >= budget:
            raise PermissionError(
                f"Budget IA mensuel atteint ({spent:.4f} / {budget:.4f} USD)."
            )

        estimated = _estimated_max_request_cost(provider, request)
        if estimated is None:
            if settings.deny_external_when_cost_unknown:
                raise PermissionError(
                    "Coût du provider inconnu et politique deny_external_when_cost_unknown active."
                )
            return

        if spent + estimated > budget:
            raise PermissionError(
                "Cette requête pourrait dépasser le budget IA mensuel."
            )

    def record(provider: ModelProvider, request: ModelRequest, response: ModelResponse) -> None:
        workspace_id = scope_id if scope_type == "workspace" else None
        record_telemetry(
            event_kind="assistant_model",
            name=f"{request.task}:{provider.descriptor.id}",
            status="success",
            workspace_id=workspace_id,
            user_id=actor_id,
            feature="DataVision AI",
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            estimated_cost_usd=response.usage.estimated_cost_usd,
            resource_type="model_provider",
            resource_id=provider.descriptor.id,
            metadata={
                "model": provider.descriptor.model,
                "kind": provider.descriptor.kind,
                "task": request.task,
            },
        )

    return ModelGateway(
        registry,
        provider_guard=guard,
        response_hook=record,
    )


def routing_policy_for_settings(
    settings: AssistantAISettings,
    *,
    task: str,
) -> RoutingPolicy:
    preferred = settings.task_routes.get(task)
    fallback = tuple(
        provider_id
        for provider_id in settings.fallback_order
        if provider_id != preferred
    )
    return RoutingPolicy(
        privacy_mode=settings.privacy_mode,
        allow_external_ai=settings.allow_external_ai,
        require_structured_output=(task == "planner"),
        preferred_provider_id=preferred,
        fallback_provider_ids=fallback,
        allow_fallback=settings.allow_provider_fallback,
    )


def route_preview(
    scope_type: ScopeType,
    scope_id: str,
    *,
    task: str,
) -> dict[str, Any]:
    settings = get_ai_settings(scope_type, scope_id)
    gateway = build_model_gateway_for_scope(scope_type, scope_id)
    request = ModelRequest(
        task=task,
        system="",
        user="",
        response_schema={"type": "object"} if task == "planner" else None,
        max_output_tokens=100,
    )
    policy = routing_policy_for_settings(settings, task=task)
    candidates = gateway.candidate_providers(
        request=request,
        policy=policy,
    )
    return {
        "task": task,
        "planner_mode": settings.planner_mode,
        "privacy_mode": settings.privacy_mode,
        "allow_external_ai": settings.allow_external_ai,
        "candidates": [
            {
                "id": p.descriptor.id,
                "name": p.descriptor.metadata.get("profile_name") or p.descriptor.id,
                "kind": p.descriptor.kind,
                "model": p.descriptor.model,
                "location": p.descriptor.metadata.get("location"),
                "priority": p.descriptor.priority,
            }
            for p in candidates
        ],
        "selected_provider_id": (
            candidates[0].descriptor.id if candidates else None
        ),
    }


def test_provider_connection(
    scope_type: ScopeType,
    scope_id: str,
    provider_id: str,
    *,
    actor_id: str | None,
) -> dict[str, Any]:
    profile = get_provider_profile(scope_type, scope_id, provider_id)
    provider = _instantiate_provider(profile, scope_type, scope_id)

    started = perf_counter()
    response = provider.generate(
        ModelRequest(
            task="summarization",
            system=(
                "Test de connectivité DataVision. "
                "Réponds uniquement par OK."
            ),
            user="OK",
            temperature=0.0,
            max_output_tokens=16,
        )
    )
    elapsed = round((perf_counter() - started) * 1000.0, 2)

    # Connection test contains no dataset/user content.
    record_event(
        "assistant.model_provider_test",
        user_id=actor_id,
        workspace_id=scope_id if scope_type == "workspace" else None,
        resource_type="assistant_model_provider",
        resource_id=provider_id,
        payload={"success": True, "latency_ms": elapsed},
    )
    return {
        "ok": True,
        "provider_id": provider_id,
        "model": response.model,
        "latency_ms": elapsed,
        "response": response.text[:120],
        "usage": response.usage.model_dump(mode="json"),
        "note": "Le test n'envoie aucune donnée de dataset.",
    }
