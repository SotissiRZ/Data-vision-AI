#!/usr/bin/env python3
from __future__ import annotations

import argparse
import concurrent.futures
import json
import math
import statistics
import time
import urllib.error
import urllib.request
from pathlib import Path


def percentile(values: list[float], p: float) -> float:
    if not values:
        return math.inf
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, math.ceil((p / 100.0) * len(ordered)) - 1))
    return ordered[idx]


def hit(url: str, timeout: float) -> tuple[bool, float, str]:
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            response.read(256)
            ok = 200 <= response.status < 400
            status = str(response.status)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        ok = False
        status = type(exc).__name__
    return ok, (time.perf_counter() - start) * 1000.0, status


def main() -> int:
    ap = argparse.ArgumentParser(description="Small dependency-free HTTP load smoke for DataVision readiness endpoints.")
    ap.add_argument("--url", default="http://127.0.0.1:3005/api/health")
    ap.add_argument("--requests", type=int, default=60)
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--timeout", type=float, default=5.0)
    ap.add_argument("--max-p95-ms", type=float, default=1500.0)
    ap.add_argument("--max-error-rate", type=float, default=0.01)
    ap.add_argument("--json-out")
    args = ap.parse_args()

    total = max(1, min(args.requests, 5000))
    concurrency = max(1, min(args.concurrency, 128))
    started = time.perf_counter()
    rows: list[tuple[bool, float, str]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(hit, args.url, args.timeout) for _ in range(total)]
        for future in concurrent.futures.as_completed(futures):
            rows.append(future.result())
    elapsed = max(time.perf_counter() - started, 1e-9)
    latencies = [row[1] for row in rows]
    errors = sum(1 for row in rows if not row[0])
    error_rate = errors / total
    p95 = percentile(latencies, 95)
    passed = error_rate <= args.max_error_rate and p95 <= args.max_p95_ms
    result = {
        "schema": "datavision-load-smoke-v1",
        "status": "pass" if passed else "fail",
        "url": args.url,
        "requests": total,
        "concurrency": concurrency,
        "errors": errors,
        "error_rate": round(error_rate, 6),
        "latency_ms": {
            "mean": round(statistics.fmean(latencies), 3) if latencies else None,
            "p50": round(percentile(latencies, 50), 3),
            "p95": round(p95, 3),
            "max": round(max(latencies), 3) if latencies else None,
        },
        "throughput_rps": round(total / elapsed, 3),
        "thresholds": {"max_p95_ms": args.max_p95_ms, "max_error_rate": args.max_error_rate},
    }
    print(json.dumps(result, indent=2))
    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
