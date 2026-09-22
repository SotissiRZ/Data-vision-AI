from __future__ import annotations

import ast
import base64
import json
import os
import resource
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.kernel_manager import manager as kernel_manager

app = FastAPI(
    title="DataVision Notebook Sandbox",
    version="2.69.0",
    docs_url=None,
    redoc_url=None,
)

MAX_STDIO = 120_000
MAX_ARTIFACT_BYTES = 5 * 1024 * 1024
MAX_TOTAL_ARTIFACT_BYTES = 20 * 1024 * 1024
ALLOWED_ARTIFACT_EXTENSIONS = {
    ".png", ".svg", ".html", ".json", ".csv", ".txt"
}


def _limits(cpu_seconds: int, memory_mb: int):
    def apply():
        resource.setrlimit(
            resource.RLIMIT_CPU,
            (max(1, cpu_seconds), max(1, cpu_seconds + 1)),
        )
        memory = max(128, memory_mb) * 1024 * 1024
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


def _safe_env(workdir: Path) -> dict[str, str]:
    return {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "PYTHONUNBUFFERED": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": "",
        "MPLBACKEND": "Agg",
        "HOME": str(workdir / "home"),
        "TMPDIR": str(workdir / "tmp"),
        "DATAVISION_SANDBOX": "1",
    }


def _truncate(text: str | None) -> str:
    raw = text or ""
    if len(raw) <= MAX_STDIO:
        return raw
    return raw[:MAX_STDIO] + "\n… sortie tronquée par DataVision …"


def _collect_artifacts(output_dir: Path) -> list[dict[str, Any]]:
    artifacts = []
    total = 0

    for path in sorted(output_dir.rglob("*")):
        if not path.is_file():
            continue
        ext = path.suffix.lower()
        if ext not in ALLOWED_ARTIFACT_EXTENSIONS:
            continue

        size = path.stat().st_size
        if size > MAX_ARTIFACT_BYTES or total + size > MAX_TOTAL_ARTIFACT_BYTES:
            continue

        total += size
        raw = path.read_bytes()
        artifacts.append(
            {
                "name": path.name,
                "size": size,
                "extension": ext,
                "content_base64": base64.b64encode(raw).decode("ascii"),
            }
        )

    return artifacts


def _python_wrapper(user_code: str) -> str:
    parsed = ast.parse(user_code or "", mode="exec")
    last_expr = None
    if parsed.body and isinstance(parsed.body[-1], ast.Expr):
        last_expr = ast.unparse(parsed.body[-1].value)
        parsed.body = parsed.body[:-1]

    body = ast.unparse(parsed)
    tail = (
        f"_dv_last_result = ({last_expr})"
        if last_expr
        else "_dv_last_result = None"
    )

    return f"""
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

try:
    import polars as pl
except Exception:
    pl = None

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except Exception:
    plt = None

DATASET_PATH = Path(os.environ["DATAVISION_DATASET_PATH"])
OUTPUT_DIR = Path(os.environ["DATAVISION_OUTPUT_DIR"])
RESULT_PATH = Path(os.environ["DATAVISION_RESULT_PATH"])
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

df = pd.read_parquet(DATASET_PATH)
dataset = df

def dv_save_dataframe(frame, name="result.csv"):
    target = OUTPUT_DIR / Path(name).name
    frame.to_csv(target, index=False)
    return str(target)

def dv_save_json(value, name="result.json"):
    target = OUTPUT_DIR / Path(name).name
    target.write_text(json.dumps(value, ensure_ascii=False, default=str), encoding="utf-8")
    return str(target)

def _serialize(value):
    if value is None:
        return {{"type": "none", "value": None}}
    if isinstance(value, pd.DataFrame):
        preview = value.head(200).astype(object).where(pd.notna(value.head(200)), None)
        return {{
            "type": "dataframe",
            "columns": [str(c) for c in preview.columns],
            "rows": preview.to_dict(orient="records"),
            "shape": [int(value.shape[0]), int(value.shape[1])],
            "truncated": len(value) > 200,
        }}
    if isinstance(value, pd.Series):
        sample = value.head(200).astype(object).where(pd.notna(value.head(200)), None)
        return {{
            "type": "series",
            "name": str(value.name),
            "values": sample.tolist(),
            "length": int(len(value)),
            "truncated": len(value) > 200,
        }}
    if isinstance(value, np.ndarray):
        return {{
            "type": "ndarray",
            "shape": list(value.shape),
            "value": value.tolist() if value.size <= 2000 else value.flatten()[:2000].tolist(),
            "truncated": value.size > 2000,
        }}
    if isinstance(value, (str, int, float, bool, list, dict)):
        return {{"type": type(value).__name__, "value": value}}
    return {{"type": type(value).__name__, "value": repr(value)[:5000]}}

{body}
{tail}

if plt is not None:
    for index, figure_number in enumerate(plt.get_fignums(), start=1):
        figure = plt.figure(figure_number)
        figure.savefig(
            OUTPUT_DIR / f"figure_{{index}}.png",
            dpi=150,
            bbox_inches="tight",
        )

RESULT_PATH.write_text(
    json.dumps(_serialize(_dv_last_result), ensure_ascii=False, default=str),
    encoding="utf-8",
)
"""


