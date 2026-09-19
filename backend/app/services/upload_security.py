from __future__ import annotations

import hashlib
import socket
import struct
import uuid
from typing import Any

from app.core.config import get_settings
from app.services.metadata_store import execute, utcnow

_EICAR = b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE"


def _persist(filename: str, content: bytes, *, status: str, engine: str, detail: str = "") -> dict[str, Any]:
    item = {
        "id": str(uuid.uuid4()),
        "filename": filename[:500],
        "sha256": hashlib.sha256(content).hexdigest(),
        "size_bytes": len(content),
        "status": status,
        "engine": engine,
        "detail": detail[:1000],
        "created_at": utcnow(),
    }
    execute(
        """INSERT INTO upload_security_scans(
             id,filename,sha256,size_bytes,status,engine,detail,created_at
           ) VALUES(:id,:filename,:sha256,:size_bytes,:status,:engine,:detail,:created_at)""",
        item,
    )
    return item


def _clamav_scan(content: bytes) -> tuple[str, str]:
    settings = get_settings()
    with socket.create_connection(
        (settings.clamav_host, int(settings.clamav_port)),
        timeout=float(settings.clamav_timeout_seconds),
    ) as sock:
        sock.settimeout(float(settings.clamav_timeout_seconds))
        sock.sendall(b"zINSTREAM\0")
        view = memoryview(content)
        chunk_size = 64 * 1024
        for offset in range(0, len(content), chunk_size):
            chunk = view[offset : offset + chunk_size]
            sock.sendall(struct.pack(">I", len(chunk)))
            sock.sendall(chunk)
        sock.sendall(struct.pack(">I", 0))
        response = sock.recv(4096).decode("utf-8", errors="replace").strip("\x00\r\n ")
    upper = response.upper()
    if "FOUND" in upper:
        return "infected", response
    if "OK" in upper:
        return "clean", response
    raise RuntimeError(f"Réponse ClamAV inattendue: {response[:300]}")


def scan_upload(filename: str, content: bytes) -> dict[str, Any]:
    settings = get_settings()
    mode = str(settings.antivirus_mode or "preferred").lower()
    if mode not in {"disabled", "preferred", "required"}:
        raise ValueError("ANTIVIRUS_MODE doit être disabled, preferred ou required")

    # Always reject the standard AV validation string even if ClamAV is unavailable.
    if _EICAR in content.upper():
        item = _persist(
            filename,
            content,
            status="infected",
            engine="builtin-eicar-guard",
            detail="EICAR test signature detected",
        )
        raise ValueError(f"Upload refusé par l'antivirus ({item['status']}).")

    if mode == "disabled":
        return _persist(filename, content, status="skipped", engine="disabled")

    try:
        status, detail = _clamav_scan(content)
        item = _persist(filename, content, status=status, engine="clamav", detail=detail)
        if status != "clean":
            raise ValueError("Upload refusé: menace détectée par ClamAV.")
        return item
    except ValueError:
        raise
    except Exception as exc:
        item = _persist(
            filename,
            content,
            status="unavailable",
            engine="clamav",
            detail=f"{type(exc).__name__}: {str(exc)[:800]}",
        )
        if mode == "required":
            raise ValueError(
                "Upload refusé: antivirus requis mais service ClamAV indisponible."
            ) from exc
        return item


def antivirus_status() -> dict[str, Any]:
    settings = get_settings()
    mode = str(settings.antivirus_mode or "preferred").lower()
    try:
        with socket.create_connection(
            (settings.clamav_host, int(settings.clamav_port)),
            timeout=min(float(settings.clamav_timeout_seconds), 2.0),
        ) as sock:
            sock.sendall(b"zPING\0")
            response = sock.recv(128).decode("utf-8", errors="replace").strip("\x00\r\n ")
        available = "PONG" in response.upper()
        error = None
    except Exception as exc:
        available = False
        error = f"{type(exc).__name__}: {str(exc)[:300]}"
    return {
        "mode": mode,
        "engine": "clamav",
        "available": available,
        "required": mode == "required",
        "production_ready": mode == "required" and available,
        "error": error,
    }
