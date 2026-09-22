from __future__ import annotations

import hashlib
import json
import os
import re
import resource
import selectors
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(os.environ.get("DATAVISION_KERNEL_ROOT", "/tmp/datavision-kernels"))
ROOT.mkdir(parents=True, exist_ok=True)
MAX_SESSIONS = max(1, int(os.environ.get("DATAVISION_KERNEL_MAX_SESSIONS", "32")))
SESSION_TTL_SECONDS = max(60, int(os.environ.get("DATAVISION_KERNEL_TTL_SECONDS", "3600")))
ALLOWED_ARTIFACT_EXTENSIONS = {".png", ".svg", ".html", ".json", ".csv", ".txt"}
MAX_ARTIFACT_BYTES = 5 * 1024 * 1024
MAX_TOTAL_ARTIFACT_BYTES = 20 * 1024 * 1024


def _safe_id(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value or "")[:120]
    if cleaned:
        return cleaned
    return hashlib.sha256((value or "kernel").encode("utf-8")).hexdigest()[:32]


def _persistent_limits(memory_mb: int):
    def apply():
        memory = max(128, min(int(memory_mb), 2048)) * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
        resource.setrlimit(
            resource.RLIMIT_FSIZE,
            (MAX_TOTAL_ARTIFACT_BYTES, MAX_TOTAL_ARTIFACT_BYTES),
        )
        resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
        try:
            resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
        except Exception:
            pass

    return apply


def _safe_env(root: Path) -> dict[str, str]:
    home = root / "home"
    tmp = root / "tmp"
    home.mkdir(parents=True, exist_ok=True)
    tmp.mkdir(parents=True, exist_ok=True)
    return {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "PYTHONUNBUFFERED": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": "/srv",
        "MPLBACKEND": "Agg",
        "HOME": str(home),
        "TMPDIR": str(tmp),
        "DATAVISION_SANDBOX": "1",
    }


def _collect_artifacts(output_dir: Path) -> list[dict[str, Any]]:
    import base64

    artifacts: list[dict[str, Any]] = []
    total = 0
    for path in sorted(output_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in ALLOWED_ARTIFACT_EXTENSIONS:
            continue
        size = path.stat().st_size
        if size > MAX_ARTIFACT_BYTES or total + size > MAX_TOTAL_ARTIFACT_BYTES:
            continue
        total += size
        artifacts.append(
            {
                "name": path.name,
                "size": size,
                "extension": path.suffix.lower(),
                "content_base64": base64.b64encode(path.read_bytes()).decode("ascii"),
            }
        )
    return artifacts


@dataclass
class KernelSession:
    session_id: str
    language: str
    memory_mb: int
    root: Path
    process: subprocess.Popen[str]
    created_at: float = field(default_factory=time.time)
    last_used_at: float = field(default_factory=time.time)
    execution_count: int = 0
    generation: str = field(default_factory=lambda: hashlib.sha256(os.urandom(32)).hexdigest()[:16])
    lock: threading.RLock = field(default_factory=threading.RLock)

    @classmethod
    def create(cls, session_id: str, language: str, memory_mb: int) -> "KernelSession":
        safe = _safe_id(session_id)
        root = ROOT / safe
        if root.exists():
            shutil.rmtree(root, ignore_errors=True)
        root.mkdir(parents=True, exist_ok=True)

        if language == "python":
            command = [sys.executable, "-u", "-m", "app.kernel_worker"]
        elif language == "r":
            command = ["Rscript", "--vanilla", "/srv/app/r_kernel_worker.R"]
        else:
            raise ValueError("Langage kernel non supporté.")

        process = subprocess.Popen(
            command,
            cwd=str(root),
            env=_safe_env(root),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            preexec_fn=_persistent_limits(memory_mb),
        )
        return cls(
            session_id=session_id,
            language=language,
            memory_mb=memory_mb,
            root=root,
            process=process,
        )

    def alive(self) -> bool:
        return self.process.poll() is None

    def info(self, *, created: bool = False) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "language": self.language,
            "status": "ready" if self.alive() else "dead",
            "generation": self.generation,
            "execution_count": self.execution_count,
            "created": created,
            "created_at": self.created_at,
            "last_used_at": self.last_used_at,
            "persistent": True,
        }

    def _request(self, payload: dict[str, Any], timeout_seconds: int) -> dict[str, Any]:
        if not self.alive() or self.process.stdin is None or self.process.stdout is None:
            raise RuntimeError("Kernel arrêté.")

        raw = json.dumps(payload, ensure_ascii=False, default=str)
        self.process.stdin.write(raw + "\n")
        self.process.stdin.flush()

        selector = selectors.DefaultSelector()
        selector.register(self.process.stdout, selectors.EVENT_READ)
        events = selector.select(timeout=max(1, timeout_seconds))
        selector.close()
        if not events:
            self.terminate()
            return {
                "status": "failed",
                "engine": f"{self.language}-persistent",
                "stdout": "",
                "stderr": "Temps d'exécution maximal dépassé. Le kernel a été redémarré.",
                "result": None,
                "error_type": "Timeout",
                "execution_count": self.execution_count,
                "kernel_terminated": True,
            }

        line = self.process.stdout.readline()
        if not line:
            stderr = ""
            if self.process.stderr is not None:
                try:
                    stderr = self.process.stderr.read(4096)
                except Exception:
                    stderr = ""
            return {
                "status": "failed",
                "engine": f"{self.language}-persistent",
                "stdout": "",
                "stderr": stderr or "Kernel interrompu.",
                "result": None,
                "error_type": "KernelExited",
                "execution_count": self.execution_count,
            }
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            return {
                "status": "failed",
                "engine": f"{self.language}-persistent",
                "stdout": "",
                "stderr": "Réponse kernel invalide.",
                "result": None,
                "error_type": "ProtocolError",
                "execution_count": self.execution_count,
            }

    def execute(
        self,
        *,
        code: str,
        dataset_bytes: bytes,
        timeout_seconds: int,
    ) -> dict[str, Any]:
        with self.lock:
            self.last_used_at = time.time()
            run_id = hashlib.sha256(os.urandom(32)).hexdigest()[:16]
            run_root = self.root / "runs" / run_id
            run_root.mkdir(parents=True, exist_ok=True)
            output_dir = run_root / "output"
            output_dir.mkdir()
            if self.language == "python":
                dataset_path = run_root / "dataset.parquet"
            else:
                dataset_path = run_root / "dataset.csv"
            dataset_path.write_bytes(dataset_bytes)

            started = time.perf_counter()
            response = self._request(
                {
                    "action": "execute",
                    "code": code,
                    "dataset_path": str(dataset_path),
                    "output_dir": str(output_dir),
                },
                timeout_seconds + 2,
            )
            elapsed = round((time.perf_counter() - started) * 1000, 3)
            self.execution_count = int(response.get("execution_count") or self.execution_count)
            response["elapsed_ms"] = elapsed
            response["artifacts"] = _collect_artifacts(output_dir)
            response["kernel"] = self.info()

            # Dataset/run payloads are disposable; variables remain in the kernel process.
            try:
                dataset_path.unlink(missing_ok=True)
            except Exception:
                pass
            return response

    def inspect(self) -> dict[str, Any]:
        with self.lock:
            response = self._request({"action": "inspect"}, 3)
            response["kernel"] = self.info()
            return response

    def terminate(self) -> None:
        with self.lock:
            if self.alive():
                try:
                    if self.process.stdin is not None:
                        self.process.stdin.write(json.dumps({"action": "shutdown"}) + "\n")
                        self.process.stdin.flush()
                    self.process.wait(timeout=1.5)
                except Exception:
                    self.process.kill()
                    try:
                        self.process.wait(timeout=1)
                    except Exception:
                        pass


