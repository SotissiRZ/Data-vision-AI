from __future__ import annotations

import hashlib
import json
from typing import Any

import pandas as pd

from app.services.preparation import apply_operation
from app.services.quality import quality_report


def _stable_id(payload: dict[str, Any], prefix: str) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(raw).hexdigest()[:14]}"


def _action(
    *,
    issue: dict[str, Any],
    operation: dict[str, Any],
    title: str,
    reason: str,
    risk: str,
    confidence: float,
    review_required: bool,
    default_selected: bool,
) -> dict[str, Any]:
    identity = {
        "issue_code": issue.get("code"),
        "column": issue.get("column"),
        "operation": operation,
    }
    return {
        "id": _stable_id(identity, "qa"),
        "issue_code": issue.get("code"),
        "column": issue.get("column"),
        "title": title,
        "reason": reason,
        "risk": risk,
        "confidence": round(float(confidence), 3),
        "review_required": bool(review_required),
        "default_selected": bool(default_selected),
        "reversible": True,
        "operation": operation,
    }


def build_quality_remediation_plan(
    df: pd.DataFrame,
    *,
    dataset_id: str | None = None,
    version: int | None = None,
) -> dict[str, Any]:
    """Build a deterministic, auditable remediation plan from quality findings.

    The planner never mutates data. It only proposes transformations that already
    exist in DataVision's governed preparation engine. Potentially semantic or
    distribution-altering actions require explicit review and are not selected by
    default.
    """
    quality = quality_report(df)
    actions: list[dict[str, Any]] = []
    seen: set[str] = set()
    rows = max(len(df), 1)

    def add(item: dict[str, Any]) -> None:
        key = json.dumps(item["operation"], sort_keys=True, ensure_ascii=False, default=str)
        if key in seen:
            return
        seen.add(key)
        actions.append(item)

    for issue in quality.get("issues", []):
        code = str(issue.get("code") or "")
        column = str(issue.get("column") or "")

        if code == "duplicates":
            add(_action(
                issue=issue,
                operation={"type": "remove_duplicates", "subset": []},
                title="Dédupliquer les lignes strictement identiques",
                reason="Les doublons stricts peuvent biaiser les agrégations et l'apprentissage. La transformation conserve la première occurrence et crée une nouvelle version.",
                risk="low",
                confidence=0.98,
                review_required=False,
                default_selected=True,
            ))
            continue

        if code == "missing_values" and column in df.columns:
            series = df[column]
            missing = int(series.isna().sum())
            missing_pct = missing / rows
            non_null = series.dropna()

            if non_null.empty:
                add(_action(
                    issue=issue,
                    operation={"type": "drop_columns", "columns": [column]},
                    title=f"Retirer la colonne vide « {column} »",
                    reason="La colonne ne contient aucune valeur exploitable. Sa suppression modifie le schéma et demande donc une validation explicite.",
                    risk="medium",
                    confidence=0.99,
                    review_required=True,
                    default_selected=False,
                ))
                continue

            if pd.api.types.is_numeric_dtype(series):
                strategy = "median"
                rationale = "La médiane limite l'influence des valeurs extrêmes par rapport à la moyenne."
            else:
                strategy = "mode"
                rationale = "Le mode conserve une modalité existante sans inventer une nouvelle catégorie."

            high_missing = missing_pct >= 0.30
            add(_action(
                issue=issue,
                operation={"type": "fill_missing", "column": column, "strategy": strategy},
                title=f"Imputer les valeurs manquantes de « {column} »",
                reason=f"{rationale} Taux de valeurs manquantes : {missing_pct:.1%}.",
                risk="medium" if high_missing else "low",
                confidence=0.72 if high_missing else 0.90,
                review_required=high_missing,
                default_selected=not high_missing,
            ))
            continue

        if code == "constant_column" and column in df.columns:
            add(_action(
                issue=issue,
                operation={"type": "drop_columns", "columns": [column]},
                title=f"Retirer la colonne constante « {column} »",
                reason="Une colonne constante n'apporte aucune variance analytique, mais sa suppression change le schéma et doit rester un choix utilisateur.",
                risk="medium",
                confidence=0.96,
                review_required=True,
                default_selected=False,
            ))
            continue

        if code == "iqr_outliers" and column in df.columns:
            add(_action(
                issue=issue,
                operation={"type": "clip_outliers_iqr", "column": column, "factor": 1.5, "mode": "clip"},
                title=f"Borner les valeurs extrêmes de « {column} »",
                reason="Le clipping IQR conserve toutes les lignes mais modifie la distribution. Une validation métier reste nécessaire avant application.",
                risk="medium",
                confidence=0.70,
                review_required=True,
                default_selected=False,
            ))

    plan_seed = {
        "dataset_id": dataset_id,
        "version": version,
        "quality": {"score": quality.get("score"), "issues_count": quality.get("issues_count")},
        "actions": [{"id": a["id"], "operation": a["operation"]} for a in actions],
    }
    plan_id = _stable_id(plan_seed, "quality_plan")
    default_ids = [a["id"] for a in actions if a["default_selected"]]
    return {
        "plan_id": plan_id,
        "dataset_id": dataset_id,
        "dataset_version": version,
        "quality": quality,
        "actions": actions,
        "action_count": len(actions),
        "default_action_ids": default_ids,
        "review_required_count": sum(1 for a in actions if a["review_required"]),
        "principles": [
            "Aucune correction n'est appliquée sans action explicite de l'utilisateur.",
            "Chaque application crée une nouvelle version immuable du dataset.",
            "Les corrections qui modifient le schéma ou la distribution exigent une revue explicite.",
        ],
    }


