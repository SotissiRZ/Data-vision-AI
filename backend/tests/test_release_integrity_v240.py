from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[2]
VERIFY = ROOT / "scripts" / "verify_release.py"
BASELINE = ROOT / "scripts" / "production_baseline.py"


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def make_archive(tmp_path: Path, *, extra: bool = False, tamper: bool = False) -> Path:
    root = "datavision-ai-v2.40.0-complet"
    payload = b"2.40.0\n"
    manifest = {
        "format": "reproducible-source-archive-v1",
        "product": "DataVision AI",
        "version": "2.40.0",
        "files": [
            {
                "path": "VERSION",
                "sha256": hashlib.sha256(payload).hexdigest(),
                "size": len(payload),
            }
        ],
    }
    archive = tmp_path / f"{root}.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr(f"{root}/VERSION", b"tampered\n" if tamper else payload)
        if extra:
            zf.writestr(f"{root}/EXTRA.txt", b"not declared")
        zf.writestr(
            f"{root}/RELEASE_MANIFEST.json",
            json.dumps(manifest, sort_keys=True).encode(),
        )
    return archive


def test_current_source_tree_passes_production_baseline():
    module = load(BASELINE, "production_baseline_v240")
    assert module.check(ROOT) == []


def test_release_verifier_accepts_valid_manifest(tmp_path):
    module = load(VERIFY, "verify_release_v240_ok")
    result = module.verify_archive(make_archive(tmp_path))
    assert result["version"] == "2.40.0"
    assert result["files"] == 1


def test_release_verifier_rejects_tampered_file(tmp_path):
    module = load(VERIFY, "verify_release_v240_tamper")
    with pytest.raises(ValueError, match="invalide"):
        module.verify_archive(make_archive(tmp_path, tamper=True))


def test_release_verifier_rejects_unlisted_file(tmp_path):
    module = load(VERIFY, "verify_release_v240_extra")
    with pytest.raises(ValueError, match="non déclaré"):
        module.verify_archive(make_archive(tmp_path, extra=True))


def test_release_packager_runs_embedded_verification():
    text = (ROOT / "scripts/release.py").read_text(encoding="utf-8")
    assert "from verify_release import verify_archive" in text
    assert "verify_archive(archive" in text


def test_ci_and_preflight_validate_production_baseline():
    preflight = (ROOT / "preflight-windows.ps1").read_text(encoding="utf-8")
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    release = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    assert "production_baseline.py --check" in preflight
    assert "production_baseline.py --root .. --check" in ci
    assert "production_baseline.py --check" in release
