from __future__ import annotations

import io
from typing import Any

import httpx
import pandas as pd

from app.core.config import get_settings


class NotebookSandboxUnavailable(RuntimeError):
    pass


def sandbox_health() -> dict[str, Any]:
    settings = get_settings()
    try:
        response = httpx.get(
            f"{settings.notebook_sandbox_url.rstrip('/')}/health",
            timeout=3.0,
        )
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        raise NotebookSandboxUnavailable(
            "Le service sandbox notebook est indisponible."
        ) from exc


def execute_sandboxed(
    *,
    language: str,
    code: str,
    dataframe: pd.DataFrame,
) -> dict[str, Any]:
    settings = get_settings()
    if len(code) > settings.notebook_max_code_chars:
        raise ValueError("Cellule trop volumineuse.")

    if language == "python":
        buffer = io.BytesIO()
        dataframe.to_parquet(buffer, index=False)
        filename = "dataset.parquet"
        content_type = "application/octet-stream"
    elif language == "r":
        raw = dataframe.to_csv(index=False).encode("utf-8")
        buffer = io.BytesIO(raw)
        filename = "dataset.csv"
        content_type = "text/csv"
    else:
        raise ValueError("Langage sandbox non supporté.")

    try:
        response = httpx.post(
            f"{settings.notebook_sandbox_url.rstrip('/')}/execute",
            data={
                "language": language,
                "code": code,
                "timeout_seconds": str(settings.notebook_timeout_seconds),
                "memory_mb": str(settings.notebook_memory_mb),
            },
            files={
                "dataset": (
                    filename,
                    buffer.getvalue(),
                    content_type,
                )
            },
            timeout=settings.notebook_timeout_seconds + 8,
        )
        response.raise_for_status()
        return response.json()
    except httpx.TimeoutException as exc:
        raise NotebookSandboxUnavailable(
            "Le sandbox a dépassé le délai autorisé."
        ) from exc
    except httpx.HTTPError as exc:
        detail = ""
        if getattr(exc, "response", None) is not None:
            try:
                detail = str(exc.response.json().get("detail") or "")
            except Exception:
                detail = ""
        raise NotebookSandboxUnavailable(
            detail or "Échec de communication avec le sandbox notebook."
        ) from exc
