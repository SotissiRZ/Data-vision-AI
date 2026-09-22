from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.services.performance_evidence import canonical_sha256, evaluate_metrics, validate_external_evidence

client = TestClient(app)


def _use_store(tmp_path: Path, monkeypatch):
    from app.core.config import get_settings
    from app.services import metadata_store

    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'performance277.db'}")
    monkeypatch.setattr(settings, "metadata_fallback_sqlite", True)
    monkeypatch.setattr(settings, "schema_auto_migrate", True)
    metadata_store._ENGINES.clear()
    metadata_store._SELECTED_BACKENDS.clear()


def _boot(tmp_path: Path, monkeypatch):
    _use_store(tmp_path, monkeypatch)
    response = client.post(
        "/api/v1/auth/bootstrap",
        json={
            "email": "perf277@datavision.local",
            "password": "Performance277!",
            "display_name": "Performance 277",
            "organization_name": "Performance Lab",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    return body, {"Authorization": f"Bearer {body['access_token']}"}


def _production_evidence(**overrides):
    payload = {
        "schema": "datavision.performance-evidence/v1",
        "product_version": "2.77.0",
        "profile": "production_standard",
        "execution_context": "production",
        "target": "https://prod.example.test/ready",
        "started_at": "2026-09-22T01:00:00+00:00",
        "completed_at": "2026-09-22T01:01:00+00:00",
        "metrics": {
            "request_p50_ms": 100.0,
            "request_p95_ms": 300.0,
            "request_p99_ms": 600.0,
            "error_rate_pct": 0.2,
            "throughput_rps": 42.0,
            "total_requests": 2500,
            "successful_requests": 2495,
        },
        "runner": {"kind": "http_threadpool", "duration_seconds": 60.0, "concurrency": 20},
        "environment": {"runner": "ci-production"},
    }
    payload.update(overrides)
    payload["artifact_sha256"] = canonical_sha256(payload)
    return payload


def test_budget_evaluator_handles_upper_and_lower_bounds():
    result = evaluate_metrics(
        {"p95": 200, "throughput": 30},
        [
            {"metric": "p95", "operator": "<=", "threshold": 250, "unit": "ms"},
            {"metric": "throughput", "operator": ">=", "threshold": 20, "unit": "rps"},
        ],
    )
    assert result["status"] == "passed"
    assert not result["violations"]

    failed = evaluate_metrics(
        {"p95": 500, "throughput": 10},
        [
            {"metric": "p95", "operator": "<=", "threshold": 250, "unit": "ms"},
            {"metric": "throughput", "operator": ">=", "threshold": 20, "unit": "rps"},
        ],
    )
    assert failed["status"] == "failed"
    assert len(failed["violations"]) == 2


def test_external_evidence_requires_nonlocal_https_and_minimum_load():
    good = validate_external_evidence(_production_evidence())
    assert good["status"] == "passed"
    assert good["production_evidence"] is True
    assert len(good["source_artifact_sha256"]) == 64

    local = _production_evidence(target="http://localhost:8000/ready")
    local["artifact_sha256"] = canonical_sha256(local)
    invalid = validate_external_evidence(local)
    assert invalid["status"] == "failed"
    assert invalid["production_evidence"] is False
    assert any(row["metric"] == "target" for row in invalid["violations"])


def test_external_evidence_rejects_tampered_sha256():
    payload = _production_evidence()
    payload["metrics"]["request_p95_ms"] = 999.0
    try:
        validate_external_evidence(payload)
    except ValueError as exc:
        assert "SHA-256" in str(exc)
    else:
        raise AssertionError("tampered evidence must be rejected")


def test_local_benchmark_is_persisted_and_never_claims_production(tmp_path, monkeypatch):
    _use_store(tmp_path, monkeypatch)
    from app.services import performance_evidence
    from app.services.schema_migrations import migration_status

    monkeypatch.setattr(
        performance_evidence,
        "_build_local_metrics",
        lambda **_: {
            "metadata_query_p50_ms": 1.0,
            "metadata_query_p95_ms": 2.0,
            "dataframe_groupby_p50_ms": 5.0,
            "dataframe_groupby_p95_ms": 8.0,
            "json_roundtrip_p50_ms": 1.0,
            "json_roundtrip_p95_ms": 2.0,
            "benchmark_error_rate_pct": 0.0,
            "benchmark_throughput_ops": 100.0,
            "operations": 15,
            "duration_ms": 100.0,
        },
    )
    run = performance_evidence.run_local_benchmark("user", "workspace", samples=5, rows=1000)
    assert run["status"] == "passed"
    assert run["production_evidence"] is False
    assert len(run["artifact_sha256"]) == 64
    status = performance_evidence.performance_evidence_status("workspace")
    assert status["latest_local"]["id"] == run["id"]
    assert status["production_evidence_status"] == "not_evidenced"
    assert "2.77.0-001" in migration_status()["applied"]


def test_imported_production_evidence_updates_workspace_status(tmp_path, monkeypatch):
    _use_store(tmp_path, monkeypatch)
    from app.services.performance_evidence import import_external_evidence, performance_evidence_status

    imported = import_external_evidence("user", "workspace", _production_evidence())
    assert imported["status"] == "passed"
    assert imported["production_evidence"] is True
    assert imported["source_artifact_sha256"]
    status = performance_evidence_status("workspace")
    assert status["latest_production"]["id"] == imported["id"]
    # The fixture timestamp is intentionally old relative to runtime; staleness must be explicit.
    assert status["production_evidence_status"] in {"passed", "stale"}


def test_performance_api_exposes_policy_runs_and_governed_benchmark(tmp_path, monkeypatch):
    boot, headers = _boot(tmp_path, monkeypatch)
    ws = boot["workspace_id"]
    from app.services import performance_evidence

    monkeypatch.setattr(
        performance_evidence,
        "_build_local_metrics",
        lambda **_: {
            "metadata_query_p50_ms": 1.0,
            "metadata_query_p95_ms": 2.0,
            "dataframe_groupby_p50_ms": 3.0,
            "dataframe_groupby_p95_ms": 4.0,
            "json_roundtrip_p50_ms": 1.0,
            "json_roundtrip_p95_ms": 2.0,
            "benchmark_error_rate_pct": 0.0,
            "benchmark_throughput_ops": 120.0,
            "operations": 15,
            "duration_ms": 80.0,
        },
    )
    run = client.post(
        f"/api/v1/workspaces/{ws}/operational/performance/benchmark",
        headers=headers,
        json={"profile": "local_smoke", "samples": 5, "rows": 1000},
    )
    assert run.status_code == 200, run.text
    assert run.json()["evidence"]["status"] == "passed"
    status = client.get(f"/api/v1/workspaces/{ws}/operational/performance", headers=headers)
    assert status.status_code == 200, status.text
    body = status.json()
    assert body["policy_schema"] == "datavision.performance-slo-policy/v1"
    assert body["latest_local"]["source"] == "local_benchmark"
    assert body["production_evidence_valid"] is False
