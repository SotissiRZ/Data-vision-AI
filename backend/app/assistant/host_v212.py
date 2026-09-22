from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from app.core.config import get_settings
from app.services.advanced_analysis import regression_analysis
from app.services.auth_service import has_permission
from app.services.modeling import get_model_card, train_model
from app.services.automl_engine import run_automl_experiment, run_automl_benchmark
from app.services.model_registry import (
    LOCAL_ACTOR, LOCAL_WORKSPACE, check_retraining, get_registry_entry,
    monitor_model, transition_model,
)
from app.services.feature_store import list_feature_sets, materialize_feature_set
from app.services.model_serving import (
    batch_score_dataset,
    list_deployments,
    rollback_deployment,
    score_deployment,
)
from app.services.notebook_service import run_cell as run_notebook_cell
from app.services.preparation import apply_operation, combine_dataframes
from app.services.profiling import profile_dataframe
from app.services.insight_engine import generate_insights
from app.services.forecasting import forecast_series
from app.services.anomaly_detection import detect_anomalies
from app.services.report_builder import build_report, export_report
from app.services.root_cause import root_cause_analysis
from app.services.decision_lab import optimize_scenarios
from app.services.responsible_ai import fairness_report, model_risk_assessment, responsible_ai_gate
from app.services.connector_service import (
    discover_connector,
    list_connectors,
    list_sources,
    test_connector,
)
from app.services.statistics_engine import statistical_test, test_advisor
from app.services.storage import (
    get_meta,
    load_dataframe,
    save_dataframe_version,
)
from app.services.tenant_access import current_access_context
from app.services.visualization import build_visualization, recommend_visualizations
from app.services.xai import model_diagnostics, partial_dependence, shap_explanation, generate_counterfactuals, xai_audit

from .models import AssistantContext
from .tools import AssistantToolRegistry, ToolSpec


_PERMISSION_MAP = {
    "dataset:read": "dataset:read",
    "dataset:transform": "dataset:write",
    "visualization:create": "analysis:run",
    "analysis:create": "analysis:run",
    "analysis:read": "analysis:run",
    "model:create": "model:run",
    "model:read": "model:run",
    "model:publish": "publish:write",
    "report:create": "publish:write",
    "dataset:export": "publish:write",
    "file:read": "dataset:read",
    "action:execute": "actions:trigger",
    "connectors:read": "connectors:read",
    "connectors:manage": "connectors:manage",
    "plugin:execute": "plugins:execute",
}


class V212HostAuthorization:
    """Bridge assistant tool permissions to DataVision v2.12 RBAC."""

    def is_allowed(
        self,
        *,
        tool: ToolSpec,
        context: AssistantContext,
    ) -> tuple[bool, str]:
        access = current_access_context()

        # Local DataVision mode: no Entreprise workspace selected.
        if context.workspaceId is None:
            return True, "mode local DataVision"

        if access is None:
            return False, "workspace Entreprise fourni sans contexte d'authentification"

        if str(access.workspace_id) != str(context.workspaceId):
            return False, "workspace du contexte assistant différent du workspace authentifié"

        for requested in tool.required_permissions:
            actual = _PERMISSION_MAP.get(requested)
            if actual is None:
                return False, f"permission assistant non mappée : {requested}"
            if not has_permission(access.user_id, access.workspace_id, actual):
                return False, f"permission requise : {actual}"

        return True, "RBAC DataVision v2.12 autorisé"


def _dataset_id(context: AssistantContext) -> str:
    if not context.activeDatasetId:
        raise ValueError("Aucun dataset actif.")
    return context.activeDatasetId


def _load(context: AssistantContext) -> tuple[str, pd.DataFrame]:
    dataset_id = _dataset_id(context)
    return dataset_id, load_dataframe(dataset_id)


def _jsonable_records(df: pd.DataFrame, limit: int = 25) -> list[dict[str, Any]]:
    frame = df.head(limit).copy()
    frame = frame.where(pd.notna(frame), None)
    return json.loads(frame.to_json(orient="records", date_format="iso"))