def preview_quality_remediation(
    df: pd.DataFrame,
    *,
    plan: dict[str, Any],
    action_ids: list[str] | None = None,
) -> dict[str, Any]:
    selected_ids = list(plan.get("default_action_ids", [])) if action_ids is None else list(dict.fromkeys(action_ids))
    actions_by_id = {str(a["id"]): a for a in plan.get("actions", [])}
    unknown = [action_id for action_id in selected_ids if action_id not in actions_by_id]
    if unknown:
        raise ValueError(f"Actions de remédiation inconnues: {', '.join(unknown)}")

    before = quality_report(df)
    work = df.copy(deep=True)
    applied: list[dict[str, Any]] = []
    for action_id in selected_ids:
        action = actions_by_id[action_id]
        work, audit = apply_operation(work, dict(action["operation"]))
        applied.append({
            "action_id": action_id,
            "title": action["title"],
            "risk": action["risk"],
            "review_required": action["review_required"],
            "operation": audit,
        })

    after = quality_report(work)
    return {
        "plan_id": plan.get("plan_id"),
        "selected_action_ids": selected_ids,
        "selected_count": len(selected_ids),
        "before": {
            "score": before["score"],
            "issues_count": before["issues_count"],
            "rows": int(len(df)),
            "columns": int(len(df.columns)),
        },
        "after": {
            "score": after["score"],
            "issues_count": after["issues_count"],
            "rows": int(len(work)),
            "columns": int(len(work.columns)),
        },
        "delta": {
            "score": int(after["score"]) - int(before["score"]),
            "issues": int(after["issues_count"]) - int(before["issues_count"]),
            "rows": int(len(work)) - int(len(df)),
            "columns": int(len(work.columns)) - int(len(df.columns)),
        },
        "applied": applied,
    }


def apply_quality_remediation(
    df: pd.DataFrame,
    *,
    plan: dict[str, Any],
    action_ids: list[str],
    expected_plan_id: str | None = None,
) -> tuple[pd.DataFrame, dict[str, Any], dict[str, Any]]:
    if expected_plan_id and expected_plan_id != plan.get("plan_id"):
        raise ValueError("Le plan de remédiation a changé. Rechargez le diagnostic avant application.")
    if not action_ids:
        raise ValueError("Sélectionnez au moins une action de remédiation.")

    preview = preview_quality_remediation(df, plan=plan, action_ids=action_ids)
    work = df.copy(deep=True)
    steps: list[dict[str, Any]] = []
    by_id = {str(a["id"]): a for a in plan.get("actions", [])}
    for action_id in preview["selected_action_ids"]:
        action = by_id[action_id]
        work, audit = apply_operation(work, dict(action["operation"]))
        steps.append({
            "action_id": action_id,
            "issue_code": action.get("issue_code"),
            "column": action.get("column"),
            "risk": action.get("risk"),
            "review_required": action.get("review_required"),
            "operation": audit,
        })

    audit_operation = {
        "type": "quality_remediation",
        "label": f"Remédiation qualité guidée ({len(steps)} action(s))",
        "params": {
            "plan_id": plan.get("plan_id"),
            "action_ids": preview["selected_action_ids"],
            "before_score": preview["before"]["score"],
            "after_score": preview["after"]["score"],
            "before_issues": preview["before"]["issues_count"],
            "after_issues": preview["after"]["issues_count"],
            "steps": steps,
        },
    }
    return work, audit_operation, preview
