from __future__ import annotations

import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd
from docx import Document
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.lib import colors

from app.core.config import get_settings
from app.services.analysis_history import get_analysis
from app.services.decision import decision_support
from app.services.profiling import profile_dataframe
from app.services.quality import quality_report
from app.services.storage import get_meta, load_dataframe


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dir() -> Path:
    path = get_settings().data_root / "reports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _slug(value: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip()).strip("-").lower()
    return safe[:80] or "rapport"


def _numeric_summary(df: pd.DataFrame, max_columns: int = 12) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for column in [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])][:max_columns]:
        s = pd.to_numeric(df[column], errors="coerce").dropna()
        if s.empty:
            continue
        rows.append({
            "variable": str(column),
            "n": int(s.size),
            "mean": float(s.mean()),
            "median": float(s.median()),
            "std": float(s.std(ddof=1)) if s.size > 1 else 0.0,
            "min": float(s.min()),
            "max": float(s.max()),
        })
    return rows


def build_report(dataset_id: str, title: str, sections: list[str] | None = None, analysis_session_id: str | None = None) -> dict[str, Any]:
    meta = get_meta(dataset_id)
    df = load_dataframe(dataset_id)
    profile = profile_dataframe(df)
    quality = quality_report(df)
    decision = decision_support(profile, quality)
    allowed = {"overview", "quality", "descriptive", "ai_analysis", "methodology", "provenance"}
    chosen = [s for s in (sections or ["overview", "quality", "descriptive", "ai_analysis", "methodology", "provenance"]) if s in allowed]
    analysis = None
    if analysis_session_id:
        analysis = get_analysis(analysis_session_id)
        if analysis.get("provenance", {}).get("dataset_id") != dataset_id:
            raise ValueError("L'analyse sélectionnée n'appartient pas à ce dataset")

    blocks: list[dict[str, Any]] = []
    if "overview" in chosen:
        blocks.append({"type": "overview", "title": "Vue d'ensemble", "data": {
            "rows": profile.get("rows"), "columns": profile.get("columns_count"), "duplicates": profile.get("duplicates"),
            "memory_bytes": profile.get("memory_bytes"), "quality_score": quality.get("score"),
            "recommended_actions": decision.get("actions", [])[:5],
        }})
    if "quality" in chosen:
        blocks.append({"type": "quality", "title": "Qualité des données", "data": {
            "score": quality.get("score"), "issues_count": quality.get("issues_count"), "issues": quality.get("issues", [])[:25]
        }})
    if "descriptive" in chosen:
        blocks.append({"type": "table", "title": "Statistiques descriptives", "columns": ["variable", "n", "mean", "median", "std", "min", "max"], "rows": _numeric_summary(df)})
    if "ai_analysis" in chosen:
        if analysis:
            blocks.append({"type": "ai_analysis", "title": "Analyse AI Analyst", "data": {
                "session_id": analysis.get("session_id"), "question": analysis.get("question"), "answer": analysis.get("answer"),
                "intent": analysis.get("intent"), "critic": analysis.get("critic"), "findings": analysis.get("findings", []),
                "provenance": analysis.get("provenance", {}),
            }})
        else:
            blocks.append({"type": "note", "title": "Analyse AI Analyst", "text": "Aucune session AI Analyst n'a été sélectionnée pour ce rapport."})
    if "methodology" in chosen:
        blocks.append({"type": "methodology", "title": "Méthodologie", "items": [
            "Les statistiques sont calculées par les moteurs Python/SQL de DataVision, et non générées par un LLM.",
            "Le rapport référence la version exacte du dataset utilisée au moment de sa création.",
            "Les données originales restent immuables; les transformations sont versionnées.",
            "Les résultats doivent être interprétés au regard du contexte métier et des hypothèses méthodologiques.",
        ]})
    if "provenance" in chosen:
        blocks.append({"type": "provenance", "title": "Provenance", "data": {
            "dataset_id": meta["id"], "dataset_name": meta.get("original_name"), "dataset_version": meta.get("version", 1),
            "root_id": meta.get("root_id", meta["id"]), "parent_id": meta.get("parent_id"), "operation": meta.get("operation"),
            "generated_at": _now(), "analysis_session_id": analysis_session_id,
        }})

    report = {
        "id": str(uuid4()), "dataset_id": dataset_id, "title": title.strip() or f"Rapport — {meta.get('original_name', 'Dataset')}",
        "created_at": _now(), "dataset": {"id": meta["id"], "name": meta.get("original_name"), "version": meta.get("version", 1)},
        "sections": chosen, "analysis_session_id": analysis_session_id, "blocks": blocks,
        "reproducibility": {"dataset_version_locked": True, "analysis_session_locked": bool(analysis_session_id)},
    }
    (_dir() / f"{report['id']}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return report


def get_report(report_id: str) -> dict[str, Any]:
    path = _dir() / f"{report_id}.json"
    if not path.exists():
        raise FileNotFoundError(report_id)
    return json.loads(path.read_text(encoding="utf-8"))


def list_reports(dataset_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in _dir().glob("*.json"):
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if report.get("dataset_id") != dataset_id:
            continue
        rows.append({
            "id": report.get("id"), "title": report.get("title"), "created_at": report.get("created_at"),
            "dataset_version": report.get("dataset", {}).get("version"), "sections": report.get("sections", []),
            "analysis_session_id": report.get("analysis_session_id"),
        })
    rows.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return rows


def _fmt(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.4g}"
    if value is None:
        return "—"
    return str(value)


def _markdown(report: dict[str, Any]) -> str:
    out = [f"# {report['title']}", "", f"Dataset : **{report['dataset']['name']}** — version **{report['dataset']['version']}**", f"Généré : {report['created_at']}", ""]
    for block in report.get("blocks", []):
        out.extend([f"## {block.get('title','Section')}", ""])
        kind = block.get("type")
        if kind == "overview":
            data = block["data"]
            out.extend([f"- Lignes : {_fmt(data.get('rows'))}", f"- Variables : {_fmt(data.get('columns'))}", f"- Doublons : {_fmt(data.get('duplicates'))}", f"- Score qualité : {_fmt(data.get('quality_score'))}", ""])
        elif kind == "quality":
            data = block["data"]
            out.append(f"Score qualité : **{_fmt(data.get('score'))}** — {data.get('issues_count',0)} problème(s).\n")
            for issue in data.get("issues", []): out.append(f"- **{issue.get('severity','info')}** — {issue.get('description','')} {issue.get('recommendation','')}")
            out.append("")
        elif kind == "table":
            cols = block.get("columns", [])
            out.append("| " + " | ".join(cols) + " |")
            out.append("| " + " | ".join(["---"] * len(cols)) + " |")
            for row in block.get("rows", []): out.append("| " + " | ".join(_fmt(row.get(c)) for c in cols) + " |")
            out.append("")
        elif kind == "ai_analysis":
            d = block["data"]
            out.extend([f"**Question :** {d.get('question','')}", "", d.get("answer", ""), "", "### Constats"])
            for f in d.get("findings", []): out.append(f"- **{f.get('title','')}** — {f.get('statement','')}")
            out.append("")
        elif kind == "methodology":
            for item in block.get("items", []): out.append(f"- {item}")
            out.append("")
        elif kind == "provenance":
            for k, v in block.get("data", {}).items(): out.append(f"- {k}: `{_fmt(v)}`")
            out.append("")
        else:
            out.extend([block.get("text", ""), ""])
    return "\n".join(out)


def _html(report: dict[str, Any]) -> str:
    md = _markdown(report)
    # A compact deterministic renderer; no external markdown package is required.
    body: list[str] = []
    for line in md.splitlines():
        if line.startswith("# "): body.append(f"<h1>{html.escape(line[2:])}</h1>")
        elif line.startswith("## "): body.append(f"<h2>{html.escape(line[3:])}</h2>")
        elif line.startswith("### "): body.append(f"<h3>{html.escape(line[4:])}</h3>")
        elif line.startswith("- "): body.append(f"<li>{html.escape(line[2:])}</li>")
        elif line.startswith("|"): body.append(f"<pre>{html.escape(line)}</pre>")
        elif line.strip(): body.append(f"<p>{html.escape(line)}</p>")
    return "<!doctype html><html><head><meta charset='utf-8'><title>" + html.escape(report['title']) + "</title><style>body{font-family:Arial,sans-serif;max-width:980px;margin:40px auto;color:#243642;line-height:1.5}h1,h2{color:#2d7692}pre{background:#f5f8fa;padding:6px;margin:0;font-size:12px}li{margin:6px 0}p{white-space:pre-wrap}</style></head><body>" + "".join(body) + "</body></html>"


def _plain_lines(report: dict[str, Any]) -> list[str]:
    return [re.sub(r"[*`#|]", "", line).strip() for line in _markdown(report).splitlines() if line.strip()]


def export_report(report_id: str, fmt: str) -> Path:
    report = get_report(report_id)
    fmt = fmt.lower()
    base = _dir() / f"{_slug(report['title'])}-{report_id[:8]}"
    if fmt in {"md", "markdown"}:
        path = base.with_suffix(".md"); path.write_text(_markdown(report), encoding="utf-8"); return path
    if fmt == "html":
        path = base.with_suffix(".html"); path.write_text(_html(report), encoding="utf-8"); return path
    if fmt == "docx":
        path = base.with_suffix(".docx")
        doc = Document(); doc.add_heading(report["title"], 0); doc.add_paragraph(f"Dataset : {report['dataset']['name']} — version {report['dataset']['version']}")
        for block in report.get("blocks", []):
            doc.add_heading(block.get("title", "Section"), level=1)
            kind = block.get("type")
            if kind == "table":
                cols = block.get("columns", []); rows = block.get("rows", [])
                table = doc.add_table(rows=1, cols=len(cols)); table.style = "Table Grid"
                for i, c in enumerate(cols): table.rows[0].cells[i].text = c
                for row in rows:
                    cells = table.add_row().cells
                    for i, c in enumerate(cols): cells[i].text = _fmt(row.get(c))
            elif kind == "ai_analysis":
                d=block["data"]; doc.add_paragraph(f"Question : {d.get('question','')}"); doc.add_paragraph(d.get("answer", ""))
                for finding in d.get("findings", []): doc.add_paragraph(f"{finding.get('title','')} — {finding.get('statement','')}", style="List Bullet")
            elif kind == "methodology":
                for item in block.get("items", []): doc.add_paragraph(item, style="List Bullet")
            else:
                data = block.get("data")
                if isinstance(data, dict):
                    for k, v in data.items():
                        if not isinstance(v, (dict, list)): doc.add_paragraph(f"{k}: {_fmt(v)}")
                if block.get("text"): doc.add_paragraph(block["text"])
        doc.save(path); return path
    if fmt == "pdf":
        path = base.with_suffix(".pdf")
        styles = getSampleStyleSheet(); story = [Paragraph(html.escape(report["title"]), styles["Title"]), Spacer(1, 12)]
        story.append(Paragraph(html.escape(f"Dataset : {report['dataset']['name']} — version {report['dataset']['version']}"), styles["BodyText"])); story.append(Spacer(1, 12))
        for block in report.get("blocks", []):
            story.append(Paragraph(html.escape(block.get("title", "Section")), styles["Heading2"]))
            if block.get("type") == "table":
                cols=block.get("columns",[]); rows=block.get("rows",[]); table_data=[cols]+[[_fmt(r.get(c)) for c in cols] for r in rows]
                t=Table(table_data, repeatRows=1); t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#dceef4")),("GRID",(0,0),(-1,-1),0.4,colors.grey),("FONTSIZE",(0,0),(-1,-1),7)])); story.extend([t,Spacer(1,10)])
            else:
                text=[]
                if block.get("type") == "ai_analysis":
                    d=block["data"]; text=[f"Question: {d.get('question','')}", d.get("answer","")] + [f"• {f.get('title','')}: {f.get('statement','')}" for f in d.get("findings",[])[:12]]
                elif block.get("type") == "methodology": text=block.get("items",[])
                elif isinstance(block.get("data"),dict): text=[f"{k}: {_fmt(v)}" for k,v in block["data"].items() if not isinstance(v,(dict,list))]
                else: text=[block.get("text","")]
                for line in text: story.append(Paragraph(html.escape(str(line)), styles["BodyText"])); story.append(Spacer(1,4))
        SimpleDocTemplate(str(path), pagesize=A4, rightMargin=36, leftMargin=36, topMargin=40, bottomMargin=40).build(story)
        return path
    raise ValueError("Format d'export non supporté")
