#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def check(root: Path) -> list[tuple[str, bool]]:
    anthropic = (root / "backend/app/assistant/providers/anthropic.py").read_text(encoding="utf-8")
    gemini = (root / "backend/app/assistant/providers/gemini.py").read_text(encoding="utf-8")
    settings = (root / "backend/app/assistant/ai_settings.py").read_text(encoding="utf-8")
    gateway_cfg = (root / "backend/app/assistant/model_gateway_config.py").read_text(encoding="utf-8")
    gateway = (root / "backend/app/assistant/model_gateway.py").read_text(encoding="utf-8")
    client = (root / "frontend/lib/assistant/settings-client.ts").read_text(encoding="utf-8")
    center = (root / "frontend/components/assistant/AIProviderControlCenter.tsx").read_text(encoding="utf-8")
    env = (root / ".env.example").read_text(encoding="utf-8")
    tests = root / "backend/tests/assistant/test_model_gateway_v273.py"
    return [
        ("native anthropic messages adapter", "class AnthropicProvider" in anthropic and "/v1/messages" in anthropic),
        ("native gemini generateContent adapter", "class GeminiProvider" in gemini and ":generateContent" in gemini),
        ("native structured output contracts", "output_config" in anthropic and "responseJsonSchema" in gemini),
        ("provider profiles support four families", '"anthropic", "gemini"' in settings and "AnthropicProvider" in settings and "GeminiProvider" in settings),
        ("privacy routing remains authoritative", "allow_external_ai" in gateway and 'privacy_mode == "local_only"' in gateway),
        ("secret vault and env credentials remain governed", "resolve_secret" in settings and "api_key_env" in settings),
        ("frontend and env configuration expose native providers", 'value="anthropic"' in center and 'value="gemini"' in center and '"anthropic"' in client and "DATAVISION_ANTHROPIC_MODEL" in env and "DATAVISION_GEMINI_MODEL" in env and "anthropic-native" in gateway_cfg and "gemini-native" in gateway_cfg),
        ("integration tests present", tests.is_file()),
    ]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    rows = check(root)
    checks = [{"id": name.lower().replace(" ", "_"), "ok": ok} for name, ok in rows]
    passed = sum(ok for _, ok in rows)
    payload = {
        "product_version": (root / "VERSION").read_text(encoding="utf-8").strip(),
        "passed": passed,
        "total": len(rows),
        "checks": checks,
    }
    (root / "compliance/MODEL_GATEWAY_ACCEPTANCE.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    for name, ok in rows:
        print(f"{'PASS' if ok else 'FAIL'} · {name}")
    print(f"MODEL_GATEWAY_ACCEPTANCE {passed}/{len(rows)}")
    if args.check and passed != len(rows):
        return 2
    if args.check:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "backend/tests/assistant/test_model_gateway_v273.py"],
            cwd=root,
            env={**os.environ, "PYTHONPATH": str(root / "backend")},
        )
        return proc.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