def _r_wrapper(user_code: str) -> str:
    escaped = json.dumps(user_code or "")
    return f"""
suppressWarnings(suppressMessages(library(jsonlite)))
dataset_path <- Sys.getenv("DATAVISION_DATASET_PATH")
result_path <- Sys.getenv("DATAVISION_RESULT_PATH")
output_dir <- Sys.getenv("DATAVISION_OUTPUT_DIR")

data <- read.csv(dataset_path, check.names=FALSE)
dataset <- data

dv_save_dataframe <- function(frame, name="result.csv") {{
  target <- file.path(output_dir, basename(name))
  write.csv(frame, target, row.names=FALSE)
  target
}}

code <- {escaped}
exprs <- parse(text=code)
last_value <- NULL
if (length(exprs) > 0) {{
  for (expr in exprs) {{
    last_value <- eval(expr, envir=.GlobalEnv)
  }}
}}

serialize_value <- function(value) {{
  if (is.null(value)) {{
    return(list(type="none", value=NULL))
  }}
  if (is.data.frame(value)) {{
    preview <- head(value, 200)
    return(list(
      type="dataframe",
      columns=names(preview),
      rows=unname(split(preview, seq_len(nrow(preview)))),
      shape=list(nrow(value), ncol(value)),
      truncated=nrow(value) > 200
    ))
  }}
  if (is.atomic(value) && length(value) <= 2000) {{
    return(list(type=class(value)[1], value=value))
  }}
  list(type=class(value)[1], value=substr(capture.output(str(value)), 1, 5000))
}}

write(
  toJSON(serialize_value(last_value), auto_unbox=TRUE, dataframe="rows", null="null"),
  file=result_path
)
"""


def _execute(
    *,
    language: str,
    code: str,
    dataset_bytes: bytes,
    timeout_seconds: int,
    memory_mb: int,
) -> dict[str, Any]:
    timeout_seconds = max(1, min(int(timeout_seconds), 60))
    memory_mb = max(128, min(int(memory_mb), 2048))

    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="dv-notebook-") as temp:
        root = Path(temp)
        (root / "home").mkdir()
        (root / "tmp").mkdir()
        output_dir = root / "output"
        output_dir.mkdir()
        result_path = root / "result.json"

        if language == "python":
            dataset_path = root / "dataset.parquet"
            dataset_path.write_bytes(dataset_bytes)
            script_path = root / "cell.py"
            try:
                wrapper = _python_wrapper(code)
            except SyntaxError as exc:
                return {
                    "status": "failed",
                    "engine": "python",
                    "stdout": "",
                    "stderr": str(exc),
                    "result": None,
                    "artifacts": [],
                    "elapsed_ms": 0,
                    "error_type": "SyntaxError",
                }
            script_path.write_text(wrapper, encoding="utf-8")
            command = ["python", "-I", "-u", str(script_path)]
        elif language == "r":
            dataset_path = root / "dataset.csv"
            dataset_path.write_bytes(dataset_bytes)
            script_path = root / "cell.R"
            script_path.write_text(_r_wrapper(code), encoding="utf-8")
            command = ["Rscript", "--vanilla", str(script_path)]
        else:
            raise ValueError("Langage sandbox inconnu.")

        env = _safe_env(root)
        env["DATAVISION_DATASET_PATH"] = str(dataset_path)
        env["DATAVISION_OUTPUT_DIR"] = str(output_dir)
        env["DATAVISION_RESULT_PATH"] = str(result_path)

        try:
            completed = subprocess.run(
                command,
                cwd=str(root),
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout_seconds + 2,
                preexec_fn=_limits(timeout_seconds, memory_mb),
            )
        except subprocess.TimeoutExpired as exc:
            return {
                "status": "failed",
                "engine": language,
                "stdout": _truncate(exc.stdout if isinstance(exc.stdout, str) else ""),
                "stderr": "Temps d'exécution maximal dépassé.",
                "result": None,
                "artifacts": [],
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                "error_type": "Timeout",
            }

        result = None
        if result_path.exists():
            try:
                result = json.loads(result_path.read_text(encoding="utf-8"))
            except Exception:
                result = None

        return {
            "status": "succeeded" if completed.returncode == 0 else "failed",
            "engine": language,
            "return_code": completed.returncode,
            "stdout": _truncate(completed.stdout),
            "stderr": _truncate(completed.stderr),
            "result": result,
            "artifacts": _collect_artifacts(output_dir),
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
            "error_type": None if completed.returncode == 0 else "ExecutionError",
        }


