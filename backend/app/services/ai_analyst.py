from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4

import numpy as np
import pandas as pd

from app.services.advanced_analysis import anova_analysis, clustering_analysis, regression_analysis
from app.services.anomaly_detection import detect_anomalies
from app.services.decision import decision_support
from app.services.forecasting import forecast_series
from app.services.modeling import automl_train
from app.services.profiling import profile_dataframe
from app.services.quality import quality_report
from app.services.root_cause import root_cause_analysis
from app.services.statistics_engine import correlation_analysis
from app.services.semantic_nlq import plan_semantic_question, execute_semantic_question


@dataclass
class AnalystContext:
    dataset: dict[str, Any]
    question: str
    target: str | None = None
    date_column: str | None = None
    variables: list[str] | None = None
    group: str | None = None
    horizon: int = 12
    mode: str = "auto"
    semantic_model: dict[str, Any] | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm(text: str) -> str:
    text = text.lower()
    replacements = {"é": "e", "è": "e", "ê": "e", "à": "a", "â": "a", "ù": "u", "û": "u", "ô": "o", "î": "i", "ï": "i", "ç": "c"}
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    return text


def _numeric_columns(df: pd.DataFrame) -> list[str]:
    return [str(c) for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]


def _categorical_columns(df: pd.DataFrame) -> list[str]:
    cols: list[str] = []
    for c in df.columns:
        if pd.api.types.is_numeric_dtype(df[c]):
            continue
        unique = df[c].nunique(dropna=True)
        if 2 <= unique <= 40:
            cols.append(str(c))
    return cols


def _date_columns(df: pd.DataFrame) -> list[str]:
    result: list[str] = []
    for c in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[c]):
            result.append(str(c))
            continue
        name = _norm(str(c))
        if any(token in name for token in ("date", "time", "jour", "mois", "annee", "timestamp")):
            parsed = pd.to_datetime(df[c], errors="coerce")
            if parsed.notna().mean() >= 0.7:
                result.append(str(c))
    return result


def _mentioned_columns(question: str, df: pd.DataFrame) -> list[str]:
    q = _norm(question)
    found: list[tuple[int, str]] = []
    for c in df.columns:
        cname = str(c)
        candidates = {_norm(cname), _norm(cname.replace("_", " ")), _norm(cname.replace("-", " "))}
        positions = [q.find(x) for x in candidates if x and q.find(x) >= 0]
        if positions:
            found.append((min(positions), cname))
    found.sort(key=lambda x: x[0])
    return [c for _, c in found]




def _semantic_matches(question: str, semantic: dict[str, Any] | None, df: pd.DataFrame) -> list[str]:
    if not semantic:
        return []
    q = _norm(question)
    found: list[tuple[int, str]] = []
    def add_terms(column: str, terms: list[str]):
        if column not in df.columns:
            return
        positions=[]
        for term in terms:
            t=_norm(str(term).strip())
            if not t:
                continue
            pos=q.find(t)
            if pos >= 0:
                positions.append(pos)
        if positions:
            found.append((min(positions), column))
    for m in semantic.get("metrics", []):
        add_terms(str(m.get("column") or ""), [m.get("id", ""), m.get("name", ""), m.get("label", ""), *(m.get("synonyms") or [])])
    for d in semantic.get("dimensions", []):
        add_terms(str(d.get("column") or ""), [d.get("column", ""), d.get("label", ""), *(d.get("synonyms") or [])])
    found.sort(key=lambda x: x[0])
    out=[]
    for _, col in found:
        if col not in out:
            out.append(col)
    return out


def _resolved_columns(question: str, df: pd.DataFrame, semantic: dict[str, Any] | None = None) -> list[str]:
    out=[]
    for col in [*_semantic_matches(question, semantic, df), *_mentioned_columns(question, df)]:
        if col not in out:
            out.append(col)
    return out

def _looks_identifier(series: pd.Series, name: str) -> bool:
    n = max(int(series.notna().sum()), 1)
    ratio = float(series.nunique(dropna=True)) / n
    lname = _norm(name)
    return ratio > 0.95 and any(token in lname for token in ("id", "ident", "uuid", "code", "numero", "number"))


