from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .models import AssistantContext


class DataEngineBridge(Protocol):
    def profile_dataset(self, *, context: AssistantContext, **kwargs: Any) -> Any: ...
    def inspect_missing_values(self, *, context: AssistantContext, **kwargs: Any) -> Any: ...
    def apply_reversible_transform(self, *, context: AssistantContext, **kwargs: Any) -> Any: ...
    def merge_datasets(self, *, context: AssistantContext, **kwargs: Any) -> Any: ...
    def delete_column(self, *, context: AssistantContext, **kwargs: Any) -> Any: ...


class VisualizationEngineBridge(Protocol):
    def create_visualization(self, *, context: AssistantContext, **kwargs: Any) -> Any: ...
    def diagnose_visualization(self, *, context: AssistantContext, **kwargs: Any) -> Any: ...


class AnalysisEngineBridge(Protocol):
    def diagnose_analysis_failure(self, *, context: AssistantContext, **kwargs: Any) -> Any: ...
    def run_statistical_test(self, *, context: AssistantContext, **kwargs: Any) -> Any: ...
    def run_regression(self, *, context: AssistantContext, **kwargs: Any) -> Any: ...


class MLEngineBridge(Protocol):
    def inspect_data_leakage(self, *, context: AssistantContext, **kwargs: Any) -> Any: ...
    def run_automl(self, *, context: AssistantContext, **kwargs: Any) -> Any: ...
    def explain_model(self, *, context: AssistantContext, **kwargs: Any) -> Any: ...
    def evaluate_model_fairness(self, *, context: AssistantContext, **kwargs: Any) -> Any: ...
    def assess_model_risk(self, *, context: AssistantContext, **kwargs: Any) -> Any: ...
    def responsible_ai_publication_gate(self, *, context: AssistantContext, **kwargs: Any) -> Any: ...


class GISEngineBridge(Protocol):
    def gis_reproject(self, *, context: AssistantContext, **kwargs: Any) -> Any: ...
    def gis_spatial_join(self, *, context: AssistantContext, **kwargs: Any) -> Any: ...
    def gis_buffer(self, *, context: AssistantContext, **kwargs: Any) -> Any: ...


class ReportEngineBridge(Protocol):
    def generate_report(self, *, context: AssistantContext, **kwargs: Any) -> Any: ...


class FileEngineBridge(Protocol):
    def inspect_uploaded_file(self, *, context: AssistantContext, **kwargs: Any) -> Any: ...
    def export_dataset(self, *, context: AssistantContext, **kwargs: Any) -> Any: ...
    def export_sensitive_data(self, *, context: AssistantContext, **kwargs: Any) -> Any: ...


class ActionConnectorBridge(Protocol):
    def send_external_message(self, *, context: AssistantContext, **kwargs: Any) -> Any: ...


@dataclass
class DataVisionHostBridges:
    data: DataEngineBridge | None = None
    visualization: VisualizationEngineBridge | None = None
    analysis: AnalysisEngineBridge | None = None
    ml: MLEngineBridge | None = None
    report: ReportEngineBridge | None = None
    gis: GISEngineBridge | None = None
    files: FileEngineBridge | None = None
    actions: ActionConnectorBridge | None = None


class MissingHostBridge(RuntimeError):
    pass


def bind_registry_to_host(registry, bridges: DataVisionHostBridges) -> None:
    """
    Bind declarative assistant tools to the actual DataVision application.

    The patch deliberately does not fabricate engine implementations. During
    integration, pass the real v2.12 services here.
    """

    mappings = {
        "profile_dataset": (bridges.data, "profile_dataset"),
        "inspect_missing_values": (bridges.data, "inspect_missing_values"),
        "apply_reversible_transform": (bridges.data, "apply_reversible_transform"),
        "merge_datasets": (bridges.data, "merge_datasets"),
        "delete_column": (bridges.data, "delete_column"),
        "create_visualization": (bridges.visualization, "create_visualization"),
        "diagnose_visualization": (bridges.visualization, "diagnose_visualization"),
        "diagnose_analysis_failure": (bridges.analysis, "diagnose_analysis_failure"),
        "run_statistical_test": (bridges.analysis, "run_statistical_test"),
        "run_regression": (bridges.analysis, "run_regression"),
        "inspect_data_leakage": (bridges.ml, "inspect_data_leakage"),
        "run_automl": (bridges.ml, "run_automl"),
        "explain_model": (bridges.ml, "explain_model"),
        "evaluate_model_fairness": (bridges.ml, "evaluate_model_fairness"),
        "assess_model_risk": (bridges.ml, "assess_model_risk"),
        "responsible_ai_publication_gate": (bridges.ml, "responsible_ai_publication_gate"),
        "gis_reproject": (bridges.gis, "gis_reproject"),
        "gis_spatial_join": (bridges.gis, "gis_spatial_join"),
        "gis_buffer": (bridges.gis, "gis_buffer"),
        "generate_report": (bridges.report, "generate_report"),
        "inspect_uploaded_file": (bridges.files, "inspect_uploaded_file"),
        "export_dataset": (bridges.files, "export_dataset"),
        "export_sensitive_data": (bridges.files, "export_sensitive_data"),
        "send_external_message": (bridges.actions, "send_external_message"),
    }

    for tool_name, (bridge, method_name) in mappings.items():
        if registry.get(tool_name) is None:
            continue

        if bridge is None:
            continue

        handler = getattr(bridge, method_name, None)
        if handler is None:
            raise MissingHostBridge(
                f"Bridge {bridge.__class__.__name__} does not implement {method_name}"
            )

        registry.bind_handler(tool_name, handler)
