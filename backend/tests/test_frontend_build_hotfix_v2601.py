from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_governance_role_matrix_is_null_safe() -> None:
    page = (ROOT / "frontend/app/page.tsx").read_text(encoding="utf-8")
    assert "controlPlane.dataset.role_matrix.map" not in page
    assert "(controlPlane?.dataset?.role_matrix??[]).map" in page


def test_typescript_incremental_is_explicit() -> None:
    tsconfig = json.loads((ROOT / "frontend/tsconfig.json").read_text(encoding="utf-8"))
    assert tsconfig["compilerOptions"]["incremental"] is True


def test_flex_alignment_uses_widely_supported_values() -> None:
    for rel in (
        "frontend/app/globals.css",
        "frontend/components/ModelRegistryView.module.css",
    ):
        css = (ROOT / rel).read_text(encoding="utf-8")
        assert "align-items:start" not in css
        assert "align-items:end" not in css
        assert "align-self:start" not in css
        assert "align-self:end" not in css