def _select_target(df: pd.DataFrame, ctx: AnalystContext, *, numeric_required: bool = False) -> str | None:
    if ctx.target and ctx.target in df.columns:
        if not numeric_required or pd.api.types.is_numeric_dtype(df[ctx.target]):
            return ctx.target
    mentioned = _resolved_columns(ctx.question, df, ctx.semantic_model)
    for c in mentioned:
        if not numeric_required or pd.api.types.is_numeric_dtype(df[c]):
            return c
    candidates = _numeric_columns(df) if numeric_required else [str(c) for c in df.columns]
    for c in reversed(candidates):
        if not _looks_identifier(df[c], c):
            return c
    return candidates[-1] if candidates else None


def _select_group(df: pd.DataFrame, ctx: AnalystContext, exclude: set[str] | None = None) -> str | None:
    exclude = exclude or set()
    if ctx.group and ctx.group in df.columns and ctx.group not in exclude:
        return ctx.group
    mentioned = _resolved_columns(ctx.question, df, ctx.semantic_model)
    cats = set(_categorical_columns(df))
    for c in mentioned:
        if c in cats and c not in exclude:
            return c
    for c in _categorical_columns(df):
        if c not in exclude:
            return c
    return None


def _select_date(df: pd.DataFrame, ctx: AnalystContext) -> str | None:
    if ctx.date_column and ctx.date_column in df.columns:
        return ctx.date_column
    mentioned = set(_resolved_columns(ctx.question, df, ctx.semantic_model))
    dates = _date_columns(df)
    for c in dates:
        if c in mentioned:
            return c
    return dates[0] if dates else None


def _requested_k(question: str) -> int:
    q = _norm(question)
    patterns = [r"(?:k\s*=\s*|en\s+)(\d+)\s*(?:clusters?|groupes?)", r"(\d+)\s*(?:clusters?|groupes?)"]
    for pattern in patterns:
        m = re.search(pattern, q)
        if m:
            return max(2, min(10, int(m.group(1))))
    return 3


def detect_intent(question: str) -> str:
    q = _norm(question)

    if (
        "root cause" in q
        or "cause racine" in q
        or "analyse des causes" in q
        or "analyse les causes" in q
        or re.search(
            r"\bpourquoi\b.*\b(?:baiss|augment|chang|vari)",
            q,
        )
        or re.search(
            r"\b(?:explique|expliquer)\b.*\b(?:baisse|hausse|variation|chute)",
            q,
        )
    ):
        return "root_cause"

    intents: list[tuple[str, tuple[str, ...]]] = [
        ("forecast", ("prevision", "prevoir", "forecast", "projection", "prochain mois", "next month", "future")),
        ("automl", ("automl", "modele predictif", "predire", "prediction", "classifier", "classification", "machine learning", "meilleur modele")),
        ("clustering", ("cluster", "segmentation", "segmenter", "regrouper", "k-means", "kmeans")),
        ("anomaly", ("anomal", "aberrant", "outlier", "atypique", "isolation forest")),
        ("anova", ("anova", "compare les groupes", "comparer les groupes", "difference entre les groupes", "moyennes entre")),
        ("root_cause", ("root cause", "cause racine", "analyse des causes", "explique la baisse", "explique la hausse", "pourquoi a baisse", "pourquoi a augmente", "quels facteurs expliquent la variation")),
        ("regression", ("regression", "facteurs associes", "facteurs qui expliquent", "influence de", "relation avec")),
        ("correlation", ("correlation", "correle", "association entre", "relations entre les variables")),
        ("quality", ("qualite", "nettoyage", "manquante", "doublon", "problemes de donnees", "data quality")),
        ("decision", ("decision", "recommandation", "que dois-je faire", "priorite", "action a prendre")),
        ("overview", ("resume", "resumer", "analyse ce dataset", "analyse les donnees", "overview", "profil", "explore", "exploration")),
    ]
    for intent, keywords in intents:
        if any(k in q for k in keywords):
            return intent
    return "overview"


