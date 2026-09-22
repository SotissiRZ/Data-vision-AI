from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app

client = TestClient(app)


def _use_store(tmp_path: Path, monkeypatch):
    from app.services import metadata_store

    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'v278.db'}")
    monkeypatch.setattr(settings, "metadata_fallback_sqlite", True)
    monkeypatch.setattr(settings, "schema_auto_migrate", True)
    monkeypatch.setattr(settings, "default_product_plan", "entreprise")
    metadata_store._ENGINES.clear()
    metadata_store._SELECTED_BACKENDS.clear()


def _boot(tmp_path: Path, monkeypatch):
    _use_store(tmp_path, monkeypatch)
    response = client.post(
        "/api/v1/auth/bootstrap",
        json={
            "email": "v278@datavision.local",
            "password": "DataVision278!Safe",
            "display_name": "V278",
            "organization_name": "Gap Closure Lab",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    return body, {"Authorization": f"Bearer {body['access_token']}"}


def test_product_plan_assignment_and_workspace_quota_are_runtime_enforced(tmp_path, monkeypatch):
    boot, headers = _boot(tmp_path, monkeypatch)
    from app.services.product_plans import assign_organization_plan, workspace_plan_status

    org = boot["organization_id"]
    ws = boot["workspace_id"]
    assigned = assign_organization_plan(org, "starter", actor_user_id=boot["user"]["id"])
    assert assigned["plan_id"] == "starter"
    assert workspace_plan_status(ws)["plan_id"] == "starter"

    response = client.post(
        "/api/v1/workspaces",
        headers=headers,
        json={"organization_id": org, "name": "Second workspace"},
    )
    assert response.status_code == 403
    assert "Quota workspaces atteint" in response.text


def test_daily_usage_quota_is_atomic_and_fail_closed(tmp_path, monkeypatch):
    boot, _headers = _boot(tmp_path, monkeypatch)
    from app.services import product_plans

    product_plans.assign_organization_plan(boot["organization_id"], "starter", actor_user_id=boot["user"]["id"])
    monkeypatch.setitem(product_plans.PLAN_CATALOG["starter"]["quotas"], "assistant_turns_per_day", 2)
    ws = boot["workspace_id"]
    assert product_plans.consume_daily_quota(ws, "assistant_turns")["used"] == 1
    assert product_plans.consume_daily_quota(ws, "assistant_turns")["used"] == 2
    with pytest.raises(product_plans.QuotaExceeded):
        product_plans.consume_daily_quota(ws, "assistant_turns")
    assert product_plans.daily_usage(ws, "assistant_turns")["used"] == 2


def test_starter_plan_blocks_enterprise_identity_and_external_gateway(tmp_path, monkeypatch):
    boot, headers = _boot(tmp_path, monkeypatch)
    from app.services.product_plans import assign_organization_plan

    assign_organization_plan(boot["organization_id"], "starter", actor_user_id=boot["user"]["id"])
    ws = boot["workspace_id"]
    oidc = client.post(
        f"/api/v1/workspaces/{ws}/identity/oidc",
        headers=headers,
        json={
            "name": "Example IdP",
            "issuer": "https://idp.example.test",
            "client_id": "client",
            "client_secret": "secret",
            "redirect_uri": "https://app.example.test/callback",
        },
    )
    assert oidc.status_code == 403
    assert "enterprise_identity" in oidc.text


def test_cloud_kms_envelope_roundtrip_uses_random_dek(tmp_path, monkeypatch):
    _use_store(tmp_path, monkeypatch)
    from app.services import secret_crypto

    settings = get_settings()
    monkeypatch.setattr(settings, "secret_kms_provider", "aws_kms")
    monkeypatch.setattr(settings, "aws_kms_key_id", "arn:aws:kms:eu-west-1:123:key/test")
    wrapped_keys: list[bytes] = []

    def wrap(provider: str, dek: bytes, *, aad: str):
        assert provider == "aws_kms"
        assert aad == "workspace-secret"
        wrapped_keys.append(bytes(dek))
        return b"wrapped:" + dek, settings.aws_kms_key_id

    def unwrap(provider: str, wrapped: bytes, *, aad: str, key_ref: str):
        assert provider == "aws_kms"
        assert aad == "workspace-secret"
        assert key_ref == settings.aws_kms_key_id
        assert wrapped.startswith(b"wrapped:")
        return wrapped.split(b":", 1)[1]

    monkeypatch.setattr(secret_crypto, "_cloud_wrap_key", wrap)
    monkeypatch.setattr(secret_crypto, "_cloud_unwrap_key", unwrap)
    encrypted_a = secret_crypto.encrypt_secret("super-secret", aad="workspace-secret")
    encrypted_b = secret_crypto.encrypt_secret("super-secret", aad="workspace-secret")
    assert encrypted_a.startswith("dvkms3:aws_kms:")
    assert encrypted_b != encrypted_a
    assert wrapped_keys[0] != wrapped_keys[1]
    assert secret_crypto.decrypt_secret(encrypted_a, aad="workspace-secret") == "super-secret"
    status = secret_crypto.kms_status()
    assert status["external_kms"] is True
    assert status["production_ready"] is True


def test_observational_causal_ate_recovers_known_effect_and_keeps_guardrail():
    from app.services.causal_inference import estimate_ate

    rng = np.random.default_rng(7)
    n = 1200
    x1 = rng.normal(size=n)
    x2 = rng.normal(size=n)
    logits = 0.8 * x1 - 0.5 * x2
    p = 1 / (1 + np.exp(-logits))
    treatment = rng.binomial(1, p)
    outcome = 3.0 * treatment + 1.4 * x1 - 0.7 * x2 + rng.normal(scale=0.8, size=n)
    df = pd.DataFrame({"treatment": treatment, "outcome": outcome, "x1": x1, "x2": x2})

    result = estimate_ate(
        df,
        treatment="treatment",
        outcome="outcome",
        covariates=["x1", "x2"],
        bootstrap_samples=80,
        random_state=11,
    )
    assert result["method"] == "propensity_score_ipw"
    assert abs(result["effect_estimate"] - 3.0) < 0.35
    assert result["causal_claim_allowed"] is False
    assert "observationnelle" in result["interpretation_guardrail"]
    assert len(result["analysis_sha256"]) == 64


def test_causal_estimator_requires_binary_treatment_and_covariates():
    from app.services.causal_inference import estimate_ate

    df = pd.DataFrame({"t": [0, 1, 2] * 10, "y": range(30), "x": range(30)})
    with pytest.raises(ValueError, match="exactement deux"):
        estimate_ate(df, treatment="t", outcome="y", covariates=["x"])
    df2 = pd.DataFrame({"t": [0, 1] * 10, "y": range(20)})
    with pytest.raises(ValueError, match="covariable"):
        estimate_ate(df2, treatment="t", outcome="y", covariates=[])


def test_proactive_schedule_claim_is_single_claim_and_moves_checkpoint(tmp_path, monkeypatch):
    _use_store(tmp_path, monkeypatch)
    from app.services.metadata_store import execute
    from app.services.proactive_intelligence import save_scan_schedule, claim_due_scan_schedules, get_scan_schedule

    save_scan_schedule(
        "dataset-v278",
        workspace_id="workspace-v278",
        actor_id="user-v278",
        enabled=True,
        interval_minutes=15,
        watch_ids=["watch-1"],
        auto_configure=False,
    )
    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    execute(
        "UPDATE proactive_scan_schedules SET next_run_at=:past WHERE dataset_id=:dataset",
        {"past": past, "dataset": "dataset-v278"},
    )
    first = claim_due_scan_schedules(limit=10)
    second = claim_due_scan_schedules(limit=10)
    assert len(first) == 1
    assert first[0]["watch_ids"] == ["watch-1"]
    assert first[0]["auto_configure"] is False
    assert second == []
    assert get_scan_schedule("dataset-v278")["last_status"] == "claimed"


def test_v278_migration_is_applied(tmp_path, monkeypatch):
    _use_store(tmp_path, monkeypatch)
    from app.services.schema_migrations import migration_status
    from app.services.metadata_store import init_metadata_store

    init_metadata_store()
    status = migration_status()
    assert "2.78.0-001" in status["applied"]
