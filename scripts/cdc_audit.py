#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "compliance" / "CDC_COVERAGE_MATRIX.json"
WEIGHTS = {"implemented": 1.0, "partial": 0.5, "missing": 0.0}


def load():
    return json.loads(MATRIX.read_text(encoding="utf-8"))


def build_report(payload):
    rows = payload["requirements"]
    weighted = sum(WEIGHTS.get(row["status"], 0) for row in rows)
    counts = {key: sum(r["status"] == key for r in rows) for key in WEIGHTS}
    missing = []
    for row in rows:
        for evidence in (row.get("evidence") or []) + (row.get("tests") or []):
            if not (ROOT / evidence).exists():
                missing.append((row["section"], evidence))
    return rows, counts, round(weighted / len(rows) * 100, 1), missing


def markdown(payload, rows, counts, score, missing):
    lines = [
        "# Matrice de couverture CDC — DataVision AI",
        "",
        f"- CDC: {payload['cdc_version']}",
        f"- Produit: {payload['product_version']}",
        f"- Couverture pondérée: **{score}%**",
        f"- Implémenté: **{counts['implemented']}** / Partiel: **{counts['partial']}** / Manquant: **{counts['missing']}**",
        f"- Preuves absentes: **{len(missing)}**",
        "",
        "> Méthode: implemented=1, partial=0.5, missing=0. Le score mesure la couverture du CDC, pas une certification externe.",
        "",
        "| § | Exigence | Statut | Priorité | Gap principal |",
        "|---:|---|---|---|---|",
    ]
    for row in rows:
        gap = " ".join(row.get("gaps") or []) or "—"
        lines.append(
            f"| {row['section']} | {row['title']} | {row['status']} | {row['priority']} | {gap.replace('|','/')} |"
        )
    lines += ["", "## Gaps prioritaires", ""]
    for priority in ("P0", "P1", "P2"):
        lines.append(f"### {priority}")
        found = False
        for row in rows:
            if row["priority"] == priority and row["status"] != "implemented":
                found = True
                gap = " ".join(row.get("gaps") or []) or "Couverture partielle."
                lines.append(f"- **§{row['section']} {row['title']}** — {gap}")
        if not found:
            lines.append("- Aucun gap.")
        lines.append("")
    lines += ["## Preuves manquantes", ""]
    if missing:
        lines += [f"- §{section}: `{path}`" for section, path in missing]
    else:
        lines.append("- Aucune preuve référencée manquante.")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    payload = load()
    rows, counts, score, missing = build_report(payload)
    if args.write:
        out = ROOT / "docs" / "CDC_COVERAGE_MATRIX.md"
        out.write_text(markdown(payload, rows, counts, score, missing), encoding="utf-8")
        summary = {
            "coverage_percent": score,
            "counts": counts,
            "missing_evidence": [{"section": s, "path": p} for s, p in missing],
        }
        (ROOT / "compliance" / "CDC_COVERAGE_SUMMARY.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    print(json.dumps({"coverage_percent": score, "counts": counts, "missing_evidence": len(missing)}, ensure_ascii=False))
    if args.check and missing:
        return 2
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