def tool_registry() -> list[dict[str, Any]]:
    return [
        {"name": "profile", "status": "implemented", "purpose": "Profilage déterministe du dataset"},
        {"name": "quality", "status": "implemented", "purpose": "Contrôles de qualité et sévérité"},
        {"name": "correlations", "status": "implemented", "purpose": "Corrélations Pearson/Spearman avec p-values"},
        {"name": "regression", "status": "implemented", "purpose": "Régression linéaire et diagnostics"},
        {"name": "anova", "status": "implemented", "purpose": "ANOVA et comparaisons de groupes"},
        {"name": "clustering", "status": "implemented", "purpose": "K-means avec silhouette"},
        {"name": "automl", "status": "implemented", "purpose": "Benchmark de modèles avec validation train/validation/test"},
        {"name": "forecast", "status": "implemented", "purpose": "Forecasting chronologique avec benchmark"},
        {"name": "anomalies", "status": "implemented", "purpose": "IQR, z-score robuste et Isolation Forest"},
        {"name": "root_cause", "status": "implemented", "purpose": "Décomposition descriptive des écarts et changements de distribution"},
        {"name": "decision_support", "status": "implemented", "purpose": "Priorisation d'actions basée sur les résultats calculés"},
        {"name": "semantic_query", "status": "implemented", "purpose": "Requête métier multi-table via la couche sémantique gouvernée"},
    ]


def _compact(value: Any, *, max_items: int = 12) -> Any:
    if isinstance(value, dict):
        return {str(k): _compact(v, max_items=max_items) for k, v in list(value.items())[:max_items]}
    if isinstance(value, list):
        items = [_compact(v, max_items=max_items) for v in value[:max_items]]
        if len(value) > max_items:
            items.append({"truncated": len(value) - max_items})
        return items
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if not np.isfinite(value) else float(value)
    return value


def _finding(level: str, title: str, statement: str, tool: str, evidence: dict[str, Any]) -> dict[str, Any]:
    return {"level": level, "title": title, "statement": statement, "evidence": {"tool": tool, **evidence}}


def _overview_findings(profile: dict[str, Any], quality: dict[str, Any]) -> list[dict[str, Any]]:
    out = [
        _finding("info", "Dimensions du dataset", f"Le dataset contient {profile['rows']} lignes et {profile['columns_count']} variables.", "profile", {"rows": profile["rows"], "columns": profile["columns_count"]}),
        _finding("info", "Qualité globale", f"Le score de qualité est de {quality['score']}/100 avec {quality['issues_count']} problème(s) détecté(s).", "quality", {"score": quality["score"], "issues_count": quality["issues_count"]}),
    ]
    missing = sorted(profile["columns"], key=lambda c: c.get("missing_pct", 0), reverse=True)
    if missing and missing[0].get("missing_pct", 0) > 0:
        c = missing[0]
        out.append(_finding("warning", "Valeurs manquantes", f"{c['name']} est la variable la plus touchée avec {c['missing_pct']:.2f}% de valeurs manquantes.", "profile", {"column": c["name"], "missing_pct": c["missing_pct"]}))
    if profile.get("duplicates", 0):
        out.append(_finding("warning", "Doublons", f"{profile['duplicates']} ligne(s) dupliquée(s) ont été détectées.", "profile", {"duplicates": profile["duplicates"]}))
    return out


