#!/usr/bin/env python3
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import platform
import socket
import statistics
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "datavision.performance-evidence/v1"
ROOT = Path(__file__).resolve().parents[1]


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    if len(values) == 1:
        return round(values[0], 4)
    pos = (len(values) - 1) * max(0.0, min(1.0, q))
    lo = int(pos)
    hi = min(len(values) - 1, lo + 1)
    frac = pos - lo
    return round(values[lo] * (1 - frac) + values[hi] * frac, 4)


def digest(payload: dict[str, Any]) -> str:
    clean = {k: v for k, v in payload.items() if k != "artifact_sha256"}
    encoded = json.dumps(clean, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def request_once(url: str, timeout: float) -> tuple[float, bool, int | None]:
    start = time.perf_counter_ns()
    status = None
    ok = False
    try:
        req = urllib.request.Request(url, method="GET", headers={"User-Agent": "DataVision-Performance-Evidence/1"})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            status = int(response.status)
            response.read(64)
            ok = 200 <= status < 400
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
    except Exception:
        pass
    latency = (time.perf_counter_ns() - start) / 1_000_000.0
    return latency, ok, status


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate DataVision external load/SLO evidence")
    parser.add_argument("--target", required=True, help="HTTPS endpoint to benchmark, e.g. https://host/ready")
    parser.add_argument("--duration", type=float, default=30.0)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--max-requests", type=int, default=5000)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--profile", default="production_standard")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    duration = max(1.0, args.duration)
    concurrency = max(1, min(args.concurrency, 200))
    max_requests = max(1, args.max_requests)
    started = datetime.now(timezone.utc).isoformat()
    started_perf = time.perf_counter()
    latencies: list[float] = []
    successes = 0
    status_counts: dict[str, int] = {}
    submitted = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        active: set[concurrent.futures.Future] = set()
        while (time.perf_counter() - started_perf) < duration and submitted < max_requests:
            while len(active) < concurrency and submitted < max_requests and (time.perf_counter() - started_perf) < duration:
                active.add(pool.submit(request_once, args.target, args.timeout))
                submitted += 1
            if not active:
                break
            done, active = concurrent.futures.wait(active, timeout=0.1, return_when=concurrent.futures.FIRST_COMPLETED)
            for future in done:
                latency, ok, status = future.result()
                latencies.append(latency)
                successes += int(ok)
                key = str(status) if status is not None else "network_error"
                status_counts[key] = status_counts.get(key, 0) + 1
        for future in concurrent.futures.as_completed(active):
            latency, ok, status = future.result()
            latencies.append(latency)
            successes += int(ok)
            key = str(status) if status is not None else "network_error"
            status_counts[key] = status_counts.get(key, 0) + 1

    elapsed = max(time.perf_counter() - started_perf, 0.000001)
    total = len(latencies)
    metrics = {
        "request_p50_ms": percentile(latencies, 0.50),
        "request_p95_ms": percentile(latencies, 0.95),
        "request_p99_ms": percentile(latencies, 0.99),
        "request_mean_ms": round(statistics.mean(latencies), 4) if latencies else None,
        "error_rate_pct": round((total - successes) * 100.0 / max(total, 1), 4),
        "throughput_rps": round(total / elapsed, 4),
        "total_requests": total,
        "successful_requests": successes,
    }
    payload = {
        "schema": SCHEMA,
        "product_version": (ROOT / "VERSION").read_text(encoding="utf-8").strip(),
        "profile": args.profile,
        "execution_context": "production",
        "target": args.target,
        "started_at": started,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "metrics": metrics,
        "runner": {
            "kind": "http_threadpool",
            "duration_seconds": round(elapsed, 3),
            "concurrency": concurrency,
            "max_requests": max_requests,
            "timeout_seconds": args.timeout,
            "status_counts": status_counts,
        },
        "environment": {
            "hostname": socket.gethostname(),
            "python": platform.python_version(),
            "platform": platform.platform(),
            "machine": platform.machine(),
        },
        "note": "Raw external target evidence. Import into DataVision to evaluate against the governed performance policy.",
    }
    payload["artifact_sha256"] = digest(payload)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "sha256": payload["artifact_sha256"], "metrics": metrics}, ensure_ascii=False))
    return 0 if total else 2


if __name__ == "__main__":
    raise SystemExit(main())
