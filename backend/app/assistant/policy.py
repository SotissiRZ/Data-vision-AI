from __future__ import annotations

from .models import ActionCheckResponse, AssistantAction, AssistantContext


ALWAYS_DENY_TOOLS = {
    "overwrite_original_dataset",
    "disable_audit_log",
    "bypass_rls",
    "reveal_secret",
}

CONFIRMATION_TOOLS = {
    "delete_dataset",
    "delete_column",
    "drop_table",
    "write_external_system",
    "send_external_message",
    "publish_report",
    "export_sensitive_data",
    "execute_notebook_cell",
}


def evaluate_action_policy(
    action: AssistantAction,
    context: AssistantContext,
) -> ActionCheckResponse:
    """
    Local safety gate.

    This does NOT replace DataVision RBAC/RLS/column-security. It adds an
    assistant-specific gate before the existing authorization layer.
    """
    if action.tool in ALWAYS_DENY_TOOLS:
        return ActionCheckResponse(
            decision="deny",
            reason="Cette action ne peut pas être effectuée par l'assistant.",
        )

    if action.tool in CONFIRMATION_TOOLS:
        return ActionCheckResponse(
            decision="confirmation_required",
            reason="Cette action modifie ou diffuse des données et exige une confirmation humaine.",
        )

    if action.risk in {"destructive", "external"}:
        return ActionCheckResponse(
            decision="confirmation_required",
            reason=f"Action classée {action.risk}; confirmation obligatoire.",
        )

    if action.risk == "reversible":
        return ActionCheckResponse(
            decision="allow",
            reason="Action réversible autorisable sous réserve des permissions DataVision existantes.",
        )

    return ActionCheckResponse(
        decision="allow",
        reason="Action de lecture/non destructive; les permissions DataVision restent applicables.",
    )