def _correlation_findings(result: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for pair in result.get("pairs", [])[:5]:
        coef = pair.get("coefficient")
        if coef is None:
            continue
        strength = abs(float(coef))
        if strength < 0.3:
            continue
        level = "high" if strength >= 0.7 else "info"
        direction = "positive" if coef >= 0 else "négative"
        findings.append(_finding(level, f"Corrélation {direction}", f"{pair['x']} et {pair['y']} présentent une corrélation {direction} de {coef:.3f}.", "correlations", {"x": pair["x"], "y": pair["y"], "coefficient": coef, "p_value": pair.get("p_value")}))
    if not findings:
        findings.append(_finding("info", "Corrélations", "Aucune corrélation linéaire forte n'a été détectée parmi les variables analysées.", "correlations", {"threshold": 0.3}))
    return findings


def _critic(executions: list[dict[str, Any]], findings: list[dict[str, Any]]) -> dict[str, Any]:
    failed = [x for x in executions if x.get("status") != "ok"]
    evidence_missing = [f["title"] for f in findings if not f.get("evidence", {}).get("tool")]
    checks = [
        {"check": "tool_execution", "passed": not failed, "detail": "Tous les outils planifiés ont été exécutés." if not failed else f"{len(failed)} outil(s) ont échoué."},
        {"check": "numeric_provenance", "passed": not evidence_missing, "detail": "Chaque constat numérique est relié à un moteur exécuté." if not evidence_missing else "Certains constats n'ont pas de provenance."},
        {"check": "llm_as_calculator", "passed": True, "detail": "Aucun nombre n'est calculé par un LLM; les calculs proviennent des moteurs Python/statistiques/ML."},
    ]
    return {"status": "passed" if all(c["passed"] for c in checks) else "warning", "checks": checks, "failed_tools": failed}


def analyze_dataset(df: pd.DataFrame, ctx: AnalystContext) -> dict[str, Any]:
    if df.empty:
        raise ValueError("Le dataset est vide")
    question = ctx.question.strip()
    if not question:
        raise ValueError("La question analytique ne peut pas être vide")

    intent = detect_intent(question)
    semantic_plan = None
    if ctx.semantic_model and ctx.dataset.get("id"):
        try:
            semantic_plan = plan_semantic_question(str(ctx.dataset.get("id")), df, question, 200, ctx.semantic_model)
        except Exception:
            semantic_plan = None
    # A pure business-metric question should use the semantic layer before generic profiling tools.
    # Explicit statistical/ML/forecast intents keep priority so "prévoir le CA" still means forecast.
    if semantic_plan and intent == "overview":
        intent = "semantic_query"
    profile = profile_dataframe(df)
    quality = quality_report(df)
    findings: list[dict[str, Any]] = []
    executions: list[dict[str, Any]] = []
    artifacts: dict[str, Any] = {}
    plan: list[dict[str, Any]] = []
    semantic_matches = _semantic_matches(question, ctx.semantic_model, df)
    if ctx.semantic_model:
        artifacts["semantic_context"] = {
            "status": ctx.semantic_model.get("status"),
            "version": ctx.semantic_model.get("version"),
            "matched_columns": semantic_matches,
            "certified_metrics": [m.get("id") for m in ctx.semantic_model.get("metrics", []) if m.get("certified")],
            "resolved_plan": semantic_plan,
        }

    def execute(step: str, tool: str, fn: Callable[[], Any]) -> Any:
        plan.append({"step": len(plan) + 1, "action": step, "tool": tool})
        started = time.perf_counter()
        try:
            raw = fn()
            executions.append({"tool": tool, "status": "ok", "duration_ms": round((time.perf_counter() - started) * 1000, 2)})
            artifacts[tool] = _compact(raw)
            return raw
        except Exception as exc:
            executions.append({"tool": tool, "status": "failed", "duration_ms": round((time.perf_counter() - started) * 1000, 2), "error": str(exc)})
            artifacts[tool] = {"error": str(exc)}
            return None

    # Always ground the analysis in dataset structure and quality.
    execute("Inspecter la structure et les types", "profile", lambda: profile)
    execute("Contrôler la qualité avant interprétation", "quality", lambda: quality)
    findings.extend(_overview_findings(profile, quality))

    if intent == "semantic_query":
        semantic = execute(
            "Interroger le modèle sémantique gouverné",
            "semantic_query",
            lambda: execute_semantic_question(str(ctx.dataset.get("id")), df, question, 200, ctx.semantic_model),
        )
        if semantic:
            plan_sem, qsem = semantic["plan"], semantic["query"]
            metric_label = plan_sem.get("metric_label") or plan_sem.get("metric_id")
            dims = plan_sem.get("dimensions") or []
            if dims and qsem.get("result"):
                top = qsem["result"][0]
                dim_label = " / ".join(str(top.get(d)) for d in dims if d in top)
                findings.append(_finding(
                    "high" if plan_sem.get("metric_certified") else "info",
                    "Métrique métier",
                    f"{metric_label} = {qsem.get('value')!s}. Premier segment: {dim_label} → {top.get('value')!s}.",
                    "semantic_query",
                    {"metric_id": plan_sem.get("metric_id"), "dimensions": dims, "value": qsem.get("value"), "first_segment": top, "semantic_model_version": qsem.get("semantic_model_version")},
                ))
            else:
                findings.append(_finding(
                    "high" if plan_sem.get("metric_certified") else "info",
                    "Métrique métier",
                    f"{metric_label} = {qsem.get('value')!s}.",
                    "semantic_query",
                    {"metric_id": plan_sem.get("metric_id"), "value": qsem.get("value"), "semantic_model_version": qsem.get("semantic_model_version")},
                ))

    elif intent in {"overview", "correlation"}:
        variables = [c for c in (ctx.variables or _resolved_columns(question, df, ctx.semantic_model)) if c in df.columns and pd.api.types.is_numeric_dtype(df[c])]
        if len(variables) < 2:
            variables = _numeric_columns(df)[:8]
        if len(variables) >= 2:
            corr = execute("Quantifier les relations entre variables numériques", "correlations", lambda: correlation_analysis(df, variables, "pearson"))
            if corr:
                findings.extend(_correlation_findings(corr))
        if intent == "overview" and _numeric_columns(df):
            anomaly_cols = _numeric_columns(df)[:6]
            anomalies = execute("Rechercher des observations atypiques", "anomalies", lambda: detect_anomalies(df, anomaly_cols, "auto", 0.05, 3.5))
            if anomalies:
                rate = float(anomalies["anomaly_rate_pct"])
                findings.append(_finding("warning" if rate >= 5 else "info", "Observations atypiques", f"Le moteur {anomalies['method']} signale {anomalies['anomalies_count']} anomalie(s), soit {rate:.2f}% des lignes.", "anomalies", {"count": anomalies["anomalies_count"], "rate_pct": rate, "method": anomalies["method"]}))

    elif intent == "quality":
        for issue in quality.get("issues", [])[:8]:
            findings.append(_finding(issue.get("severity", "info"), "Problème de qualité", issue.get("description", "Problème détecté"), "quality", {"code": issue.get("code"), "column": issue.get("column"), "recommendation": issue.get("recommendation")}))

    elif intent == "decision":
        decision = execute("Prioriser les actions à partir des contrôles calculés", "decision_support", lambda: decision_support(profile, quality))
        if decision:
            for action in decision.get("actions", []):
                findings.append(_finding(action.get("priority", "info"), "Action recommandée", action.get("action", ""), "decision_support", {"evidence": action.get("evidence"), "automatic_decision": False}))

    elif intent == "anomaly":
        variables = [c for c in (ctx.variables or _resolved_columns(question, df, ctx.semantic_model)) if c in df.columns and pd.api.types.is_numeric_dtype(df[c])]
        if not variables:
            variables = _numeric_columns(df)[:8]
        anomalies = execute("Détecter les anomalies sur les variables numériques sélectionnées", "anomalies", lambda: detect_anomalies(df, variables, "auto", 0.05, 3.5)) if variables else None
        if anomalies:
            rate = float(anomalies["anomaly_rate_pct"])
            findings.append(_finding("warning" if rate else "info", "Anomalies détectées", f"{anomalies['anomalies_count']} observation(s) sont signalées par {anomalies['method']} ({rate:.2f}%).", "anomalies", {"count": anomalies["anomalies_count"], "rate_pct": rate, "method": anomalies["method"], "columns": anomalies["columns"]}))

    elif intent == "forecast":
        date_col = _select_date(df, ctx)
        target = _select_target(df, ctx, numeric_required=True)
        if not date_col or not target or date_col == target:
            raise ValueError("Le forecasting nécessite une colonne de date identifiable et une cible numérique. Précisez-les dans la demande ou les paramètres.")
        forecast = execute(f"Prévoir {target} à partir de {date_col}", "forecast", lambda: forecast_series(df, date_col, target, ctx.horizon, "auto", "auto"))
        if forecast:
            first = forecast["forecast"][0]
            last = forecast["forecast"][-1]
            findings.append(_finding("info", "Prévision", f"La méthode retenue est {forecast['method']}. La prévision passe de {first['prediction']:.3f} à {last['prediction']:.3f} sur {forecast['horizon']} période(s).", "forecast", {"method": forecast["method"], "horizon": forecast["horizon"], "first_prediction": first["prediction"], "last_prediction": last["prediction"]}))

    elif intent == "root_cause":
        target = _select_target(df, ctx, numeric_required=True)
        if not target:
            raise ValueError(
                "La Root Cause Analysis nécessite une cible numérique identifiable."
            )

        mentioned = _resolved_columns(
            question,
            df,
            ctx.semantic_model,
        )
        date_columns = _date_columns(df)
        categorical = _categorical_columns(df)

        comparison = None
        for column in mentioned:
            if column != target and (
                column in date_columns
                or column in categorical
            ):
                comparison = column
                break
        if comparison is None:
            comparison = (
                date_columns[0]
                if date_columns
                else _select_group(df, ctx, {target})
            )
        if not comparison:
            raise ValueError(
                "Précisez une dimension de comparaison (date, période ou groupe)."
            )

        dimensions = [
            column
            for column in categorical
            if column not in {target, comparison}
        ][:8]

        root = execute(
            f"Décomposer la variation de {target} selon {comparison}",
            "root_cause",
            lambda: root_cause_analysis(
                df,
                target=target,
                comparison_column=comparison,
                metric="mean",
                dimensions=dimensions,
                time_grain="auto",
                min_segment_size=3,
                top_n=8,
            ),
        )
        if root:
            delta_pct = root.get("delta_pct")
            delta_text = (
                f"{float(delta_pct):+.1f}%"
                if delta_pct is not None
                else f"{float(root['delta']):+.3f}"
            )
            findings.append(
                _finding(
                    "high",
                    "Variation observée",
                    (
                        f"{target} passe de "
                        f"{root['baseline']['metric']:.3f} à "
                        f"{root['current']['metric']:.3f} "
                        f"({delta_text})."
                    ),
                    "root_cause",
                    {
                        "target": target,
                        "comparison_column": comparison,
                        "baseline": root["baseline"],
                        "current": root["current"],
                        "delta": root["delta"],
                        "delta_pct": root.get("delta_pct"),
                    },
                )
            )

            decompositions = root.get(
                "dimension_decompositions",
                [],
            )
            if decompositions:
                strongest = decompositions[0]
                top_segments = strongest.get(
                    "top_segments",
                    [],
                )
                if top_segments:
                    top = top_segments[0]
                    findings.append(
                        _finding(
                            "high",
                            "Segment prioritaire à examiner",
                            (
                                f"{strongest['dimension']} = "
                                f"{top['segment']} représente une des "
                                f"plus fortes contributions descriptives "
                                f"à l'écart ({top['contribution']:+.3f})."
                            ),
                            "root_cause",
                            {
                                "dimension": strongest["dimension"],
                                "segment": top["segment"],
                                "contribution": top["contribution"],
                                "mix_effect": top.get("mix_effect"),
                                "rate_effect": top.get("rate_effect"),
                            },
                        )
                    )

            shifts = root.get("feature_shifts", [])
            if shifts:
                shift = shifts[0]
                findings.append(
                    _finding(
                        "info",
                        "Changement de distribution",
                        (
                            f"{shift['feature']} présente le changement "
                            f"de distribution le plus marqué "
                            f"(score={shift['score']:.3f})."
                        ),
                        "root_cause",
                        {
                            "feature": shift["feature"],
                            "type": shift["type"],
                            "score": shift["score"],
                        },
                    )
                )

    elif intent == "regression":
        target = _select_target(df, ctx, numeric_required=True)
        if not target:
            raise ValueError("Aucune variable numérique n'est disponible comme variable dépendante")
        mentioned = [c for c in _resolved_columns(question, df, ctx.semantic_model) if c != target]
        independents = [c for c in (ctx.variables or mentioned) if c in df.columns and c != target]
        if not independents:
            independents = [str(c) for c in df.columns if str(c) != target and not _looks_identifier(df[c], str(c))][:8]
        result = execute(f"Estimer les facteurs associés à {target}", "regression", lambda: regression_analysis(df, target, independents))
        if result:
            findings.append(_finding("info", "Pouvoir explicatif", f"La régression explique {100 * float(result['r_squared']):.1f}% de la variance de {target} (R²={float(result['r_squared']):.3f}).", "regression", {"target": target, "r_squared": result["r_squared"], "adj_r_squared": result["adj_r_squared"], "n": result["n"]}))
            significant = [c for c in result.get("coefficients", []) if c.get("term") != "const" and c.get("p_value") is not None and c["p_value"] < 0.05]
            for coef in sorted(significant, key=lambda x: x["p_value"])[:5]:
                findings.append(_finding("high", "Facteur statistiquement associé", f"{coef['term']} est associé à {target} (β={coef['estimate']:.3f}, p={coef['p_value']:.4g}).", "regression", {"term": coef["term"], "estimate": coef["estimate"], "p_value": coef["p_value"]}))

    elif intent == "anova":
        response = _select_target(df, ctx, numeric_required=True)
        factor = _select_group(df, ctx, {response} if response else set())
        if not response or not factor:
            raise ValueError("L'ANOVA nécessite une variable réponse numérique et un facteur catégoriel. Précisez-les dans la demande.")
        result = execute(f"Comparer {response} selon {factor}", "anova", lambda: anova_analysis(df, response, factor, None))
        if result:
            row = result["anova_table"][0]
            findings.append(_finding("high" if row.get("p_value") is not None and row["p_value"] < 0.05 else "info", "Comparaison des groupes", f"ANOVA {response} ~ {factor}: F={row.get('f'):.3f}, p={row.get('p_value'):.4g}.", "anova", {"response": response, "factor": factor, "f": row.get("f"), "p_value": row.get("p_value")}))

    elif intent == "clustering":
        variables = [c for c in (ctx.variables or _resolved_columns(question, df, ctx.semantic_model)) if c in df.columns and pd.api.types.is_numeric_dtype(df[c])]
        if len(variables) < 2:
            variables = [c for c in _numeric_columns(df) if not _looks_identifier(df[c], c)][:6]
        if len(variables) < 2:
            raise ValueError("Le clustering nécessite au moins deux variables numériques")
        k = _requested_k(question)
        result = execute(f"Segmenter les observations en {k} clusters", "clustering", lambda: clustering_analysis(df, variables, k))
        if result:
            findings.append(_finding("info", "Segmentation", f"K-means a construit {k} groupes avec un silhouette score de {float(result['silhouette_score']):.3f}.", "clustering", {"k": k, "silhouette_score": result["silhouette_score"], "variables": variables}))

    elif intent == "automl":
        target = _select_target(df, ctx, numeric_required=False)
        if not target:
            raise ValueError("Précisez la variable cible à prédire")
        automl = execute(f"Comparer plusieurs modèles pour prédire {target}", "automl", lambda: automl_train(df, target=target, task="auto", primary_metric="auto", cv_folds=5, tune=ctx.mode == "deep", max_candidates=5 if ctx.mode == "deep" else 3, dataset_context=ctx.dataset))
        if automl:
            metric_name = automl.get("primary_metric") or "métrique principale"
            metric_value = automl.get("metrics", {}).get(metric_name)
            findings.append(_finding("info", "Modèle prédictif retenu", f"Le benchmark a retenu {automl.get('algorithm', 'un modèle')} pour {target}.", "automl", {"target": target, "algorithm": automl.get("algorithm"), "primary_metric": metric_name, "primary_metric_value": metric_value, "test_metrics": automl.get("metrics"), "model_id": automl.get("model_id")}))

    # Add decision support at the end of analytical runs so the response can end with actionable, non-automatic next steps.
    if intent not in {"decision", "quality"}:
        decision = execute("Formuler les prochaines actions sans décision automatique", "decision_support", lambda: decision_support(profile, quality))
        if decision:
            artifacts["decision_support"] = _compact(decision)

    critic = _critic(executions, findings)
    successful_tools = [x["tool"] for x in executions if x.get("status") == "ok"]
    answer_parts = [f["statement"] for f in findings[:6]]
    answer = " ".join(answer_parts) if answer_parts else "L'analyse s'est exécutée, mais aucun constat synthétique n'a été produit."
    if critic["status"] != "passed":
        answer += " Certains outils n'ont pas pu être exécutés; consultez le contrôle Critic."

    return {
        "session_id": str(uuid4()),
        "question": question,
        "intent": intent,
        "mode": ctx.mode,
        "answer": answer,
        "plan": plan,
        "executions": executions,
        "findings": findings,
        "artifacts": artifacts,
        "critic": critic,
        "provenance": {
            "dataset_id": ctx.dataset.get("id"),
            "dataset_name": ctx.dataset.get("name"),
            "dataset_version": ctx.dataset.get("version", 1),
            "executed_at": _now(),
            "tools_executed": successful_tools,
            "calculation_policy": "deterministic_tools_only",
            "llm_used_for_numeric_calculation": False,
            "semantic_grounding": bool(ctx.semantic_model),
            "semantic_model_version": (ctx.semantic_model or {}).get("version"),
            "semantic_matches": semantic_matches,
        },
    }
