from __future__ import annotations

import ast
import contextlib
import io
import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

try:
    import polars as pl
except Exception:  # pragma: no cover
    pl = None

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except Exception:  # pragma: no cover
    plt = None

MAX_STDIO = 120_000


def _truncate(text: str | None) -> str:
    raw = text or ""
    if len(raw) <= MAX_STDIO:
        return raw
    return raw[:MAX_STDIO] + "\n… sortie tronquée par DataVision …"


def _serialize(value: Any) -> dict[str, Any]:
    if value is None:
        return {"type": "none", "value": None}
    if isinstance(value, pd.DataFrame):
        preview = value.head(200).astype(object).where(pd.notna(value.head(200)), None)
        return {
            "type": "dataframe",
            "columns": [str(c) for c in preview.columns],
            "rows": preview.to_dict(orient="records"),
            "shape": [int(value.shape[0]), int(value.shape[1])],
            "truncated": len(value) > 200,
        }
    if isinstance(value, pd.Series):
        sample = value.head(200).astype(object).where(pd.notna(value.head(200)), None)
        return {
            "type": "series",
            "name": str(value.name),
            "values": sample.tolist(),
            "length": int(len(value)),
            "truncated": len(value) > 200,
        }
    if isinstance(value, np.ndarray):
        flat = value.flatten()
        return {
            "type": "ndarray",
            "shape": list(value.shape),
            "value": value.tolist() if value.size <= 2000 else flat[:2000].tolist(),
            "truncated": value.size > 2000,
        }
    if isinstance(value, (str, int, float, bool, list, dict)):
        return {"type": type(value).__name__, "value": value}
    return {"type": type(value).__name__, "value": repr(value)[:5000]}


def _exec_last_expr(code: str, namespace: dict[str, Any]) -> Any:
    parsed = ast.parse(code or "", mode="exec")
    if not parsed.body:
        return None
    last = parsed.body[-1]
    if isinstance(last, ast.Expr):
        body = ast.Module(body=parsed.body[:-1], type_ignores=[])
        if body.body:
            exec(compile(body, "<datavision-cell>", "exec"), namespace, namespace)
        expr = ast.Expression(last.value)
        return eval(compile(expr, "<datavision-cell>", "eval"), namespace, namespace)
    exec(compile(parsed, "<datavision-cell>", "exec"), namespace, namespace)
    return None


def main() -> None:
    namespace: dict[str, Any] = {
        "__name__": "__datavision_notebook__",
        "pd": pd,
        "np": np,
        "pl": pl,
        "plt": plt,
    }
    execution_count = 0

    for raw in sys.stdin:
        try:
            request = json.loads(raw)
        except Exception:
            print(json.dumps({"status": "failed", "error_type": "ProtocolError"}), flush=True)
            continue

        action = request.get("action", "execute")
        if action == "shutdown":
            print(json.dumps({"status": "ok", "execution_count": execution_count}), flush=True)
            break
        if action == "inspect":
            public = sorted(
                key for key in namespace
                if not key.startswith("_") and key not in {"pd", "np", "pl", "plt", "df", "dataset"}
            )
            print(json.dumps({
                "status": "ok",
                "execution_count": execution_count,
                "variables": public[:200],
            }), flush=True)
            continue

        dataset_path = Path(str(request["dataset_path"]))
        output_dir = Path(str(request["output_dir"]))
        output_dir.mkdir(parents=True, exist_ok=True)
        code = str(request.get("code") or "")

        frame = pd.read_parquet(dataset_path) if dataset_path.suffix.lower() == ".parquet" else pd.read_csv(dataset_path)
        namespace["df"] = frame
        namespace["dataset"] = frame
        namespace["DATASET_PATH"] = dataset_path
        namespace["OUTPUT_DIR"] = output_dir

        def dv_save_dataframe(value, name="result.csv"):
            target = output_dir / Path(str(name)).name
            value.to_csv(target, index=False)
            return str(target)

        def dv_save_json(value, name="result.json"):
            target = output_dir / Path(str(name)).name
            target.write_text(
                json.dumps(value, ensure_ascii=False, default=str),
                encoding="utf-8",
            )
            return str(target)

        namespace["dv_save_dataframe"] = dv_save_dataframe
        namespace["dv_save_json"] = dv_save_json

        stdout = io.StringIO()
        stderr = io.StringIO()
        response: dict[str, Any]
        try:
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                value = _exec_last_expr(code, namespace)
            execution_count += 1

            if plt is not None:
                for index, figure_number in enumerate(plt.get_fignums(), start=1):
                    figure = plt.figure(figure_number)
                    figure.savefig(
                        output_dir / f"figure_{index}.png",
                        dpi=150,
                        bbox_inches="tight",
                    )
                plt.close("all")

            response = {
                "status": "succeeded",
                "engine": "python-persistent",
                "stdout": _truncate(stdout.getvalue()),
                "stderr": _truncate(stderr.getvalue()),
                "result": _serialize(value),
                "error_type": None,
                "execution_count": execution_count,
            }
        except SyntaxError as exc:
            response = {
                "status": "failed",
                "engine": "python-persistent",
                "stdout": _truncate(stdout.getvalue()),
                "stderr": str(exc),
                "result": None,
                "error_type": "SyntaxError",
                "execution_count": execution_count,
            }
        except BaseException as exc:  # user code boundary
            response = {
                "status": "failed",
                "engine": "python-persistent",
                "stdout": _truncate(stdout.getvalue()),
                "stderr": _truncate("".join(traceback.format_exception_only(type(exc), exc))),
                "result": None,
                "error_type": type(exc).__name__,
                "execution_count": execution_count,
            }
        print(json.dumps(response, ensure_ascii=False, default=str), flush=True)


if __name__ == "__main__":
    main()
