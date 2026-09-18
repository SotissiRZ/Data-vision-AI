from __future__ import annotations

import math
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.services.metadata_store import execute, fetch_all, fetch_one, json_dumps, json_loads, utcnow


FEATURE_RULES: list[tuple[str, str]] = [
    ("/ai/", "AI Analyst"),
    ("/workspace/nlq", "NLQ"),
    ("/workspace/sql", "SQL Workspace"),
    ("/semantic", "Semantic Layer"),
    ("/dashboards", "Dashboards"),
    ("/reports", "Reports"),
    ("/models/automl", "AutoML"),
    ("/models/", "Models & XAI"),
    ("/forecast", "Forecasting"),
    ("/analysis/", "Statistical Analysis"),
    ("/visualizations", "Visualization Studio"),
    ("/proactive/", "Proactive Intelligence"),
    ("/contracts", "Data Reliability"),
    ("/lineage", "Lineage"),
    ("/connectors", "Connectors"),
    ("/sources", "Sources & Refresh"),
    ("/reviews", "Collaboration & Review"),
    ("/jobs", "Background Jobs"),
    ("/operational", "Operational Intelligence"),
    ("/evaluations", "AI Evaluation"),
    ("/actions", "Governed Actions"),
]


def feature_for_path(path: str) -> str:
    for token, label in FEATURE_RULES:
        if token in path:
            return label
    if "/datasets" in path:
        return "Data Workspace"
    if "/workspaces" in path:
        return "Governance"
    if "/auth/" in path:
        return "Authentication"
    return "Platform"


def record_telemetry(
    *,
    event_kind: str,
    name: str,
    status: str,
    workspace_id: str | None = None,
    organization_id: str | None = None,
    user_id: str | None = None,
    feature: str | None = None,
    latency_ms: float | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    estimated_cost_usd: float | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    event_id = str(uuid.uuid4())
    execute(
        """INSERT INTO telemetry_events(
            id,organization_id,workspace_id,user_id,event_kind,feature,name,status,latency_ms,input_tokens,output_tokens,
            estimated_cost_usd,resource_type,resource_id,metadata_json,created_at
        ) VALUES(:id,:org,:ws,:user,:kind,:feature,:name,:status,:latency,:input_tokens,:output_tokens,:cost,:rtype,:rid,:metadata,:created)""",
        {
            "id": event_id,
            "org": organization_id,
            "ws": workspace_id,
            "user": user_id,
            "kind": event_kind,
            "feature": feature,
            "name": name,
            "status": status,
            "latency": latency_ms,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost": estimated_cost_usd,
            "rtype": resource_type,
            "rid": resource_id,
            "metadata": json_dumps(metadata or {}),
            "created": utcnow(),
        },
    )
    return event_id


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    xs = sorted(float(x) for x in values)
    if len(xs) == 1:
        return round(xs[0], 2)
    pos = (len(xs) - 1) * pct
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return round(xs[lo], 2)
    value = xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)
    return round(value, 2)


def _since(hours: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=max(1, min(hours, 24 * 90)))).isoformat()


def list_telemetry(workspace_id: str, *, hours: int = 24, limit: int = 200, event_kind: str | None = None) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"ws": workspace_id, "since": _since(hours), "limit": max(1, min(limit, 1000))}
    where = "workspace_id=:ws AND created_at>=:since"
    if event_kind:
        where += " AND event_kind=:kind"
        params["kind"] = event_kind
    rows = fetch_all(f"SELECT * FROM telemetry_events WHERE {where} ORDER BY created_at DESC LIMIT :limit", params)
    for row in rows:
        row["metadata"] = json_loads(row.pop("metadata_json", "{}"), {})
    return rows