class V212DataBridge:
    def profile_dataset(
        self,
        *,
        context: AssistantContext,
        include_distributions: bool = True,
        sample_rows: int = 5000,
        **_: Any,
    ) -> dict[str, Any]:
        dataset_id, df = _load(context)
        work = df.head(sample_rows) if len(df) > sample_rows else df
        result = profile_dataframe(work)
        result["dataset_id"] = dataset_id
        result["sampled"] = len(work) != len(df)
        result["total_rows"] = int(len(df))
        return result

    def inspect_missing_values(
        self,
        *,
        context: AssistantContext,
        columns: list[str] | None = None,
        include_patterns: bool = True,
        **_: Any,
    ) -> dict[str, Any]:
        dataset_id, df = _load(context)
        selected = columns or [str(c) for c in df.columns]
        unknown = [c for c in selected if c not in df.columns]
        if unknown:
            raise ValueError(f"Colonnes inconnues : {', '.join(unknown)}")
        rows = max(len(df), 1)
        details = []
        for col in selected:
            missing = int(df[col].isna().sum())
            details.append(
                {
                    "column": col,
                    "missing": missing,
                    "missing_pct": round(missing / rows * 100.0, 4),
                    "dtype": str(df[col].dtype),
                }
            )
        return {
            "dataset_id": dataset_id,
            "rows": int(len(df)),
            "columns": details,
            "include_patterns": bool(include_patterns),
        }

    def apply_reversible_transform(
        self,
        *,
        context: AssistantContext,
        operation: str,
        parameters: dict[str, Any],
        create_new_version: bool = True,
        **_: Any,
    ) -> dict[str, Any]:
        if not create_new_version:
            raise ValueError("DataVision exige une nouvelle version pour les transformations agentiques.")
        dataset_id, df = _load(context)
        mapping = {
            "filter": "filter_rows",
            "rename": "rename_column",
            "cast": "cast_type",
            "impute": "fill_missing",
            "drop_duplicates": "remove_duplicates",
            "normalize": "normalize_minmax",
            "standardize": "standardize",
            "encode": "one_hot_encode",
            "outlier_treatment": "clip_outliers_iqr",
            "feature_engineering": "add_calculated_column",
        }
        host_type = mapping.get(operation)
        if not host_type:
            raise ValueError(f"Transformation non mappée : {operation}")
        host_op = {"type": host_type, **parameters}
        transformed, audit_op = apply_operation(df, host_op)
        meta = save_dataframe_version(dataset_id, transformed, audit_op)
        return {
            "status": "ok",
            "dataset_id": meta["id"],
            "parent_dataset_id": dataset_id,
            "version": meta.get("version"),
            "operation": audit_op,
            "rollback_token": dataset_id,
            "rows": int(len(transformed)),
            "columns": int(len(transformed.columns)),
        }

    def merge_datasets(
        self,
        *,
        context: AssistantContext,
        right_dataset_id: str,
        how: str,
        left_on: list[str],
        right_on: list[str],
        suffixes: tuple[str, str] = ("_x", "_y"),
        **_: Any,
    ) -> dict[str, Any]:
        left_id, left = _load(context)
        right = load_dataframe(right_dataset_id)
        merged, audit_op = combine_dataframes(
            left,
            right,
            {
                "type": "merge",
                "how": how,
                "left_on": left_on,
                "right_on": right_on,
            },
        )
        audit_op["params"]["requested_suffixes"] = list(suffixes)
        meta = save_dataframe_version(left_id, merged, audit_op)
        return {
            "status": "ok",
            "dataset_id": meta["id"],
            "parent_dataset_id": left_id,
            "right_dataset_id": right_dataset_id,
            "version": meta.get("version"),
            "rollback_token": left_id,
            "rows": int(len(merged)),
            "columns": int(len(merged.columns)),
        }

    def delete_column(
        self,
        *,
        context: AssistantContext,
        columns: list[str],
        create_new_version: bool = True,
        **_: Any,
    ) -> dict[str, Any]:
        if not create_new_version:
            raise ValueError("La suppression doit créer une nouvelle version.")
        dataset_id, df = _load(context)
        transformed, audit_op = apply_operation(
            df,
            {"type": "drop_columns", "columns": columns},
        )
        meta = save_dataframe_version(dataset_id, transformed, audit_op)
        return {
            "status": "ok",
            "dataset_id": meta["id"],
            "parent_dataset_id": dataset_id,
            "version": meta.get("version"),
            "removed_columns": columns,
            "rollback_token": dataset_id,
        }


