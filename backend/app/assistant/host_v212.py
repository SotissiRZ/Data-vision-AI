from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from app.core.config import get_settings
from app.services.advanced_analysis import regression_analysis
from app.services.auth_service import has_permission
from app.services.modeling import automl_train, get_model_card, train_model
from app.services.notebook_service import run_cell as run_notebook_cell
from app.services.preparation import apply_operation, combine_dataframes
from app.services.profiling import profile_dataframe
from app.services.report_builder import build_report, export_report
from app.services.statistics_engine import statistical_test, test_advisor
from app.services.storage import (
    get_meta,
    load_dataframe,
    save_dataframe_version,
)
from app.services.tenant_access import current_access_context
from app.services.visualization import build_visualization, recommend_visualizations
from app.services.xai import model_diagnostics

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
    "report:create": "publish:write",
    "dataset:export": "publish:write",
    "file:read": "dataset:read",
    "action:execute": "actions:trigger",
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

        # Local DataVision mode: no Enterprise workspace selected.
        if context.workspaceId is None:
            return True, "mode local DataVision"

        if access is None:
            return False, "workspace Enterprise fourni sans contexte d'authentification"

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

    def run_automl(
        self,
        *,
        context: AssistantContext,
        task: str,
        target: str | None = None,
        features: list[str] | None = None,
        metric: str | None = None,
        validation: str = "cross_validation",
        max_models: int = 8,
        explain: bool = True,
        **_: Any,
    ) -> dict[str, Any]:
        dataset_id, df = _load(context)
        if task not in {"classification", "regression"}:
            raise ValueError(
                "Le bridge AutoML v2.12 exécute classification/régression. "
                "Clustering et forecasting utilisent leurs moteurs dédiés."
            )
        if not target:
            raise ValueError("Cible requise.")
        work = df
        if features:
            missing = [c for c in features if c not in df.columns]
            if missing:
                raise ValueError(f"Variables inconnues : {', '.join(missing)}")
            work = df[[*features, target]].copy()
        result = automl_train(
            work,
            target=target,
            task=task,
            primary_metric=metric or "auto",
            cv_folds=5 if validation == "cross_validation" else 2,
            tune=True,
            max_candidates=max_models,
            dataset_context={"id": dataset_id, "version": get_meta(dataset_id).get("version")},
        )
        result["requested_explain"] = explain
        result["rollback_token"] = result.get("model_id")
        return result

    def explain_model(
        self,
        *,
        context: AssistantContext,
        method: str,
        row_id: str | int | None = None,
        feature: str | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        model_id = context.activeModelId
        if not model_id:
            raise ValueError("Aucun modèle actif.")
        card = get_model_card(model_id)

        if method in {"feature_importance", "permutation_importance"}:
            return {
                "model_id": model_id,
                "method": method,
                "feature_importance": card.get("feature_importance", []),
                "model_card": card,
            }

        if method in {"confusion_matrix", "calibration"}:
            if not context.activeDatasetId:
                raise ValueError("Dataset actif requis pour les diagnostics.")
            diagnostics = model_diagnostics(
                model_id,
                load_dataframe(context.activeDatasetId),
            )
            return {
                "model_id": model_id,
                "method": method,
                "result": diagnostics.get(method),
                "diagnostics": diagnostics,
            }

        if method.startswith("shap"):
            raise ValueError("SHAP reste explicitement partiel dans la base v2.12.")
        if method in {"partial_dependence", "counterfactual"}:
            raise ValueError(f"{method} n'est pas encore implémenté dans le moteur v2.12.")

        raise ValueError(f"Méthode XAI non supportée : {method}")


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
        )
        report_id = report["id"]
        if format == "pptx":
            raise ValueError("L'export PPTX n'est pas encore disponible dans le moteur de rapport v2.12.")
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

    mapping = {
        "profile_dataset": data.profile_dataset,
        "inspect_missing_values": data.inspect_missing_values,
        "apply_reversible_transform": data.apply_reversible_transform,
        "merge_datasets": data.merge_datasets,
        "delete_column": data.delete_column,
        "create_visualization": visual.create_visualization,
        "diagnose_visualization": visual.diagnose_visualization,
        "diagnose_analysis_failure": analysis.diagnose_analysis_failure,
        "run_statistical_test": analysis.run_statistical_test,
        "run_regression": analysis.run_regression,
        "inspect_data_leakage": ml.inspect_data_leakage,
        "run_automl": ml.run_automl,
        "explain_model": ml.explain_model,
        "generate_report": reports.generate_report,
        "inspect_uploaded_file": files.inspect_uploaded_file,
        "export_dataset": files.export_dataset,
        "export_sensitive_data": files.export_sensitive_data,
        "execute_notebook_cell": notebooks.execute_notebook_cell,
    }

    for name, handler in mapping.items():
        if registry.get(name) is not None:
            registry.bind_handler(name, handler)