class KernelManager:
    def __init__(self) -> None:
        self._sessions: dict[str, KernelSession] = {}
        self._lock = threading.RLock()

    def cleanup(self) -> None:
        now = time.time()
        with self._lock:
            expired = [
                key for key, session in self._sessions.items()
                if not session.alive() or now - session.last_used_at > SESSION_TTL_SECONDS
            ]
            for key in expired:
                session = self._sessions.pop(key)
                session.terminate()

    def open(self, session_id: str, language: str, memory_mb: int) -> tuple[KernelSession, bool]:
        self.cleanup()
        with self._lock:
            current = self._sessions.get(session_id)
            if current is not None and current.alive():
                if current.language != language:
                    raise ValueError("Le langage du kernel ne peut pas être modifié.")
                current.last_used_at = time.time()
                return current, False

            if len(self._sessions) >= MAX_SESSIONS:
                oldest_key = min(self._sessions, key=lambda key: self._sessions[key].last_used_at)
                self._sessions.pop(oldest_key).terminate()

            session = KernelSession.create(session_id, language, memory_mb)
            self._sessions[session_id] = session
            return session, True

    def get(self, session_id: str) -> KernelSession | None:
        self.cleanup()
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None or not session.alive():
                return None
            return session

    def restart(self, session_id: str, language: str, memory_mb: int) -> KernelSession:
        with self._lock:
            current = self._sessions.pop(session_id, None)
            if current is not None:
                current.terminate()
            session = KernelSession.create(session_id, language, memory_mb)
            self._sessions[session_id] = session
            return session

    def close(self, session_id: str) -> bool:
        with self._lock:
            current = self._sessions.pop(session_id, None)
        if current is None:
            return False
        current.terminate()
        return True

    def list(self) -> list[dict[str, Any]]:
        self.cleanup()
        with self._lock:
            return [session.info() for session in self._sessions.values()]


manager = KernelManager()
