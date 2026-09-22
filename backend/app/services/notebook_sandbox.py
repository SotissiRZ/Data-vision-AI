from __future__ import annotations

import io
from typing import Any

import httpx
import pandas as pd

from app.core.config import get_settings


class NotebookSandboxUnavailable(RuntimeError):
    pass


def _base() -> str:
    return get_settings().notebook_sandbox_url.rstrip("/")


def _detail(exc: httpx.HTTPError, fallback: str) -> str:
    if getattr(exc, "response", None) is not None:
        try:
            payload = exc.response.json()
            if isinstance(payload, dict) and payload.get("detail"):
                return str(payload["detail"])
        except Exception:
            pass
    return fallback


def sandbox_health() -> dict[str, Any]:
    try:
        response = httpx.get(f"{_base()}/health", timeout=3.0)
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        raise NotebookSandboxUnavailable(
            "Le service sandbox notebook est indisponible."
        ) from exc


def sandbox_packages() -> dict[str, Any]:
    try:
        response = httpx.get(f"{_base()}/packages", timeout=8.0)
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        raise NotebookSandboxUnavailable(
            "L'inventaire des packages notebook est indisponible."
        ) from exc


def _dataset_payload(language: str, dataframe: pd.DataFrame) -> tuple[str, bytes, str]:
    if language == "python":
        buffer = io.BytesIO()
        dataframe.to_parquet(buffer, index=False)
        return "dataset.parquet", buffer.getvalue(), "application/octet-stream"
    if language == "r":
        return "dataset.csv", dataframe.to_csv(index=False).encode("utf-8"), "text/csv"
    raise ValueError("Langage sandbox non supporté.")


def execute_sandboxed(
    *,
    language: str,
    code: str,
    dataframe: pd.DataFrame,
) -> dict[str, Any]:
    """Legacy stateless execution kept for backward compatibility."""
    settings = get_settings()
    if len(code) > settings.notebook_max_code_chars:
        raise ValueError("Cellule trop volumineuse.")
    filename, raw, content_type = _dataset_payload(language, dataframe)
    try:
        response = httpx.post(
            f"{_base()}/execute",
            data={
                "language": language,
                "code": code,
                "timeout_seconds": str(settings.notebook_timeout_seconds),
                "memory_mb": str(settings.notebook_memory_mb),
            },
            files={"dataset": (filename, raw, content_type)},
            timeout=settings.notebook_timeout_seconds + 8,
        )
        response.raise_for_status()
        return response.json()
    except httpx.TimeoutException as exc:
        raise NotebookSandboxUnavailable(
            "Le sandbox a dépassé le délai autorisé."
        ) from exc
    except httpx.HTTPError as exc:
        raise NotebookSandboxUnavailable(
            _detail(exc, "Échec de communication avec le sandbox notebook.")
        ) from exc


def open_kernel_session(
    *,
    session_id: str,
    language: str,
) -> dict[str, Any]:
    settings = get_settings()
    try:
        response = httpx.post(
            f"{_base()}/sessions/open",
            json={
                "session_id": session_id,
                "language": language,
                "memory_mb": settings.notebook_memory_mb,
            },
            timeout=6.0,
        )
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as exc:
        raise NotebookSandboxUnavailable(
            _detail(exc, "Impossible d'ouvrir le kernel notebook.")
        ) from exc


def kernel_session_status(session_id: str) -> dict[str, Any] | None:
    try:
        response = httpx.get(f"{_base()}/sessions/{session_id}", timeout=0.5)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as exc:
        raise NotebookSandboxUnavailable(
            _detail(exc, "État du kernel indisponible.")
        ) from exc


def kernel_session_variables(session_id: str) -> dict[str, Any]:
    try:
        response = httpx.get(
            f"{_base()}/sessions/{session_id}/variables",
            timeout=0.75,
        )
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as exc:
        raise NotebookSandboxUnavailable(
            _detail(exc, "Variables du kernel indisponibles.")
        ) from exc


def restart_kernel_session(*, session_id: str, language: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        response = httpx.post(
            f"{_base()}/sessions/{session_id}/restart",
            json={
                "session_id": session_id,
                "language": language,
                "memory_mb": settings.notebook_memory_mb,
            },
            timeout=6.0,
        )
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as exc:
        raise NotebookSandboxUnavailable(
            _detail(exc, "Impossible de redémarrer le kernel.")
        ) from exc


def close_kernel_session(session_id: str) -> bool:
    try:
        response = httpx.delete(f"{_base()}/sessions/{session_id}", timeout=4.0)
        response.raise_for_status()
        return bool(response.json().get("ok"))
    except httpx.HTTPError as exc:
        raise NotebookSandboxUnavailable(
            _detail(exc, "Impossible de fermer le kernel.")
        ) from exc


def execute_sandboxed_session(
    *,
    session_id: str,
    language: str,
    code: str,
    dataframe: pd.DataFrame,
) -> dict[str, Any]:
    settings = get_settings()
    if len(code) > settings.notebook_max_code_chars:
        raise ValueError("Cellule trop volumineuse.")

    opened = open_kernel_session(session_id=session_id, language=language)
    filename, raw, content_type = _dataset_payload(language, dataframe)
    try:
        response = httpx.post(
            f"{_base()}/sessions/{session_id}/execute",
            data={
                "code": code,
                "timeout_seconds": str(settings.notebook_timeout_seconds),
            },
            files={"dataset": (filename, raw, content_type)},
            timeout=settings.notebook_timeout_seconds + 8,
        )
        response.raise_for_status()
        payload = response.json()
        payload.setdefault("kernel", opened)
        payload["kernel_created"] = bool(opened.get("created"))
        return payload
    except httpx.TimeoutException as exc:
        raise NotebookSandboxUnavailable(
            "Le kernel a dépassé le délai autorisé."
        ) from exc
    except httpx.HTTPError as exc:
        raise NotebookSandboxUnavailable(
            _detail(exc, "Échec de communication avec le kernel notebook.")
        ) from exc