def feature_usage(workspace_id: str, *, hours: int = 24 * 30) -> dict[str, Any]:
    rows = fetch_all(
        """SELECT feature,COUNT(*) AS uses,COUNT(DISTINCT user_id) AS users,
                  AVG(latency_ms) AS avg_latency_ms,
                  SUM(CASE WHEN status LIKE '2%' OR status LIKE '3%' OR status IN ('ok','success','completed') THEN 0 ELSE 1 END) AS errors
           FROM telemetry_events
           WHERE workspace_id=:ws AND created_at>=:since AND feature IS NOT NULL
           GROUP BY feature ORDER BY uses DESC""",
        {"ws": workspace_id, "since": _since(hours)},
    )
    total = sum(int(r.get("uses") or 0) for r in rows)
    for row in rows:
        row["uses"] = int(row.get("uses") or 0)
        row["users"] = int(row.get("users") or 0)
        row["errors"] = int(row.get("errors") or 0)
        row["share_pct"] = round(100.0 * row["uses"] / total, 2) if total else 0.0
        if row.get("avg_latency_ms") is not None:
            row["avg_latency_ms"] = round(float(row["avg_latency_ms"]), 2)
    return {"window_hours": hours, "total_events": total, "features": rows}


def job_attempts(job_id: str) -> list[dict[str, Any]]:
    return fetch_all("SELECT * FROM job_attempts WHERE job_id=:job ORDER BY attempt_number", {"job": job_id})


def operational_overview(workspace_id: str, *, hours: int = 24) -> dict[str, Any]:
    since = _since(hours)
    api_rows = fetch_all(
        "SELECT status,latency_ms FROM telemetry_events WHERE workspace_id=:ws AND event_kind='http' AND created_at>=:since",
        {"ws": workspace_id, "since": since},
    )
    latencies = [float(r["latency_ms"]) for r in api_rows if r.get("latency_ms") is not None]
    api_total = len(api_rows)
    api_ok = sum(1 for r in api_rows if str(r.get("status", "")).startswith(("2", "3")) or r.get("status") in {"ok", "success"})
    api_availability = round(100.0 * api_ok / api_total, 3) if api_total else None

    jobs = fetch_all(
        "SELECT status,job_type,created_at,started_at,finished_at FROM jobs WHERE workspace_id=:ws AND created_at>=:since",
        {"ws": workspace_id, "since": since},
    )
    terminal = [j for j in jobs if j.get("status") in {"completed", "failed", "cancelled"}]
    completed = sum(1 for j in terminal if j.get("status") == "completed")
    job_success = round(100.0 * completed / len(terminal), 2) if terminal else None
    retrying = sum(1 for j in jobs if j.get("status") == "retry_wait")

    refresh = fetch_all(
        "SELECT status FROM refresh_runs WHERE workspace_id=:ws AND started_at>=:since",
        {"ws": workspace_id, "since": since},
    )
    refresh_success = round(100.0 * sum(1 for r in refresh if r.get("status") == "completed") / len(refresh), 2) if refresh else None

    ai = fetch_one(
        """SELECT COALESCE(SUM(input_tokens),0) AS input_tokens,COALESCE(SUM(output_tokens),0) AS output_tokens,
                  COALESCE(SUM(estimated_cost_usd),0) AS cost
           FROM telemetry_events WHERE workspace_id=:ws AND event_kind='ai' AND created_at>=:since""",
        {"ws": workspace_id, "since": since},
    ) or {}
    eval_latest = fetch_one(
        "SELECT id,score,status,cases_total,cases_passed,cases_failed,created_at FROM evaluation_runs WHERE workspace_id=:ws ORDER BY created_at DESC LIMIT 1",
        {"ws": workspace_id},
    )
    usage = feature_usage(workspace_id, hours=hours)

    p95 = _percentile(latencies, 0.95)
    slo = {
        "api_availability": {"value": api_availability, "target": 99.0, "unit": "%", "met": api_availability is None or api_availability >= 99.0},
        "api_p95_latency": {"value": p95, "target": 750.0, "unit": "ms", "met": p95 is None or p95 <= 750.0},
        "job_success": {"value": job_success, "target": 95.0, "unit": "%", "met": job_success is None or job_success >= 95.0},
        "refresh_success": {"value": refresh_success, "target": 95.0, "unit": "%", "met": refresh_success is None or refresh_success >= 95.0},
    }
    met = sum(1 for x in slo.values() if x["met"])
    return {
        "window_hours": hours,
        "api": {"requests": api_total, "availability_pct": api_availability, "p50_latency_ms": _percentile(latencies, 0.50), "p95_latency_ms": p95, "p99_latency_ms": _percentile(latencies, 0.99)},
        "jobs": {"total": len(jobs), "terminal": len(terminal), "success_rate_pct": job_success, "retry_wait": retrying},
        "refresh": {"runs": len(refresh), "success_rate_pct": refresh_success},
        "ai_usage": {"input_tokens": int(ai.get("input_tokens") or 0), "output_tokens": int(ai.get("output_tokens") or 0), "estimated_cost_usd": round(float(ai.get("cost") or 0), 6), "note": "0 signifie qu'aucun fournisseur LLM instrumenté n'a reporté de tokens/coût."},
        "evaluation": eval_latest,
        "slo": {"status": "healthy" if met == len(slo) else "attention", "met": met, "total": len(slo), "indicators": slo},
        "top_features": usage["features"][:8],
    }