class V212VisualizationBridge:
    def create_visualization(
        self,
        *,
        context: AssistantContext,
        chart_type: str,
        x: str | None = None,
        y: str | None = None,
        color: str | None = None,
        size: str | None = None,
        facet: str | None = None,
        aggregation: str | None = None,
        title: str | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        dataset_id, df = _load(context)
        type_map = {
            "boxplot": "box",
            "correlation_matrix": "heatmap",
            "time_series": "line",
        }
        host_type = type_map.get(chart_type, chart_type)
        result = build_visualization(
            df,
            chart_type=host_type,
            x=x,
            y=y,
            color=color,
            size=size,
            facet=facet,
            aggregation=aggregation or "none",
        )
        result["dataset_id"] = dataset_id
        if title:
            result["title"] = title
        if size:
            result["requested_size"] = size
        if facet:
            result["requested_facet"] = facet
        return result

    def diagnose_visualization(
        self,
        *,
        context: AssistantContext,
        **_: Any,
    ) -> dict[str, Any]:
        dataset_id, df = _load(context)
        selected: list[str] = []
        if context.selectedEntity and context.selectedEntity.type in {"column", "variable"}:
            if context.selectedEntity.id:
                selected.append(context.selectedEntity.id)
        return {
            "dataset_id": dataset_id,
            "recommendations": recommend_visualizations(df, selected),
            "selected_columns": selected,
        }


class V212AnalysisBridge:
    def diagnose_analysis_failure(
        self,
        *,
        context: AssistantContext,
        **_: Any,
    ) -> dict[str, Any]:
        failures = [
            {
                "type": event.type,
                "severity": event.severity,
                "payload": event.payload,
                "timestamp": event.timestamp.isoformat(),
            }
            for event in context.recentEvents
            if event.severity in {"warning", "critical"} or event.type.endswith(".failed")
        ]
        return {"recent_failures": failures[-10:], "count": len(failures)}

    def forecast_dataset(
        self,
        *,
        context: AssistantContext,
        date_column: str,
        target: str,
        horizon: int = 12,
        frequency: str = "auto",
        method: str = "auto",
        backtest_windows: int = 3,
        interval_level: float = 0.95,
        missing_strategy: str = "none",
        selection_metric: str = "rmse",
        **_: Any,
    ) -> dict[str, Any]:
        _, df = _load(context)
        return forecast_series(
            df, date_column, target, horizon, frequency, method, backtest_windows, interval_level,
            missing_strategy, selection_metric,
        )

    def detect_dataset_anomalies(
        self,
        *,
        context: AssistantContext,
        columns: list[str] | None = None,
        method: str = "auto",
        contamination: float = 0.05,
        threshold: float = 3.5,
        **_: Any,
    ) -> dict[str, Any]:
        _, df = _load(context)
        return detect_anomalies(df, columns or [], method, contamination, threshold)

    def generate_dataset_insights(
        self,
        *,
        context: AssistantContext,
        max_insights: int = 12,
        persist: bool = False,
        **_: Any,
    ) -> dict[str, Any]:
        dataset_id, df = _load(context)
        return generate_insights(
            dataset_id,
            df,
            max_insights=max(1, min(int(max_insights), 40)),
            persist=bool(persist),
        )

    def run_statistical_test(
        self,
        *,
        context: AssistantContext,
        test: str,
        outcome: str | None = None,
        group: str | None = None,
        variables: list[str] | None = None,
        alpha: float = 0.05,
        alternative: str = "two-sided",
        **_: Any,
    ) -> dict[str, Any]:
        _, df = _load(context)
        variables = variables or []
        mapping = {
            "t_test": "student_t",
            "welch": "welch_t",
            "mann_whitney": "mann_whitney",
            "wilcoxon": "wilcoxon",
            "chi_square": "chi_square",
            "fisher": "fisher",
            "anova": "anova_oneway",
            "kruskal_wallis": "kruskal_wallis",
            "pearson": "pearson",
            "spearman": "spearman",
        }
        if test in {"normality", "homoscedasticity"}:
            if outcome and group:
                advisor = test_advisor(df, value=outcome, group=group)
            elif len(variables) >= 2:
                advisor = test_advisor(df, x=variables[0], y=variables[1])
            else:
                raise ValueError("Normalité/homoscédasticité nécessite outcome+group ou deux variables.")
            diagnostics = advisor.get("diagnostics", {})
            key = "normality" if test == "normality" else "levene"
            return {
                "test": test,
                "diagnostics": diagnostics.get(key, diagnostics),
                "advisor": advisor,
                "alpha": alpha,
            }

        host_test = mapping.get(test)
        if not host_test:
            raise ValueError(f"Test non supporté : {test}")

        if host_test in {"pearson", "spearman", "chi_square", "fisher", "wilcoxon"}:
            if len(variables) < 2:
                raise ValueError("Deux variables sont requises.")
            return statistical_test(
                df,
                host_test,
                x=variables[0],
                y=variables[1],
                paired=(host_test == "wilcoxon"),
            )

        return statistical_test(
            df,
            host_test,
            value=outcome,
            group=group,
        )

    def run_regression(
        self,
        *,
        context: AssistantContext,
        kind: str,
        target: str,
        features: list[str],
        regularization: str = "none",
        **_: Any,
    ) -> dict[str, Any]:
        dataset_id, df = _load(context)
        if kind in {"linear", "multiple_linear"}:
            result = regression_analysis(df, target, features)
            result["dataset_id"] = dataset_id
            return result

        if kind == "logistic":
            trained = train_model(
                df,
                target=target,
                task="classification",
                algorithm="logistic_regression",
                dataset_context={"id": dataset_id, "version": get_meta(dataset_id).get("version")},
            )
            return {
                "model_id": trained.model_id,
                "task": trained.task,
                "algorithm": trained.algorithm,
                "metrics": trained.metrics,
                "validation_metrics": trained.validation_metrics,
                "model_card": trained.model_card,
            }

        if kind == "regularized":
            if regularization not in {"l2", "none"}:
                raise ValueError("v2.12 implémente Ridge (L2) mais pas encore L1/ElasticNet.")
            trained = train_model(
                df,
                target=target,
                task="regression",
                algorithm="ridge" if regularization == "l2" else "linear_regression",
                dataset_context={"id": dataset_id, "version": get_meta(dataset_id).get("version")},
            )
            return {
                "model_id": trained.model_id,
                "task": trained.task,
                "algorithm": trained.algorithm,
                "metrics": trained.metrics,
                "validation_metrics": trained.validation_metrics,
                "model_card": trained.model_card,
            }

        raise ValueError(f"Régression non supportée : {kind}")


    def run_root_cause_analysis(
        self,
        *,
        context: AssistantContext,
        target: str,
        comparison_column: str,
        baseline_value: Any | None = None,
        current_value: Any | None = None,
        metric: str = "mean",
        dimensions: list[str] | None = None,
        time_grain: str = "auto",
        min_segment_size: int = 5,
        top_n: int = 8,
        **_: Any,
    ) -> dict[str, Any]:
        dataset_id, df = _load(context)
        result = root_cause_analysis(
            df,
            target=target,
            comparison_column=comparison_column,
            baseline_value=baseline_value,
            current_value=current_value,
            metric=metric,
            dimensions=dimensions,
            time_grain=time_grain,
            min_segment_size=min_segment_size,
            top_n=top_n,
        )
        meta = get_meta(dataset_id)
        result["provenance"] = {
            "dataset_id": dataset_id,
            "dataset_version": meta.get("version"),
            "root_id": meta.get("root_id") or meta.get("id"),
            "calculation_engine": "deterministic_root_cause",
        }
        return result


class V212MLBridge:
    def inspect_data_leakage(
        self,
        *,
        context: AssistantContext,
        target: str | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        dataset_id, df = _load(context)
        if target is None:
            target = context.uiState.get("target") if context.uiState else None
        if not target:
            return {
                "dataset_id": dataset_id,
                "status": "needs_target",
                "message": "Sélectionnez une cible pour exécuter les garde-fous de leakage.",
            }
        if target not in df.columns:
            raise ValueError(f"Cible inconnue : {target}")

        suspicious = []
        target_values = df[target]
        for col in df.columns:
            if col == target:
                continue
            if df[col].equals(target_values):
                suspicious.append(
                    {"column": str(col), "reason": "copie exacte de la cible", "severity": "critical"}
                )
            elif str(col).lower() in {
                f"{str(target).lower()}_label",
                f"{str(target).lower()}_target",
                f"target_{str(target).lower()}",
            }:
                suspicious.append(
                    {"column": str(col), "reason": "nom de variable fortement suspect", "severity": "warning"}
                )
        return {
            "dataset_id": dataset_id,
            "target": target,
            "signals": suspicious,
            "status": "warning" if suspicious else "ok",
            "note": "Contrôle déterministe de pré-entraînement; les garde-fous du moteur ML s'exécutent aussi pendant l'entraînement.",
        }


    def benchmark_models(
        self,
        *,
        context: AssistantContext,
        target: str,
        task: str = "auto",
        primary_metric: str = "auto",
        cv_folds: int = 5,
        max_candidates: int = 10,
        **_: Any,
    ) -> dict[str, Any]:
        _dataset_id_value, df = _load(context)
        return run_automl_benchmark(
            df, target=target, task=task, primary_metric=primary_metric,
            cv_folds=cv_folds, max_candidates=max_candidates,
        )

    def run_automl(
        self,
        *,
        context: AssistantContext,
        task: str,
        target: str | None = None,
        features: list[str] | None = None,
        metric: str | None = None,
        validation: str = "cross_validation",
        time_column: str | None = None,
        max_models: int = 8,
        explain: bool = True,
        **_: Any,
    ) -> dict[str, Any]:
        dataset_id, df = _load(context)
        if task not in {"classification", "regression", "clustering"}:
            raise ValueError("AutoML v2.51 couvre classification, régression et clustering avec ML Safety. Le forecasting conserve son moteur dédié.")
        if task != "clustering" and not target:
            raise ValueError("Cible requise pour une tâche supervisée.")
        result = run_automl_experiment(
            df, target=target, task=task, features=features,
            primary_metric=metric or "auto",
            cv_folds=5 if validation == "cross_validation" else 2,
            tune=True, max_candidates=max_models,
            dataset_context={"id": dataset_id, "version": get_meta(dataset_id).get("version")},
            split_strategy="temporal" if validation == "time_split" else ("random" if validation == "holdout" else "auto"),
            time_column=time_column,
        )
        result["requested_explain"] = explain
        result["rollback_token"] = result.get("model_id")
        return result


    def optimize_decision_scenarios(
        self,
        *,
        context: AssistantContext,
        base_row: dict[str, Any],
        controls: dict[str, dict[str, Any]],
        objective: str = "maximize",
        target_value: float | None = None,
        desired_class: Any | None = None,
        max_candidates: int = 2000,
        max_results: int = 10,
        **_: Any,
    ) -> dict[str, Any]:
        model_id = context.activeModelId
        if not model_id:
            raise ValueError("Aucun modèle actif.")
        return optimize_scenarios(
            model_id,
            base_row,
            controls,
            objective=objective,
            target_value=target_value,
            desired_class=desired_class,
            max_candidates=max_candidates,
            max_results=max_results,
        )


    def evaluate_model_fairness(
        self,
        *,
        context: AssistantContext,
        protected_columns: list[str],
        positive_label: Any | None = None,
        mode: str = "both",
        min_group_size: int = 20,
        **_: Any,
    ) -> dict[str, Any]:
        model_id = context.activeModelId
        if not model_id:
            raise ValueError("Aucun modèle actif.")
        card = get_model_card(model_id)
        dataset_id = card.get("dataset", {}).get("id") or context.activeDatasetId
        if not dataset_id:
            raise ValueError("Dataset de référence introuvable.")
        return fairness_report(
            model_id, load_dataframe(dataset_id),
            protected_columns=protected_columns, positive_label=positive_label,
            mode=mode, min_group_size=min_group_size,
        )

    def assess_model_risk(
        self,
        *,
        context: AssistantContext,
        protected_columns: list[str] | None = None,
        positive_label: Any | None = None,
        mode: str = "both",
        min_group_size: int = 20,
        **_: Any,
    ) -> dict[str, Any]:
        model_id = context.activeModelId
        if not model_id:
            raise ValueError("Aucun modèle actif.")
        fairness = None
        if protected_columns:
            card = get_model_card(model_id)
            dataset_id = card.get("dataset", {}).get("id") or context.activeDatasetId
            if not dataset_id:
                raise ValueError("Dataset de référence introuvable.")
            fairness = fairness_report(
                model_id, load_dataframe(dataset_id),
                protected_columns=protected_columns, positive_label=positive_label,
                mode=mode, min_group_size=min_group_size,
            )
        return model_risk_assessment(model_id, fairness=fairness)

    def responsible_ai_publication_gate(
        self,
        *,
        context: AssistantContext,
        protected_columns: list[str],
        positive_label: Any | None = None,
        mode: str = "both",
        min_group_size: int = 20,
        policy: dict[str, Any] | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        model_id = context.activeModelId
        if not model_id:
            raise ValueError("Aucun modèle actif.")
        card = get_model_card(model_id)
        dataset_id = card.get("dataset", {}).get("id") or context.activeDatasetId
        if not dataset_id:
            raise ValueError("Dataset de référence introuvable.")
        return responsible_ai_gate(
            model_id, load_dataframe(dataset_id),
            protected_columns=protected_columns, positive_label=positive_label,
            mode=mode, min_group_size=min_group_size, policy=policy,
        )

    def explain_model(
        self,
        *,
        context: AssistantContext,
        method: str,
        row_id: str | int | None = None,
        feature: str | None = None,
        features: list[str] | None = None,
        row: dict[str, Any] | None = None,
        desired_class: Any | None = None,
        desired_value: float | None = None,
        direction: str | None = None,
        immutable_features: list[str] | None = None,
        actionable_features: list[str] | None = None,
        feature_constraints: dict[str, dict[str, Any]] | None = None,
        include_shap: bool = False,
        **_: Any,
    ) -> dict[str, Any]:
        model_id = context.activeModelId
        if not model_id:
            raise ValueError("Aucun modèle actif.")
        card = get_model_card(model_id)

        if method in {
            "feature_importance",
            "permutation_importance",
        }:
            return {
                "model_id": model_id,
                "method": method,
                "feature_importance": card.get(
                    "feature_importance",
                    [],
                ),
                "model_card": card,
            }

        dataset_id = (
            context.activeDatasetId
            or card.get("dataset", {}).get("id")
        )

        if method == "xai_audit":
            if not dataset_id:
                raise ValueError("Dataset de référence requis pour l'audit XAI.")
            return xai_audit(
                model_id,
                load_dataframe(dataset_id),
                row=row,
                pdp_features=list(features or ([feature] if feature else [])),
                include_shap=include_shap,
                persist=True,
            )

        if method in {
            "confusion_matrix",
            "calibration",
            "diagnostics",
        }:
            if not dataset_id:
                raise ValueError(
                    "Dataset de référence requis pour les diagnostics."
                )
            diagnostics = model_diagnostics(
                model_id,
                load_dataframe(dataset_id),
            )
            if method == "diagnostics":
                return diagnostics
            return {
                "model_id": model_id,
                "method": method,
                "result": diagnostics.get(method),
                "diagnostics": diagnostics,
            }

        if method in {"shap", "shap_global", "shap_local"}:
            if not dataset_id:
                raise ValueError(
                    "Dataset de référence requis pour SHAP."
                )
            return shap_explanation(
                model_id,
                load_dataframe(dataset_id),
                row=row if method != "shap_global" else None,
                max_rows=50,
            )

        if method == "partial_dependence":
            if not dataset_id:
                raise ValueError(
                    "Dataset de référence requis pour PDP."
                )
            selected = list(features or [])
            if feature and feature not in selected:
                selected.append(feature)
            if not selected:
                raise ValueError(
                    "Au moins une variable est requise pour PDP."
                )
            return partial_dependence(
                model_id,
                load_dataframe(dataset_id),
                selected,
                grid_points=20,
            )

        if method in {"counterfactual", "counterfactuals"}:
            if not dataset_id:
                raise ValueError(
                    "Dataset de référence requis pour les contre-factuels."
                )
            if row is None:
                raise ValueError(
                    "Une observation de référence est requise."
                )
            return generate_counterfactuals(
                model_id,
                load_dataframe(dataset_id),
                row,
                desired_class=desired_class,
                desired_value=desired_value,
                direction=direction,
                max_changes=2,
                max_results=5,
                immutable_features=immutable_features,
                actionable_features=actionable_features,
                feature_constraints=feature_constraints,
            )

        raise ValueError(
            f"Méthode XAI non supportée : {method}"
        )

class V212ConnectorBridge:
    @staticmethod
    def _workspace(context: AssistantContext) -> str:
        workspace_id = context.workspaceId
        if not workspace_id:
            raise ValueError(
                "Aucun workspace actif pour les connecteurs."
            )
        return workspace_id

    def list_data_connectors(
        self,
        *,
        context: AssistantContext,
        **_: Any,
    ) -> dict[str, Any]:
        workspace_id = self._workspace(context)
        return {
            "workspace_id": workspace_id,
            "connectors": list_connectors(workspace_id),
            "sources": list_sources(workspace_id),
        }

    def discover_data_connector(
        self,
        *,
        context: AssistantContext,
        connector_id: str,
        max_tables: int = 100,
        **_: Any,
    ) -> dict[str, Any]:
        workspace_id = self._workspace(context)
        return discover_connector(
            workspace_id,
            connector_id,
            max_tables=max_tables,
        )

    def test_data_connector(
        self,
        *,
        context: AssistantContext,
        connector_id: str,
        **_: Any,
    ) -> dict[str, Any]:
        workspace_id = self._workspace(context)
        return test_connector(
            workspace_id,
            connector_id,
        )


class V212MLOpsBridge:
    @staticmethod
    def _identity(context: AssistantContext) -> tuple[str, str]:
        access = current_access_context()
        if context.workspaceId is None:
            return LOCAL_ACTOR, LOCAL_WORKSPACE
        if access is None:
            raise PermissionError("Contexte Entreprise requis pour cette opération MLOps.")
        return str(access.user_id), str(access.workspace_id)

    def get_model_registry_status(
        self,
        *,
        context: AssistantContext,
        **_: Any,
    ) -> dict[str, Any]:
        _actor, workspace_id = self._identity(context)
        if not context.activeModelId:
            raise ValueError("Aucun modèle actif.")
        return get_registry_entry(workspace_id, context.activeModelId)

    def monitor_model_health(
        self,
        *,
        context: AssistantContext,
        current_dataset_id: str | None = None,
        policy: dict[str, Any] | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        actor, workspace_id = self._identity(context)
        if not context.activeModelId:
            raise ValueError("Aucun modèle actif.")
        dataset_id = current_dataset_id or context.activeDatasetId
        if not dataset_id:
            raise ValueError("Aucun dataset courant fourni pour le monitoring.")
        return monitor_model(
            actor,
            workspace_id,
            context.activeModelId,
            current_dataset_id=dataset_id,
            policy=policy,
        )

    def check_model_retraining(
        self,
        *,
        context: AssistantContext,
        create_request: bool = False,
        **_: Any,
    ) -> dict[str, Any]:
        actor, workspace_id = self._identity(context)
        if not context.activeModelId:
            raise ValueError("Aucun modèle actif.")
        return check_retraining(
            actor,
            workspace_id,
            context.activeModelId,
            create_request=bool(create_request),
        )

    def request_model_retraining(
        self,
        *,
        context: AssistantContext,
        create_request: bool = True,
        **_: Any,
    ) -> dict[str, Any]:
        return self.check_model_retraining(
            context=context,
            create_request=True,
        )

    def transition_model_stage(
        self,
        *,
        context: AssistantContext,
        target_stage: str,
        note: str = "",
        **_: Any,
    ) -> dict[str, Any]:
        actor, workspace_id = self._identity(context)
        if not context.activeModelId:
            raise ValueError("Aucun modèle actif.")
        return transition_model(
            actor,
            workspace_id,
            context.activeModelId,
            target_stage=target_stage,
            note=note,
        )


    def list_feature_sets(
        self,
        *,
        context: AssistantContext,
        **_: Any,
    ) -> dict[str, Any]:
        _actor, workspace_id = self._identity(context)
        rows = list_feature_sets(workspace_id)
        return {"feature_sets": rows, "count": len(rows)}
    
    def materialize_feature_set(
        self,
        *,
        context: AssistantContext,
        feature_set_id: str,
        source_dataset_id: str | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        actor, workspace_id = self._identity(context)
        return materialize_feature_set(
            actor,
            workspace_id,
            feature_set_id,
            source_dataset_id=source_dataset_id,
        )
    
    def list_model_deployments(
        self,
        *,
        context: AssistantContext,
        **_: Any,
    ) -> dict[str, Any]:
        _actor, workspace_id = self._identity(context)
        rows = list_deployments(workspace_id)
        return {"deployments": rows, "count": len(rows)}
    
    def score_model_deployment(
        self,
        *,
        context: AssistantContext,
        endpoint_key: str,
        rows: list[dict[str, Any]],
        request_id: str | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        _actor, workspace_id = self._identity(context)
        return score_deployment(
            workspace_id,
            endpoint_key,
            rows,
            request_id=request_id,
        )
    
    def batch_score_model(
        self,
        *,
        context: AssistantContext,
        dataset_id: str,
        prediction_column: str = "prediction",
        **_: Any,
    ) -> dict[str, Any]:
        actor, workspace_id = self._identity(context)
        model_id = context.activeModelId
        if not model_id:
            raise ValueError("Aucun modèle actif.")
        return batch_score_dataset(
            actor,
            workspace_id,
            model_id=model_id,
            dataset_id=dataset_id,
            prediction_column=prediction_column,
        )
    
    def rollback_model_deployment(
        self,
        *,
        context: AssistantContext,
        deployment_id: str,
        **_: Any,
    ) -> dict[str, Any]:
        actor, workspace_id = self._identity(context)
        return rollback_deployment(
            actor,
            workspace_id,
            deployment_id,
        )
    
    
class V212NotebookBridge:
    def execute_notebook_cell(
        self,
        *,
        context: AssistantContext,
        notebook_id: str,
        cell_id: str,
        **_: Any,
    ) -> dict[str, Any]:
        result = run_notebook_cell(notebook_id, cell_id)
        return {
            "status": result.get("status"),
            "notebook_id": notebook_id,
            "cell_id": cell_id,
            "run_id": result.get("id"),
            "engine": result.get("engine"),
            "result": result.get("result"),
            "artifacts": result.get("artifacts", []),
            "provenance": result.get("provenance", {}),
            "elapsed_ms": result.get("elapsed_ms"),
            "error": result.get("stderr") if result.get("status") != "succeeded" else None,
        }


class V212ReportBridge:
    def generate_report(
        self,
        *,
        context: AssistantContext,
        title: str,
        format: str = "pdf",
        include_methodology: bool = True,
        include_provenance: bool = True,
        include_visualizations: bool = True,
        custom_blocks: list[dict[str, Any]] | None = None,
        block_order: list[str] | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        dataset_id = _dataset_id(context)
        sections = [
            "executive_summary",
            "analytical_story",
            "overview",
            "quality",
            "descriptive",
            "limitations",
        ]
        if include_visualizations:
            sections.append("visualizations")
        if include_methodology:
            sections.append("methodology")
        if include_provenance:
            sections.append("provenance")
        report = build_report(
            dataset_id,
            title=title,
            sections=sections,
            auto_story=True,
            auto_visualizations=include_visualizations,
            custom_blocks=custom_blocks or None,
            block_order=block_order or None,
        )
        report_id = report["id"]
        path = export_report(report_id, format)
        return {
            "report_id": report_id,
            "dataset_id": dataset_id,
            "format": format,
            "artifact_path": str(path),
            "download_path": f"/api/v1/datasets/{dataset_id}/reports/{report_id}/export/{format}",
            "rollback_token": report_id,
        }


class V212FileBridge:
    def inspect_uploaded_file(
        self,
        *,
        context: AssistantContext,
        file_id: str,
        parse_tables: bool = True,
        max_pages: int | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        # In v2.12 uploaded structured files become datasets. `file_id` is therefore
        # resolved through the governed dataset metadata store.
        meta = get_meta(file_id)
        result = {
            "file_id": file_id,
            "metadata": meta,
            "parse_tables": parse_tables,
            "max_pages": max_pages,
        }
        try:
            df = load_dataframe(file_id)
            result["rows"] = int(len(df))
            result["columns"] = [str(c) for c in df.columns]
            result["preview"] = _jsonable_records(df, 10)
        except Exception:
            result["preview"] = []
        return result

    def export_dataset(
        self,
        *,
        context: AssistantContext,
        format: str,
        columns: list[str] | None = None,
        include_metadata: bool = True,
        **_: Any,
    ) -> dict[str, Any]:
        dataset_id, df = _load(context)
        if columns:
            unknown = [c for c in columns if c not in df.columns]
            if unknown:
                raise ValueError(f"Colonnes inconnues : {', '.join(unknown)}")
            df = df[columns].copy()

        if format == "geojson":
            raise ValueError("GeoJSON nécessite le moteur SIG, encore partiel dans cette fusion.")

        settings = get_settings()
        export_dir = settings.data_root / "assistant_exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        path = export_dir / f"{dataset_id}.{format}"

        if format == "csv":
            df.to_csv(path, index=False)
        elif format == "xlsx":
            df.to_excel(path, index=False)
        elif format == "parquet":
            df.to_parquet(path, index=False)
        elif format == "json":
            df.to_json(path, orient="records", force_ascii=False, date_format="iso")
        else:
            raise ValueError(f"Format d'export non supporté : {format}")

        payload = {
            "dataset_id": dataset_id,
            "format": format,
            "artifact_path": str(path),
            "rows": int(len(df)),
            "columns": int(len(df.columns)),
        }
        if include_metadata:
            payload["metadata"] = get_meta(dataset_id)
        return payload

    def export_sensitive_data(self, *, context: AssistantContext, **kwargs: Any) -> dict[str, Any]:
        return self.export_dataset(context=context, **kwargs)


def bind_v212_host(registry: AssistantToolRegistry) -> None:
    data = V212DataBridge()
    visual = V212VisualizationBridge()
    analysis = V212AnalysisBridge()
    ml = V212MLBridge()
    reports = V212ReportBridge()
    files = V212FileBridge()
    notebooks = V212NotebookBridge()
    mlops = V212MLOpsBridge()
    connectors = V212ConnectorBridge()

    mapping = {
        "profile_dataset": data.profile_dataset,
        "inspect_missing_values": data.inspect_missing_values,
        "apply_reversible_transform": data.apply_reversible_transform,
        "merge_datasets": data.merge_datasets,
        "delete_column": data.delete_column,
        "create_visualization": visual.create_visualization,
        "diagnose_visualization": visual.diagnose_visualization,
        "diagnose_analysis_failure": analysis.diagnose_analysis_failure,
        "forecast_dataset": analysis.forecast_dataset,
        "detect_dataset_anomalies": analysis.detect_dataset_anomalies,
        "generate_dataset_insights": analysis.generate_dataset_insights,
        "run_statistical_test": analysis.run_statistical_test,
        "run_regression": analysis.run_regression,
        "run_root_cause_analysis": analysis.run_root_cause_analysis,
        "inspect_data_leakage": ml.inspect_data_leakage,
        "benchmark_models": ml.benchmark_models,
        "run_automl": ml.run_automl,
        "explain_model": ml.explain_model,
        "evaluate_model_fairness": ml.evaluate_model_fairness,
        "assess_model_risk": ml.assess_model_risk,
        "responsible_ai_publication_gate": ml.responsible_ai_publication_gate,
        "optimize_decision_scenarios": ml.optimize_decision_scenarios,
        "generate_report": reports.generate_report,
        "inspect_uploaded_file": files.inspect_uploaded_file,
        "export_dataset": files.export_dataset,
        "export_sensitive_data": files.export_sensitive_data,
        "execute_notebook_cell": notebooks.execute_notebook_cell,
        "list_feature_sets": mlops.list_feature_sets,
        "materialize_feature_set": mlops.materialize_feature_set,
        "list_model_deployments": mlops.list_model_deployments,
        "score_model_deployment": mlops.score_model_deployment,
        "batch_score_model": mlops.batch_score_model,
        "rollback_model_deployment": mlops.rollback_model_deployment,
        "get_model_registry_status": mlops.get_model_registry_status,
        "monitor_model_health": mlops.monitor_model_health,
        "check_model_retraining": mlops.check_model_retraining,
        "request_model_retraining": mlops.request_model_retraining,
        "transition_model_stage": mlops.transition_model_stage,
        "list_data_connectors": connectors.list_data_connectors,
        "discover_data_connector": connectors.discover_data_connector,
        "test_data_connector": connectors.test_data_connector,
    }

    for name, handler in mapping.items():
        if registry.get(name) is not None:
            registry.bind_handler(name, handler)