def _health_payload() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "datavision-notebook-sandbox",
        "version": "2.69.0",
        "languages": ["python", "r"],
        "network_policy": "internal-only",
        "persistent_kernels": True,
        "active_kernels": len(kernel_manager.list()),
    }


@app.get("/health/live")
def health_live():
    return _health_payload()


@app.get("/health/ready")
def health_ready():
    return _health_payload()


@app.get("/health")
def health():
    return _health_payload()


@app.post("/execute")
async def execute(
    language: str = Form(...),
    code: str = Form(...),
    timeout_seconds: int = Form(20),
    memory_mb: int = Form(768),
    dataset: UploadFile = File(...),
):
    if language not in {"python", "r"}:
        raise HTTPException(status_code=422, detail="Langage non supporté.")
    if len(code) > 100_000:
        raise HTTPException(status_code=413, detail="Cellule trop volumineuse.")

    raw = await dataset.read()
    if len(raw) > 200 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Dataset trop volumineux pour cette exécution.")

    try:
        return _execute(
            language=language,
            code=code,
            dataset_bytes=raw,
            timeout_seconds=timeout_seconds,
            memory_mb=memory_mb,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Sandbox failure: {type(exc).__name__}") from exc


class KernelOpenRequest(BaseModel):
    session_id: str = Field(min_length=8, max_length=180)
    language: str = Field(pattern="^(python|r)$")
    memory_mb: int = Field(default=768, ge=128, le=2048)


@app.post("/sessions/open")
def session_open(payload: KernelOpenRequest):
    try:
        session, created = kernel_manager.open(
            payload.session_id,
            payload.language,
            payload.memory_mb,
        )
        return session.info(created=created)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Kernel open failure: {type(exc).__name__}") from exc


@app.get("/sessions")
def sessions_list():
    return {"items": kernel_manager.list()}


@app.get("/sessions/{session_id}")
def session_status(session_id: str):
    session = kernel_manager.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Kernel introuvable.")
    return session.info()


@app.get("/sessions/{session_id}/variables")
def session_variables(session_id: str):
    session = kernel_manager.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Kernel introuvable.")
    return session.inspect()


@app.post("/sessions/{session_id}/restart")
def session_restart(session_id: str, payload: KernelOpenRequest):
    if payload.session_id != session_id:
        raise HTTPException(status_code=422, detail="Session incohérente.")
    try:
        session = kernel_manager.restart(
            session_id,
            payload.language,
            payload.memory_mb,
        )
        return session.info(created=True)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Kernel restart failure: {type(exc).__name__}") from exc


@app.delete("/sessions/{session_id}")
def session_close(session_id: str):
    return {"ok": kernel_manager.close(session_id)}


@app.post("/sessions/{session_id}/execute")
async def session_execute(
    session_id: str,
    code: str = Form(...),
    timeout_seconds: int = Form(20),
    dataset: UploadFile = File(...),
):
    session = kernel_manager.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Kernel introuvable.")
    if len(code) > 100_000:
        raise HTTPException(status_code=413, detail="Cellule trop volumineuse.")
    raw = await dataset.read()
    if len(raw) > 200 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Dataset trop volumineux pour cette exécution.")
    try:
        return session.execute(
            code=code,
            dataset_bytes=raw,
            timeout_seconds=max(1, min(int(timeout_seconds), 60)),
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Kernel execution failure: {type(exc).__name__}") from exc


@app.get("/packages")
def package_inventory():
    import importlib.metadata
    python_packages = {
        dist.metadata.get("Name", "").lower(): dist.version
        for dist in importlib.metadata.distributions()
        if dist.metadata.get("Name")
    }
    r_packages: dict[str, str] = {}
    try:
        completed = subprocess.run(
            [
                "Rscript",
                "--vanilla",
                "-e",
                "ip<-installed.packages();cat(jsonlite::toJSON(as.list(setNames(ip[,3],tolower(rownames(ip)))),auto_unbox=TRUE))",
            ],
            capture_output=True,
            text=True,
            timeout=8,
            env={**os.environ, "HOME": "/tmp/datavision-home"},
        )
        if completed.returncode == 0 and completed.stdout.strip():
            raw = json.loads(completed.stdout)
            if isinstance(raw, dict):
                r_packages = {str(k): str(v) for k, v in raw.items()}
    except Exception:
        r_packages = {}
    return {
        "python": python_packages,
        "r": r_packages,
        "install_policy": "image-managed",
        "dynamic_install": False,
    }