def create_evaluation_suite(user_id: str, workspace_id: str, dataset_id: str, name: str, description: str = "") -> dict[str, Any]:
    suite_id = str(uuid.uuid4())
    now = utcnow()
    execute(
        "INSERT INTO evaluation_suites(id,workspace_id,dataset_id,name,description,created_by,created_at,updated_at) VALUES(:id,:ws,:ds,:name,:description,:user,:now,:now)",
        {"id": suite_id, "ws": workspace_id, "ds": dataset_id, "name": name.strip(), "description": description.strip(), "user": user_id, "now": now},
    )
    return get_evaluation_suite(workspace_id, suite_id)


def list_evaluation_suites(workspace_id: str) -> list[dict[str, Any]]:
    rows = fetch_all(
        """SELECT s.*,COUNT(c.id) AS cases_count
           FROM evaluation_suites s LEFT JOIN evaluation_cases c ON c.suite_id=s.id AND c.enabled=1
           WHERE s.workspace_id=:ws GROUP BY s.id,s.workspace_id,s.dataset_id,s.name,s.description,s.created_by,s.created_at,s.updated_at
           ORDER BY s.updated_at DESC""",
        {"ws": workspace_id},
    )
    return rows


def get_evaluation_suite(workspace_id: str, suite_id: str) -> dict[str, Any]:
    suite = fetch_one("SELECT * FROM evaluation_suites WHERE id=:id AND workspace_id=:ws", {"id": suite_id, "ws": workspace_id})
    if not suite:
        raise KeyError("Suite d'évaluation introuvable")
    cases = fetch_all("SELECT * FROM evaluation_cases WHERE suite_id=:id AND workspace_id=:ws ORDER BY created_at", {"id": suite_id, "ws": workspace_id})
    for case in cases:
        case["expectations"] = json_loads(case.pop("expectations_json", "{}"), {})
        case["enabled"] = bool(case.get("enabled"))
    suite["cases"] = cases
    latest = fetch_one("SELECT * FROM evaluation_runs WHERE suite_id=:id ORDER BY created_at DESC LIMIT 1", {"id": suite_id})
    suite["latest_run"] = latest
    return suite


def add_evaluation_case(user_id: str, workspace_id: str, suite_id: str, question: str, expectations: dict[str, Any]) -> dict[str, Any]:
    _ = get_evaluation_suite(workspace_id, suite_id)
    case_id = str(uuid.uuid4())
    now = utcnow()
    execute(
        "INSERT INTO evaluation_cases(id,suite_id,workspace_id,question,expectations_json,enabled,created_by,created_at,updated_at) VALUES(:id,:suite,:ws,:q,:e,1,:user,:now,:now)",
        {"id": case_id, "suite": suite_id, "ws": workspace_id, "q": question.strip(), "e": json_dumps(expectations or {}), "user": user_id, "now": now},
    )
    return next(c for c in get_evaluation_suite(workspace_id, suite_id)["cases"] if c["id"] == case_id)


