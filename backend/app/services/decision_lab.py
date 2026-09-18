from __future__ import annotations

from typing import Any

import joblib
import numpy as np
import pandas as pd

from app.core.config import get_settings
from app.services.modeling import predict


def _load_payload(model_id: str) -> dict[str, Any]:
    path = get_settings().model_dir / f"{model_id}.joblib"
    if not path.exists():
        raise FileNotFoundError(model_id)
    return joblib.load(path)


def model_what_if(model_id: str, base_row: dict[str, Any], scenarios: list[dict[str, Any]]) -> dict[str, Any]:
    payload = _load_payload(model_id)
    features = list(payload.get("features") or [])
    missing = [c for c in features if c not in base_row]
    if missing:
        raise ValueError(f"Variables manquantes dans le scénario de référence: {missing}")
    rows = [dict(base_row)]
    names = ["Référence"]
    for i, scenario in enumerate(scenarios[:20]):
        row = dict(base_row)
        overrides = scenario.get("overrides") or {}
        for key, value in overrides.items():
            if key in features:
                row[key] = value
        rows.append(row)
        names.append(str(scenario.get("name") or f"Scénario {i+1}"))
    scored = predict(model_id, rows)
    task = payload.get("task")
    output = []
    base_prediction = scored["predictions"][0]
    for i, name in enumerate(names):
        item: dict[str, Any] = {"name": name, "prediction": scored["predictions"][i], "overrides": {} if i == 0 else scenarios[i-1].get("overrides", {})}
        if task == "regression":
            try:
                item["delta"] = float(item["prediction"]) - float(base_prediction)
                item["delta_pct"] = None if abs(float(base_prediction)) < 1e-12 else item["delta"] / abs(float(base_prediction)) * 100
            except Exception:
                pass
        elif "probabilities" in scored:
            probs = scored["probabilities"][i]
            item["probabilities"] = probs
            if i > 0:
                item["probability_delta"] = [float(a)-float(b) for a,b in zip(probs, scored["probabilities"][0])]
        output.append(item)
    return {
        "model_id": model_id,
        "task": task,
        "target": payload.get("target"),
        "features": features,
        "classes": scored.get("classes"),
        "scenarios": output,
        "warning": "Simulation contrefactuelle du modèle: elle décrit la réponse du modèle aux hypothèses fournies, pas un effet causal garanti.",
        "calculation_policy": "saved_model_inference",
    }


def sensitivity_curve(model_id: str, base_row: dict[str, Any], feature: str, values: list[Any]) -> dict[str, Any]:
    payload = _load_payload(model_id)
    features = list(payload.get("features") or [])
    if feature not in features:
        raise ValueError(f"Variable inconnue pour ce modèle: {feature}")
    rows=[]
    for value in values[:60]:
        row=dict(base_row); row[feature]=value; rows.append(row)
    scored=predict(model_id, rows)
    points=[]
    for i,value in enumerate(values[:60]):
        item={"value": value, "prediction": scored["predictions"][i]}
        if "probabilities" in scored: item["probabilities"]=scored["probabilities"][i]
        points.append(item)
    return {"model_id":model_id,"feature":feature,"task":payload.get("task"),"target":payload.get("target"),"classes":scored.get("classes"),"points":points,"calculation_policy":"saved_model_inference"}
