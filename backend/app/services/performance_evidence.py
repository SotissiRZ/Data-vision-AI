from __future__ import annotations

import hashlib
import json
import os
import platform
import statistics
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

import pandas as pd

from app.services.metadata_store import execute, fetch_all, fetch_one, json_dumps, json_loads, metadata_backend, utcnow

ROOT = Path(__file__).resolve().parents[3]
POLICY_PATH = ROOT / "policies" / "performance_slo.json"
EVIDENCE_SCHEMA = "datavision.performance-evidence/v1"


def _product_version() -> str:
    try:
        return (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return os.getenv("DATAVISION_VERSION", "unknown")


def load_performance_policy() -> dict[str, Any]:
    payload = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    if payload.get("schema") != "datavision.performance-slo-policy/v1":
        raise ValueError("Politique performance invalide")
    return payload


def profile_policy(profile: str) -> dict[str, Any]:
    profile = str(profile or "").strip()
    payload = load_performance_policy()
    selected = (payload.get("profiles") or {}).get(profile)
    if not isinstance(selected, dict):
        raise ValueError(f"Profil performance inconnu: {profile}")
    return {"profile": profile, **selected}


def canonical_sha256(payload: dict[str, Any]) -> str:
    clean = {k: v for k, v in payload.items() if k != "artifact_sha256"}
    encoded = json.dumps(clean, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(float(v) for v in values)
    if len(ordered) == 1:
        return round(ordered[0], 4)
    position = (len(ordered) - 1) * min(1.0, max(0.0, q))
    lower = int(position)
    upper = min(len(ordered) - 1, lower + 1)
    fraction = position - lower
    value = ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction
    return round(value, 4)


def evaluate_metrics(metrics: dict[str, Any], budgets: list[dict[str, Any]]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    for budget in budgets:
        metric = str(budget["metric"])
        operator = str(budget["operator"])
        threshold = float(budget["threshold"])
        raw = metrics.get(metric)
        observed = None if raw is None else float(raw)
        if observed is None:
            passed = False
        elif operator == "<=":
            passed = observed <= threshold
        elif operator == ">=":
            passed = observed >= threshold
        else:
            raise ValueError(f"Opérateur de budget non supporté: {operator}")
        checks.append({
            "metric": metric,
            "operator": operator,
            "threshold": threshold,
            "unit": budget.get("unit"),
            "observed": observed,
            "passed": passed,
        })
    violations = [check for check in checks if not check["passed"]]
    return {"status": "passed" if not violations else "failed", "checks": checks, "violations": violations}


def _measure(fn: Callable[[], Any], samples: int) -> tuple[list[float], int]:
    latencies: list[float] = []
    errors = 0
    for _ in range(samples):
        start = time.perf_counter_ns()
        try:
            fn()
        except Exception:
            errors += 1
        finally:
            latencies.append((time.perf_counter_ns() - start) / 1_000_000.0)
    return latencies, errors


def _local_environment(rows: int, samples: int) -> dict[str, Any]:
    raw = {
        "product_version": _product_version(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpu_count": os.cpu_count(),
        "metadata_backend": metadata_backend(),
        "pandas": pd.__version__,
        "rows": rows,
        "samples": samples,
    }
    raw["fingerprint_sha256"] = hashlib.sha256(
        json.dumps(raw, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    return raw


def _build_local_metrics(*, rows: int, samples: int) -> dict[str, Any]:
    # Deterministic input values; only measured duration varies by host.
    frame = pd.DataFrame({
        "group": [f"g{i % 20}" for i in range(rows)],
        "value": [(i * 17) % 10_003 for i in range(rows)],
        "weight": [1.0 + (i % 7) / 10.0 for i in range(rows)],
    })
    json_payload = {"rows": [{"id": i, "value": (i * 13) % 997} for i in range(min(rows, 2500))]}

    metadata_latencies, metadata_errors = _measure(lambda: fetch_one("SELECT 1 AS value"), samples)
    dataframe_latencies, dataframe_errors = _measure(
        lambda: frame.assign(weighted=frame["value"] * frame["weight"]).groupby("group", sort=True)["weighted"].agg(["count", "mean", "sum"]),
        samples,
    )
    json_latencies, json_errors = _measure(
        lambda: json.loads(json.dumps(json_payload, sort_keys=True, separators=(",", ":"))),
        samples,
    )
    total_ops = samples * 3
    total_ms = sum(metadata_latencies) + sum(dataframe_latencies) + sum(json_latencies)
    errors = metadata_errors + dataframe_errors + json_errors
    return {
        "metadata_query_p50_ms": _percentile(metadata_latencies, 0.50),
        "metadata_query_p95_ms": _percentile(metadata_latencies, 0.95),
        "dataframe_groupby_p50_ms": _percentile(dataframe_latencies, 0.50),
        "dataframe_groupby_p95_ms": _percentile(dataframe_latencies, 0.95),
        "json_roundtrip_p50_ms": _percentile(json_latencies, 0.50),
        "json_roundtrip_p95_ms": _percentile(json_latencies, 0.95),
        "benchmark_error_rate_pct": round(errors * 100.0 / max(total_ops, 1), 4),
        "benchmark_throughput_ops": round(total_ops / max(total_ms / 1000.0, 0.000001), 3),
        "operations": total_ops,
        "duration_ms": round(total_ms, 3),
    }


def _persist(actor_user_id: str | None, workspace_id: str, payload: dict[str, Any], *, source: str) -> dict[str, Any]:
    run_id = str(payload.get("id") or uuid.uuid4())
    created_at = str(payload.get("created_at") or utcnow())
    stored = {**payload, "id": run_id, "workspace_id": workspace_id, "created_at": created_at, "source": source}
    stored["artifact_sha256"] = canonical_sha256(stored)
    execute(
        "INSERT INTO performance_evidence_runs(id,workspace_id,profile,source,execution_context,target,status,artifact_sha256,payload_json,created_by,created_at) "
        "VALUES(:id,:ws,:profile,:source,:context,:target,:status,:sha,:payload,:user,:created)",
        {
            "id": run_id,
            "ws": workspace_id,
            "profile": stored.get("profile"),
            "source": source,
            "context": stored.get("execution_context"),
            "target": stored.get("target"),
            "status": stored.get("status"),
            "sha": stored["artifact_sha256"],
            "payload": json_dumps(stored),
            "user": actor_user_id,
            "created": created_at,
        },
    )
    return stored


def run_local_benchmark(
    actor_user_id: str | None,
    workspace_id: str,
    *,
    profile: str = "local_smoke",
    rows: int = 20_000,
    samples: int = 8,
) -> dict[str, Any]:
    policy = profile_policy(profile)
    if policy.get("execution_context") != "local":
        raise ValueError("Le benchmark in-process n'accepte qu'un profil local")
    min_samples = int(policy.get("min_samples") or 1)
    samples = max(min_samples, min(int(samples), 50))
    rows = max(1_000, min(int(rows), 100_000))
    started = datetime.now(timezone.utc).isoformat()
    metrics = _build_local_metrics(rows=rows, samples=samples)
    evaluation = evaluate_metrics(metrics, list(policy.get("budgets") or []))
    payload = {
        "schema": EVIDENCE_SCHEMA,
        "product_version": _product_version(),
        "profile": profile,
        "execution_context": "local",
        "target": "in-process",
        "started_at": started,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "metrics": metrics,
        "budgets": policy.get("budgets") or [],
        "checks": evaluation["checks"],
        "violations": evaluation["violations"],
        "status": evaluation["status"],
        "environment": _local_environment(rows, samples),
        "runner": {"kind": "in_process", "samples": samples, "rows": rows},
        "production_evidence": False,
        "note": "Preuve locale de non-régression; ne constitue pas une mesure de capacité production.",
    }
    return _persist(actor_user_id, workspace_id, payload, source="local_benchmark")


def _is_nonlocal_https_target(target: str) -> bool:
    parsed = urlparse(str(target or ""))
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and host not in {"", "localhost", "127.0.0.1", "::1"}


def _parse_iso(value: Any) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def validate_external_evidence(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict) or payload.get("schema") != EVIDENCE_SCHEMA:
        raise ValueError("Format de preuve performance invalide")
    profile = str(payload.get("profile") or "production_standard")
    policy = profile_policy(profile)
    if policy.get("execution_context") != "production":
        raise ValueError("Une preuve externe doit utiliser un profil production")
    supplied_sha = str(payload.get("artifact_sha256") or "").strip().lower()
    calculated_source_sha = canonical_sha256(payload)
    if supplied_sha and supplied_sha != calculated_source_sha:
        raise ValueError("SHA-256 de preuve invalide")
    source_artifact_sha256 = supplied_sha or calculated_source_sha
    metrics = payload.get("metrics") or {}
    if not isinstance(metrics, dict):
        raise ValueError("metrics doit être un objet")
    runner = payload.get("runner") or {}
    total_requests = int(metrics.get("total_requests") or 0)
    duration = float(runner.get("duration_seconds") or 0)
    concurrency = int(runner.get("concurrency") or 0)
    structural_violations: list[dict[str, Any]] = []
    requirements = {
        "total_requests": (total_requests, ">=", int(policy.get("min_requests") or 1)),
        "duration_seconds": (duration, ">=", float(policy.get("min_duration_seconds") or 0)),
        "concurrency": (concurrency, ">=", int(policy.get("min_concurrency") or 1)),
    }
    for metric, (observed, operator, threshold) in requirements.items():
        if observed < threshold:
            structural_violations.append({"metric": metric, "operator": operator, "threshold": threshold, "observed": observed, "passed": False})
    evaluation = evaluate_metrics(metrics, list(policy.get("budgets") or []))
    target_ok = _is_nonlocal_https_target(str(payload.get("target") or ""))
    if not target_ok:
        structural_violations.append({"metric": "target", "operator": "non-local https", "threshold": "https://production-host", "observed": payload.get("target"), "passed": False})
    violations = [*evaluation["violations"], *structural_violations]
    status = "passed" if not violations else "failed"
    normalized = {
        **payload,
        "schema": EVIDENCE_SCHEMA,
        "product_version": str(payload.get("product_version") or _product_version()),
        "profile": profile,
        "execution_context": "production",
        "metrics": metrics,
        "budgets": policy.get("budgets") or [],
        "checks": evaluation["checks"],
        "violations": violations,
        "status": status,
        "production_evidence": bool(target_ok and not structural_violations),
        "source_artifact_sha256": source_artifact_sha256,
    }
    normalized["artifact_sha256"] = canonical_sha256(normalized)
    return normalized


def import_external_evidence(actor_user_id: str | None, workspace_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    normalized = validate_external_evidence(payload)
    return _persist(actor_user_id, workspace_id, normalized, source="external_target")


def list_performance_evidence(workspace_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
    rows = fetch_all(
        "SELECT id,workspace_id,profile,source,execution_context,target,status,artifact_sha256,payload_json,created_by,created_at "
        "FROM performance_evidence_runs WHERE workspace_id=:ws ORDER BY created_at DESC LIMIT :limit",
        {"ws": workspace_id, "limit": max(1, min(int(limit), 200))},
    )
    result: list[dict[str, Any]] = []
    for row in rows:
        payload = json_loads(row.pop("payload_json", "{}"), {})
        result.append({**payload, **row})
    return result


def performance_evidence_status(workspace_id: str) -> dict[str, Any]:
    policy = load_performance_policy()
    runs = list_performance_evidence(workspace_id, limit=100)
    latest_local = next((row for row in runs if row.get("source") == "local_benchmark"), None)
    latest_production = next((row for row in runs if row.get("source") == "external_target" and row.get("production_evidence")), None)
    production_policy = profile_policy("production_standard")
    production_state = "not_evidenced"
    if latest_production:
        completed = _parse_iso(latest_production.get("completed_at") or latest_production.get("created_at"))
        age_hours = None if completed is None else max(0.0, (datetime.now(timezone.utc) - completed.astimezone(timezone.utc)).total_seconds() / 3600.0)
        if age_hours is not None and age_hours > float(production_policy.get("max_age_hours") or 168):
            production_state = "stale"
        else:
            production_state = "passed" if latest_production.get("status") == "passed" else "failed"
    return {
        "workspace_id": workspace_id,
        "policy_schema": policy.get("schema"),
        "policy_version": policy.get("policy_version"),
        "profiles": policy.get("profiles") or {},
        "operational_slo": policy.get("operational_slo") or {},
        "latest_local": latest_local,
        "latest_production": latest_production,
        "production_evidence_status": production_state,
        "production_evidence_valid": production_state == "passed",
        "runs": runs[:20],
        "note": "Les preuves locales et production sont séparées; DataVision ne transforme jamais un benchmark local en résultat production.",
    }