def _value_at_path(value: Any, path: str) -> Any:
    current = value
    for part in [p for p in path.split(".") if p]:
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit():
            idx = int(part)
            current = current[idx] if 0 <= idx < len(current) else None
        else:
            return None
    return current


def _evaluate_result(result: dict[str, Any], expectations: dict[str, Any], duration_ms: float) -> tuple[list[dict[str, Any]], float, bool]:
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, actual: Any, expected: Any) -> None:
        checks.append({"name": name, "passed": bool(passed), "actual": actual, "expected": expected})

    if expectations.get("expected_intent"):
        exp = expectations["expected_intent"]
        add("intent", result.get("intent") == exp, result.get("intent"), exp)
    if expectations.get("critic_status"):
        exp = expectations["critic_status"]
        actual = (result.get("critic") or {}).get("status")
        add("critic_status", actual == exp, actual, exp)
    required_tools = list(expectations.get("required_tools") or [])
    if required_tools:
        actual_tools = [x.get("tool") for x in result.get("executions", []) if x.get("status") == "ok"]
        add("required_tools", all(t in actual_tools for t in required_tools), actual_tools, required_tools)
    contains = list(expectations.get("answer_contains") or [])
    if contains:
        answer = str(result.get("answer") or "").lower()
        add("answer_contains", all(str(x).lower() in answer for x in contains), result.get("answer"), contains)
    if expectations.get("min_findings") is not None:
        exp = int(expectations["min_findings"])
        actual = len(result.get("findings") or [])
        add("min_findings", actual >= exp, actual, f">={exp}")
    if expectations.get("max_duration_ms") is not None:
        exp = float(expectations["max_duration_ms"])
        add("max_duration_ms", duration_ms <= exp, round(duration_ms, 2), exp)
    path = expectations.get("expected_value_path")
    if path:
        actual = _value_at_path(result, str(path))
        expected = expectations.get("expected_value")
        tolerance = float(expectations.get("tolerance") or 0.0)
        if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
            passed = abs(float(actual) - float(expected)) <= tolerance
        else:
            passed = actual == expected
        add("expected_value", passed, actual, {"value": expected, "tolerance": tolerance, "path": path})
    if not checks:
        add("execution", bool(result.get("critic")), result.get("critic", {}).get("status"), "result produced")
    passed_count = sum(1 for c in checks if c["passed"])
    score = round(100.0 * passed_count / len(checks), 2)
    return checks, score, passed_count == len(checks)


