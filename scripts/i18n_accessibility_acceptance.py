#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path


def _catalog_keys(text: str, name: str) -> set[str]:
    match = re.search(rf"const {name}: Record<string,string> = \{{(.*?)\n\}};", text, re.S)
    if not match:
        return set()
    return set(re.findall(r"'([^']+)'\s*:", match.group(1)))


def checks(root: Path) -> list[tuple[str, bool, list[str], list[str]]]:
    page = (root / "frontend/app/page.tsx").read_text(encoding="utf-8")
    css = (root / "frontend/app/globals.css").read_text(encoding="utf-8")
    i18n = (root / "frontend/lib/i18n.ts").read_text(encoding="utf-8")
    prefs = (root / "backend/app/services/user_preferences.py").read_text(encoding="utf-8")
    routes = (root / "backend/app/api/routes/enterprise.py").read_text(encoding="utf-8")
    e2e = root / "frontend/e2e/accessibility.spec.ts"
    test = "backend/tests/test_i18n_accessibility_v274.py"
    doc = "docs/I18N_ACCESSIBILITY_V2740.md"
    fr = _catalog_keys(i18n, "fr")
    parity = bool(fr) and all(_catalog_keys(i18n, loc) == fr for loc in ("en", "es", "ar"))
    return [
        ("four locale catalogs with parity", parity and len(fr) >= 90 and "dir:'rtl'" in i18n, ["frontend/lib/i18n.ts"], [test]),
        ("locale and accessibility preferences persisted", '_ALLOWED_LOCALES = {"fr", "en", "es", "ar"}' in prefs and 'result["high_contrast"]' in prefs and 'result["reduce_motion"]' in prefs and 'pattern="^(fr|en|es|ar)$"' in routes, ["backend/app/services/user_preferences.py", "backend/app/api/routes/enterprise.py"], [test]),
        ("document language and rtl direction are dynamic", "root.lang=locale" in page and "root.dir=localeDirection(locale)" in page, ["frontend/app/page.tsx", "frontend/lib/i18n.ts"], [test]),
        ("localized navigation and display controls", "localizedViewLabel" in page and "localizedAreaLabel" in page and "LOCALES.map" in page, ["frontend/app/page.tsx", "frontend/lib/i18n.ts"], [test]),
        ("keyboard focus and skip navigation", 'className="skip-link" href="#main-content"' in page and "mainContentRef.current?.focus({preventScroll:true})" in page and 'aria-keyshortcuts="Control+K Meta+K"' in page, ["frontend/app/page.tsx", "frontend/app/globals.css"], [test, "frontend/e2e/accessibility.spec.ts"]),
        ("screen reader landmarks and live announcements", 'role="status" aria-live="polite"' in page and 'role="alert"' in page and 'aria-label={tr(\'a11y.primaryNavigation\')}' in page, ["frontend/app/page.tsx"], [test]),
        ("contrast motion and visible focus guardrails", 'html[data-dv-contrast="high"]' in css and 'html[data-dv-motion="reduced"]' in css and ":focus-visible" in css and "prefers-reduced-motion:reduce" in css, ["frontend/app/globals.css"], [test, "frontend/e2e/accessibility.spec.ts"]),
        ("wcag engineering evidence and browser e2e contract", (root / doc).is_file() and e2e.is_file(), [doc], [test, "frontend/e2e/accessibility.spec.ts"]),
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    rows = checks(root)
    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    items = [
        {"id": name.lower().replace(" ", "_"), "ok": ok, "evidence": evidence, "tests": tests}
        for name, ok, evidence, tests in rows
    ]
    payload = {
        "product": "DataVision AI",
        "product_version": version,
        "passed": sum(item["ok"] for item in items),
        "total": len(items),
        "items": items,
        "note": "Internal engineering acceptance baseline; not an external WCAG certification.",
    }
    out = root / "compliance/I18N_ACCESSIBILITY_ACCEPTANCE.json"
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for item in items:
        print(f"{'PASS' if item['ok'] else 'FAIL'} · {item['id']}")
    print(f"I18N_ACCESSIBILITY_ACCEPTANCE {payload['passed']}/{payload['total']}")
    if args.check and payload["passed"] != payload["total"]:
        return 2
    if args.check:
        env = {**os.environ, "PYTHONPATH": str(root / "backend")}
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "backend/tests/test_i18n_accessibility_v274.py"],
            cwd=root,
            env=env,
        )
        return proc.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
