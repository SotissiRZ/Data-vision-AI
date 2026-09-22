from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[2]


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_production_acceptance_harness_exists():
    gate = text("scripts/production_acceptance.py")
    assert "test:e2e:production" in gate
    assert "load_smoke.py" in gate
    assert "production_signoff.py" in gate
    assert "helm lint" in gate


def test_signoff_requires_authoritative_evidence():
    signoff = text("scripts/production_signoff.py")
    assert 'REQUIRED_KINDS = ("ci", "compose", "helm", "e2e", "load", "security", "uat")' in signoff
    assert "--require-all" in signoff
    assert "datavision-production-evidence-v1" in signoff


def test_load_smoke_has_explicit_thresholds():
    smoke = text("scripts/load_smoke.py")
    assert "--max-p95-ms" in smoke
    assert "--max-error-rate" in smoke
    assert "throughput_rps" in smoke


def test_playwright_has_production_suite():
    package = json.loads(text("frontend/package.json"))
    assert "test:e2e:production" in package["scripts"]
    spec = text("frontend/e2e/production.spec.ts")
    assert "@production" in spec
    assert "Agrandir la fenêtre" in spec


def test_windows_runner_executes_real_build_and_e2e():
    runner = text("production-acceptance-windows.ps1")
    assert "docker compose up -d --build" in runner
    assert "npm run typecheck" in runner
    assert "npm run build" in runner
    assert "npm run test:e2e:production" in runner


def test_ci_contains_production_acceptance_steps():
    ci = text(".github/workflows/ci.yml")
    assert "helm lint" in ci
    assert "test:e2e:production" in ci
    assert "production-load.json" in ci
    assert "production_acceptance.py" in ci