def run_evaluation_suite(user_id: str, workspace_id: str, suite_id: str) -> dict[str, Any]:
    from app.services.ai_analyst import AnalystContext, analyze_dataset
    from app.services.semantic_layer import get_semantic_model
    from app.services.storage import get_meta, load_dataframe
    from app.services.tenant_access import authorize_dataset, context_for_job, reset_access_context, set_access_context

    suite = get_evaluation_suite(workspace_id, suite_id)
    dataset_id = suite["dataset_id"]
    ctx = context_for_job(user_id, workspace_id)
    if ctx:
        authorize_dataset(dataset_id, "analysis:run", ctx)
    token = set_access_context(ctx)
    run_id = str(uuid.uuid4())
    started = time.perf_counter()
    results: list[dict[str, Any]] = []
    try:
        df = load_dataframe(dataset_id)
        meta = get_meta(dataset_id)
        dataset = {
            "id": meta["id"], "name": meta["original_name"], "format": meta["extension"],
            "version": meta.get("version", 1), "parent_id": meta.get("parent_id"),
            "root_id": meta.get("root_id", meta["id"]), "operation": meta.get("operation"),
        }
        semantic = get_semantic_model(dataset_id, df)
        cases = [c for c in suite["cases"] if c.get("enabled")]
        for case in cases:
            case_started = time.perf_counter()
            error: str | None = None
            result: dict[str, Any] = {}
            try:
                result = analyze_dataset(df, AnalystContext(dataset=dataset, question=case["question"], mode="auto", semantic_model=semantic))
            except Exception as exc:
                error = str(exc)
            duration = (time.perf_counter() - case_started) * 1000.0
            if error:
                checks = [{"name": "execution", "passed": False, "actual": error, "expected": "successful execution"}]
                score = 0.0
                passed = False
                snapshot = {"error": error}
            else:
                checks, score, passed = _evaluate_result(result, case.get("expectations") or {}, duration)
                snapshot = {
                    "intent": result.get("intent"),
                    "critic": result.get("critic"),
                    "answer": result.get("answer"),
                    "executions": result.get("executions", []),
                    "provenance": result.get("provenance", {}),
                }
            row_id = str(uuid.uuid4())
            execute(
                "INSERT INTO evaluation_results(id,run_id,case_id,workspace_id,status,score,duration_ms,checks_json,result_snapshot_json,created_at) VALUES(:id,:run,:case,:ws,:status,:score,:duration,:checks,:snapshot,:created)",
                {"id": row_id, "run": run_id, "case": case["id"], "ws": workspace_id, "status": "passed" if passed else "failed", "score": score, "duration": duration, "checks": json_dumps(checks), "snapshot": json_dumps(snapshot), "created": utcnow()},
            )
            results.append({"id": row_id, "case_id": case["id"], "question": case["question"], "status": "passed" if passed else "failed", "score": score, "duration_ms": round(duration, 2), "checks": checks, "result": snapshot})
        passed_cases = sum(1 for x in results if x["status"] == "passed")
        total = len(results)
        total_duration = (time.perf_counter() - started) * 1000.0
        score = round(sum(float(x["score"]) for x in results) / total, 2) if total else 0.0
        status = "passed" if total and passed_cases == total else "failed"
        execute(
            "INSERT INTO evaluation_runs(id,suite_id,workspace_id,dataset_id,status,score,cases_total,cases_passed,cases_failed,duration_ms,triggered_by,created_at) VALUES(:id,:suite,:ws,:ds,:status,:score,:total,:passed,:failed,:duration,:user,:created)",
            {"id": run_id, "suite": suite_id, "ws": workspace_id, "ds": dataset_id, "status": status, "score": score, "total": total, "passed": passed_cases, "failed": total-passed_cases, "duration": total_duration, "user": user_id, "created": utcnow()},
        )
        record_telemetry(event_kind="evaluation", name="ai_analyst_suite", status=status, workspace_id=workspace_id, user_id=user_id, feature="AI Evaluation", latency_ms=total_duration, resource_type="evaluation_suite", resource_id=suite_id, metadata={"run_id": run_id, "score": score, "cases": total})
        return {"id": run_id, "suite_id": suite_id, "dataset_id": dataset_id, "status": status, "score": score, "cases_total": total, "cases_passed": passed_cases, "cases_failed": total-passed_cases, "duration_ms": round(total_duration, 2), "results": results, "created_at": utcnow()}
    finally:
        reset_access_context(token)


def list_evaluation_runs(workspace_id: str, suite_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"ws": workspace_id, "limit": max(1, min(limit, 200))}
    where = "workspace_id=:ws"
    if suite_id:
        where += " AND suite_id=:suite"
        params["suite"] = suite_id
    return fetch_all(f"SELECT * FROM evaluation_runs WHERE {where} ORDER BY created_at DESC LIMIT :limit", params)


def get_evaluation_run(workspace_id: str, run_id: str) -> dict[str, Any]:
    run = fetch_one("SELECT * FROM evaluation_runs WHERE id=:id AND workspace_id=:ws", {"id": run_id, "ws": workspace_id})
    if not run:
        raise KeyError("Run d'évaluation introuvable")
    rows = fetch_all("SELECT * FROM evaluation_results WHERE run_id=:run AND workspace_id=:ws ORDER BY created_at", {"run": run_id, "ws": workspace_id})
    for row in rows:
        row["checks"] = json_loads(row.pop("checks_json", "[]"), [])
        row["result"] = json_loads(row.pop("result_snapshot_json", "{}"), {})
    run["results"] = rows
    return run
