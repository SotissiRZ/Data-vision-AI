from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAGE = (ROOT / "frontend" / "app" / "page.tsx").read_text(encoding="utf-8")


def test_trust_center_uses_versions_array_from_api_envelope():
    assert "Array.isArray(versionPayload?.versions)?versionPayload.versions" in PAGE
    assert "(result.versions??[]).slice()" not in PAGE
    assert "lineageVersions.slice().sort" in PAGE


def test_trust_center_guards_array_contracts():
    assert "const trustChecks:AnyObj[]=Array.isArray(trust?.checks)?trust.checks:[];" in PAGE
    assert "const trustWarnings:string[]=Array.isArray(trust?.warnings)" in PAGE
    assert "trustChecks.map((c:AnyObj)" in PAGE
    assert "trustWarnings.map((w:string" in PAGE


def test_trust_center_policy_is_null_safe():
    assert "const trustPolicy=trust?.policy??{};" in PAGE
    assert "trustPolicy.raw_data_to_external_llm" in PAGE
