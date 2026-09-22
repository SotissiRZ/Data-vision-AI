from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np

from app.core.config import get_settings
from app.services.semantic_layer import get_semantic_model, query_semantic_metric
from app.services.storage import get_meta


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _root_id(dataset_id: str) -> str:
    meta = get_meta(dataset_id)
    return str(meta.get("root_id") or meta["id"])


def _base_dir(dataset_id: str) -> Path:
    path = get_settings().data_root / "proactive" / _root_id(dataset_id)
    path.mkdir(parents=True, exist_ok=True)
    (path / "alerts").mkdir(parents=True, exist_ok=True)
    return path


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)


def _watches_path(dataset_id: str) -> Path:
    return _base_dir(dataset_id) / "watches.json"


def _scan_state_path(dataset_id: str) -> Path:
    return _base_dir(dataset_id) / "scan_state.json"


def list_watches(dataset_id: str) -> list[dict[str, Any]]:
    rows = _read_json(_watches_path(dataset_id), [])
    return rows if isinstance(rows, list) else []


def _save_watches(dataset_id: str, rows: list[dict[str, Any]]) -> None:
    _write_json(_watches_path(dataset_id), rows)


def _date_dimensions(model: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for d in model.get("dimensions", []):
        if d.get("hidden"):
            continue
        kind = str(d.get("kind") or "").lower()
        name = f"{d.get('id','')} {d.get('column','')} {d.get('label','')}".lower()
        if kind in {"date", "datetime", "time"} or any(x in name for x in ("date", "time", "jour", "mois", "month", "year", "annee", "année")):
            out.append(d)
    out.sort(key=lambda d: (not bool(d.get("certified")), str(d.get("id"))))
    return out


def _certified_metrics(model: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [m for m in model.get("metrics", []) if m.get("certified")]
    return rows or list(model.get("metrics", []))


def _validate_watch(dataset_id: str, df, watch: dict[str, Any]) -> dict[str, Any]:
    model = get_semantic_model(dataset_id, df)
    metric_ids = {str(m.get("id")) for m in model.get("metrics", [])}
    dim_ids = {str(d.get("id")) for d in model.get("dimensions", [])}
    metric_id = str(watch.get("metric_id") or "")
    date_dimension = str(watch.get("date_dimension") or "")
    if metric_id not in metric_ids:
        raise ValueError(f"Métrique inconnue pour la surveillance: {metric_id}")
    if not date_dimension or date_dimension not in dim_ids:
        raise ValueError(f"Dimension temporelle inconnue pour la surveillance: {date_dimension}")
    grain = str(watch.get("time_grain") or "month")
    if grain not in {"day", "week", "month", "quarter", "year"}:
        raise ValueError("Granularité temporelle invalide")
    direction = str(watch.get("direction") or "both")
    if direction not in {"both", "up", "down"}:
        raise ValueError("Direction de surveillance invalide")
    return {
        **watch,
        "metric_id": metric_id,
        "date_dimension": date_dimension,
        "time_grain": grain,
        "direction": direction,
        "threshold_pct": float(watch.get("threshold_pct", 10.0)),
        "anomaly_z_threshold": float(watch.get("anomaly_z_threshold", 2.5)),
        "min_history": max(3, int(watch.get("min_history", 4))),
        "filters": list(watch.get("filters") or []),
        "enabled": bool(watch.get("enabled", True)),
    }


def save_watch(dataset_id: str, df, payload: dict[str, Any]) -> dict[str, Any]:
    watch = _validate_watch(dataset_id, df, payload)
    rows = list_watches(dataset_id)
    now = _now()
    watch_id = str(watch.get("id") or uuid4())
    existing = next((x for x in rows if x.get("id") == watch_id), None)
    item = {
        "id": watch_id,
        "name": str(watch.get("name") or f"Surveillance {watch['metric_id']}").strip(),
        "metric_id": watch["metric_id"],
        "date_dimension": watch["date_dimension"],
        "time_grain": watch["time_grain"],
        "direction": watch["direction"],
        "threshold_pct": watch["threshold_pct"],
        "anomaly_z_threshold": watch["anomaly_z_threshold"],
        "min_history": watch["min_history"],
        "filters": watch["filters"],
        "enabled": watch["enabled"],
        "created_at": (existing or {}).get("created_at") or now,
        "updated_at": now,
        "last_scanned_at": (existing or {}).get("last_scanned_at"),
        "last_status": (existing or {}).get("last_status"),
        "last_value": (existing or {}).get("last_value"),
        "last_period": (existing or {}).get("last_period"),
    }
    rows = [item if x.get("id") == watch_id else x for x in rows]
    if not existing:
        rows.append(item)
    _save_watches(dataset_id, rows)
    return item


def delete_watch(dataset_id: str, watch_id: str) -> None:
    rows = list_watches(dataset_id)
    after = [x for x in rows if x.get("id") != watch_id]
    if len(after) == len(rows):
        raise FileNotFoundError(watch_id)
    _save_watches(dataset_id, after)


def auto_configure_watches(dataset_id: str, df, threshold_pct: float = 10.0, time_grain: str = "month") -> list[dict[str, Any]]:
    model = get_semantic_model(dataset_id, df)
    dates = _date_dimensions(model)
    if not dates:
        return []
    date_dim = dates[0]
    existing = list_watches(dataset_id)
    by_key = {(x.get("metric_id"), x.get("date_dimension"), x.get("time_grain")): x for x in existing}
    created: list[dict[str, Any]] = []
    for metric in _certified_metrics(model):
        key = (metric.get("id"), date_dim.get("id"), time_grain)
        if key in by_key:
            created.append(by_key[key])
            continue
        created.append(save_watch(dataset_id, df, {
            "name": f"{metric.get('label') or metric.get('name') or metric.get('id')} · {time_grain}",
            "metric_id": metric.get("id"),
            "date_dimension": date_dim.get("id"),
            "time_grain": time_grain,
            "direction": "both",
            "threshold_pct": threshold_pct,
            "anomaly_z_threshold": 2.5,
            "min_history": 4,
            "enabled": True,
        }))
    return created


def _robust_z(latest: float, history: list[float]) -> float | None:
    if len(history) < 3:
        return None
    arr = np.asarray(history, dtype=float)
    med = float(np.median(arr))
    mad = float(np.median(np.abs(arr - med)))
    if mad > 1e-12:
        return (latest - med) / (1.4826 * mad)
    std = float(np.std(arr))
    if std > 1e-12:
        return (latest - float(np.mean(arr))) / std
    return None


def _pct_change(current: float, previous: float) -> float | None:
    if not math.isfinite(current) or not math.isfinite(previous) or abs(previous) <= 1e-12:
        return None
    return (current - previous) / abs(previous) * 100.0


def _severity(delta_pct: float | None, level_z: float | None, change_z: float | None, threshold_pct: float, z_threshold: float, direction: str) -> tuple[str | None, list[str]]:
    signals: list[str] = []
    dp = float(delta_pct) if delta_pct is not None else 0.0
    directional = direction == "both" or (direction == "up" and dp > 0) or (direction == "down" and dp < 0)
    change_ratio = abs(dp) / max(abs(float(threshold_pct)), 1e-9) if directional and delta_pct is not None else 0.0
    z_ratio = max(abs(level_z or 0.0), abs(change_z or 0.0)) / max(float(z_threshold), 1e-9)
    if change_ratio >= 1:
        signals.append("variation_threshold")
    if level_z is not None and abs(level_z) >= z_threshold:
        signals.append("level_anomaly")
    if change_z is not None and abs(change_z) >= z_threshold:
        signals.append("change_point")
    score = max(change_ratio, z_ratio)
    if score >= 1.75:
        return "critical", signals
    if score >= 1.0:
        return "high", signals
    if score >= 0.70:
        return "medium", signals
    return None, signals


def _alert_dir(dataset_id: str) -> Path:
    return _base_dir(dataset_id) / "alerts"


def _all_alerts(dataset_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in _alert_dir(dataset_id).glob("*.json"):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
            rows.append(item)
        except Exception:
            continue
    rows.sort(key=lambda x: (x.get("detected_at") or ""), reverse=True)
    return rows


def list_alerts(dataset_id: str, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    rows = _all_alerts(dataset_id)
    if status and status != "all":
        rows = [x for x in rows if x.get("status") == status]
    return rows[: max(1, min(int(limit), 500))]


def update_alert_status(dataset_id: str, alert_id: str, status: str) -> dict[str, Any]:
    if status not in {"open", "acknowledged", "dismissed", "resolved"}:
        raise ValueError("Statut d'alerte invalide")
    path = _alert_dir(dataset_id) / f"{alert_id}.json"
    if not path.exists():
        raise FileNotFoundError(alert_id)
    item = _read_json(path, {})
    item["status"] = status
    item["status_updated_at"] = _now()
    _write_json(path, item)
    return item


def _metric_label(model: dict[str, Any], metric_id: str) -> str:
    metric = next((m for m in model.get("metrics", []) if m.get("id") == metric_id), {})
    return str(metric.get("label") or metric.get("name") or metric_id)


def _investigations(model: dict[str, Any], metric_id: str) -> list[dict[str, Any]]:
    dims = [d for d in model.get("dimensions", []) if not d.get("hidden") and str(d.get("kind") or "").lower() not in {"date", "datetime", "time"}]
    dims.sort(key=lambda d: (not bool(d.get("certified")), str(d.get("label") or d.get("id"))))
    out = []
    for d in dims[:4]:
        out.append({
            "type": "semantic_breakdown",
            "metric_id": metric_id,
            "dimension_id": d.get("id"),
            "label": f"Décomposer par {d.get('label') or d.get('id')}",
            "reason": "Identifier les segments qui contribuent le plus au changement observé.",
        })
    out.append({"type": "quality_check", "label": "Vérifier la qualité des données", "reason": "Écarter un changement artificiel lié aux données manquantes, doublons ou types incohérents."})
    return out


def scan(dataset_id: str, df, watch_ids: list[str] | None = None, auto_configure: bool = True) -> dict[str, Any]:
    watches = list_watches(dataset_id)
    if not watches and auto_configure:
        watches = auto_configure_watches(dataset_id, df)
    selected = [w for w in watches if w.get("enabled") and (not watch_ids or w.get("id") in set(watch_ids))]
    model = get_semantic_model(dataset_id, df)
    existing = _all_alerts(dataset_id)
    fingerprints = {x.get("fingerprint") for x in existing}
    generated: list[dict[str, Any]] = []
    evaluations: list[dict[str, Any]] = []
    now = _now()

    for watch in selected:
        watch = _validate_watch(dataset_id, df, watch)
        try:
            q = query_semantic_metric(
                dataset_id, df, watch["metric_id"], dimensions=[], filters=watch.get("filters") or [], limit=1000,
                date_dimension=watch["date_dimension"], time_grain=watch["time_grain"], comparison="previous_period",
            )
            rows = [r for r in q.get("result", []) if r.get("value") is not None]
            rows.sort(key=lambda r: str(r.get(watch["date_dimension"]) or ""))
            if len(rows) < 2:
                evaluations.append({"watch_id": watch["id"], "status": "insufficient_history", "points": len(rows)})
                continue
            values = [float(r["value"]) for r in rows]
            latest, previous = values[-1], values[-2]
            delta_pct = _pct_change(latest, previous)
            history = values[:-1]
            level_z = _robust_z(latest, history)
            changes = [_pct_change(values[i], values[i-1]) for i in range(1, len(values))]
            clean_changes = [float(x) for x in changes[:-1] if x is not None]
            latest_change = changes[-1] if changes else None
            change_z = _robust_z(float(latest_change), clean_changes) if latest_change is not None and len(clean_changes) >= 3 else None
            severity, signals = _severity(delta_pct, level_z, change_z, watch["threshold_pct"], watch["anomaly_z_threshold"], watch["direction"])
            period = rows[-1].get(watch["date_dimension"])
            evaluation = {
                "watch_id": watch["id"], "metric_id": watch["metric_id"], "period": period,
                "value": latest, "previous_value": previous, "delta_pct": delta_pct,
                "level_z": level_z, "change_z": change_z, "severity": severity, "signals": signals,
                "points": len(rows), "status": "alert" if severity else "stable",
            }
            evaluations.append(evaluation)
            if severity:
                fingerprint = f"{watch['id']}::{period}"
                if fingerprint not in fingerprints:
                    metric_label = _metric_label(model, watch["metric_id"])
                    direction_word = "hausse" if (delta_pct or 0) > 0 else "baisse"
                    evidence_parts = []
                    if delta_pct is not None:
                        evidence_parts.append(f"{direction_word} de {abs(delta_pct):.1f}% vs période précédente")
                    if level_z is not None and abs(level_z) >= watch["anomaly_z_threshold"]:
                        evidence_parts.append(f"niveau atypique (z={level_z:.2f})")
                    if change_z is not None and abs(change_z) >= watch["anomaly_z_threshold"]:
                        evidence_parts.append(f"rupture de variation (z={change_z:.2f})")
                    alert = {
                        "id": str(uuid4()), "fingerprint": fingerprint, "dataset_id": dataset_id, "root_id": _root_id(dataset_id),
                        "watch_id": watch["id"], "metric_id": watch["metric_id"], "metric_label": metric_label,
                        "severity": severity, "status": "open", "signals": signals, "detected_at": now,
                        "period": period, "value": latest, "previous_value": previous, "delta_pct": delta_pct,
                        "level_z": level_z, "change_z": change_z,
                        "title": f"{metric_label} · changement à investiguer",
                        "statement": f"{metric_label} présente une {direction_word} inhabituelle sur la dernière période.",
                        "evidence": "; ".join(evidence_parts) or "Signal détecté par le moteur de surveillance.",
                        "trend": [{"period": r.get(watch["date_dimension"]), "value": r.get("value")} for r in rows[-12:]],
                        "investigations": _investigations(model, watch["metric_id"]),
                        "provenance": {
                            "engine": "deterministic_proactive_monitor_v1", "semantic_model_version": model.get("version"),
                            "time_grain": watch["time_grain"], "date_dimension": watch["date_dimension"],
                            "threshold_pct": watch["threshold_pct"], "anomaly_z_threshold": watch["anomaly_z_threshold"],
                            "calculation_policy": "deterministic_semantic_engine",
                        },
                    }
                    _write_json(_alert_dir(dataset_id) / f"{alert['id']}.json", alert)
                    generated.append(alert); fingerprints.add(fingerprint)
            # update watch state
            watches = [
                {**x, "last_scanned_at": now, "last_status": "alert" if severity else "stable", "last_value": latest, "last_period": period}
                if x.get("id") == watch["id"] else x for x in watches
            ]
        except Exception as exc:
            evaluations.append({"watch_id": watch.get("id"), "status": "failed", "error": str(exc)})
    _save_watches(dataset_id, watches)
    state = {"last_scan_at": now, "dataset_id": dataset_id, "evaluated": len(evaluations), "new_alerts": len(generated)}
    _write_json(_scan_state_path(dataset_id), state)
    return {**state, "evaluations": evaluations, "alerts": generated, "inbox": proactive_summary(dataset_id)}


def proactive_summary(dataset_id: str) -> dict[str, Any]:
    alerts = _all_alerts(dataset_id)
    watches = list_watches(dataset_id)
    open_alerts = [a for a in alerts if a.get("status") == "open"]
    severity_counts = {k: sum(1 for a in open_alerts if a.get("severity") == k) for k in ("critical", "high", "medium")}
    state = _read_json(_scan_state_path(dataset_id), {})
    latest = open_alerts[0] if open_alerts else None
    return {
        "watch_count": len(watches),
        "active_watches": sum(1 for w in watches if w.get("enabled")),
        "open_alerts": len(open_alerts),
        "severity": severity_counts,
        "last_scan_at": state.get("last_scan_at"),
        "latest_alert": latest,
        "status": "attention" if severity_counts["critical"] or severity_counts["high"] else "watch" if open_alerts else "clear",
        "engine": "deterministic_proactive_monitor_v1",
    }


# v2.78 governed proactive scheduling -------------------------------------------------
def save_scan_schedule(
    dataset_id: str,
    *,
    workspace_id: str | None,
    actor_id: str | None,
    enabled: bool = True,
    interval_minutes: int = 1440,
    watch_ids: list[str] | None = None,
    auto_configure: bool = True,
) -> dict[str, Any]:
    from app.services.metadata_store import execute, fetch_one, json_dumps, json_loads, utcnow

    interval = max(15, min(int(interval_minutes), 43200))
    now_dt = datetime.now(timezone.utc)
    now = now_dt.isoformat()
    next_run = (now_dt + timedelta(minutes=interval)).isoformat()
    execute(
        """INSERT INTO proactive_scan_schedules(
            dataset_id,workspace_id,enabled,interval_minutes,next_run_at,last_run_at,last_status,
            watch_ids_json,auto_configure,created_by,created_at,updated_at
        ) VALUES(:dataset,:workspace,:enabled,:interval,:next_run,NULL,NULL,:watch_ids,:auto_configure,:actor,:created,:updated)
        ON CONFLICT(dataset_id) DO UPDATE SET
            workspace_id=excluded.workspace_id,enabled=excluded.enabled,interval_minutes=excluded.interval_minutes,
            next_run_at=excluded.next_run_at,watch_ids_json=excluded.watch_ids_json,
            auto_configure=excluded.auto_configure,updated_at=excluded.updated_at""",
        {
            "dataset": dataset_id,
            "workspace": workspace_id,
            "enabled": 1 if enabled else 0,
            "interval": interval,
            "next_run": next_run,
            "watch_ids": json_dumps(list(watch_ids or [])),
            "auto_configure": 1 if auto_configure else 0,
            "actor": actor_id,
            "created": now,
            "updated": now,
        },
    )
    row = fetch_one("SELECT * FROM proactive_scan_schedules WHERE dataset_id=:dataset", {"dataset": dataset_id})
    if not row:
        raise RuntimeError("Impossible de persister la planification proactive")
    row["watch_ids"] = json_loads(row.pop("watch_ids_json"), [])
    row["enabled"] = bool(row.get("enabled"))
    row["auto_configure"] = bool(row.get("auto_configure"))
    return row


def get_scan_schedule(dataset_id: str) -> dict[str, Any] | None:
    from app.services.metadata_store import fetch_one, json_loads

    row = fetch_one("SELECT * FROM proactive_scan_schedules WHERE dataset_id=:dataset", {"dataset": dataset_id})
    if not row:
        return None
    row["watch_ids"] = json_loads(row.pop("watch_ids_json"), [])
    row["enabled"] = bool(row.get("enabled"))
    row["auto_configure"] = bool(row.get("auto_configure"))
    return row


def claim_due_scan_schedules(limit: int = 20) -> list[dict[str, Any]]:
    """Claim due schedules by moving next_run_at forward before enqueueing.

    The conditional UPDATE makes competing workers fail closed: only the worker that still
    sees the original due timestamp gets the schedule back.
    """
    from sqlalchemy import text
    from app.services.metadata_store import connection, json_loads, utcnow

    now_dt = datetime.now(timezone.utc)
    now = now_dt.isoformat()
    claimed: list[dict[str, Any]] = []
    with connection() as conn:
        rows = conn.execute(
            text(
                """SELECT * FROM proactive_scan_schedules
                   WHERE enabled=1 AND next_run_at<=:now
                   ORDER BY next_run_at ASC LIMIT :limit"""
            ),
            {"now": now, "limit": max(1, min(int(limit), 100))},
        ).mappings().all()
        for raw in rows:
            row = dict(raw)
            interval = max(15, int(row.get("interval_minutes") or 1440))
            next_run = (now_dt + timedelta(minutes=interval)).isoformat()
            result = conn.execute(
                text(
                    """UPDATE proactive_scan_schedules
                       SET next_run_at=:next_run,last_run_at=:last_run,last_status='claimed',updated_at=:updated
                       WHERE dataset_id=:dataset AND enabled=1 AND next_run_at=:expected"""
                ),
                {
                    "next_run": next_run,
                    "last_run": now,
                    "updated": now,
                    "dataset": row["dataset_id"],
                    "expected": row["next_run_at"],
                },
            )
            if int(result.rowcount or 0) == 1:
                row["next_run_at"] = next_run
                row["last_run_at"] = now
                row["last_status"] = "claimed"
                row["watch_ids"] = json_loads(row.pop("watch_ids_json"), [])
                row["enabled"] = True
                row["auto_configure"] = bool(row.get("auto_configure"))
                claimed.append(row)
    return claimed


def mark_scan_schedule_result(dataset_id: str, status: str) -> None:
    from app.services.metadata_store import execute, utcnow

    execute(
        "UPDATE proactive_scan_schedules SET last_status=:status,updated_at=:updated WHERE dataset_id=:dataset",
        {"status": str(status)[:80], "updated": utcnow(), "dataset": dataset_id},
    )
