from pathlib import Path

from app.services.cdc_compliance import (
    get_cdc_report,
    production_acceptance,
)


ROOT = Path(__file__).resolve().parents[2]


def test_cdc_matrix_has_all_75_sections_and_evidence():
    report = get_cdc_report()
    assert report["summary"]["sections"] == 75
    assert report["summary"]["missing"] == 0
    assert report["summary"]["evidence_complete"] is True
    assert report["missing_evidence"] == []
    assert [row["section"] for row in report["requirements"]] == list(range(1, 76))


def test_coverage_is_weighted_and_not_claimed_as_100_percent():
    report = get_cdc_report()
    assert report["summary"]["implemented"] == 52
    assert report["summary"]["partial"] == 23
    assert report["summary"]["weighted_coverage_percent"] == 84.7
    assert report["summary"]["overall_acceptance"] == "conditional"


def test_mvp_gate_uses_the_16_mandatory_items():
    report = get_cdc_report()
    items = report["summary"]["mvp_items"]
    assert len(items) == 16
    assert all(item["pass"] for item in items)
    assert report["summary"]["mvp_acceptance"] == "pass"


def test_p0_gaps_are_explicit_and_actionable():
    report = get_cdc_report()
    p0 = report["priority_gaps"]["P0"]
    sections = {item["section"] for item in p0}
    assert {71, 74}.issubset(sections)
    assert 46 not in sections
    assert all(item["gaps"] for item in p0)


def test_production_acceptance_is_conditional_not_fake_pass():
    result = production_acceptance()
    assert result["acceptance"] == "conditional"
    assert result["coverage_percent"] == 84.7
    assert result["signoff_required"]
    assert any(gate["id"] == "mvp" and gate["status"] == "pass" for gate in result["gates"])
    assert any(gate["id"] == "security" and gate["status"] == "conditional" for gate in result["gates"])


def test_compliance_assets_and_ui_are_present():
    main = (ROOT / "backend/app/main.py").read_text(encoding="utf-8")
    page = (ROOT / "frontend/app/page.tsx").read_text(encoding="utf-8")
    api = (ROOT / "frontend/lib/api.ts").read_text(encoding="utf-8")
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert '/api/v1/system/cdc-compliance' in main
    assert '/api/v1/system/production-acceptance' in main
    assert "ComplianceCenter" in page
    assert "CDC & Acceptance" in page
    assert "getCdcCompliance" in api
    assert "cdc_audit.py --check" in ci


def test_release_packager_excludes_stale_release_manifest():
    release = (ROOT / "scripts/release.py").read_text(encoding="utf-8")
    assert "'RELEASE_MANIFEST.json'" in release
