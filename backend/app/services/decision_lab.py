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



def _control_values(
    spec: dict[str, Any],
    baseline: Any,
) -> list[Any]:
    if isinstance(spec.get("values"), list):
        values = spec["values"][:20]
        return values

    if all(key in spec for key in ("min", "max")):
        minimum = float(spec["min"])
        maximum = float(spec["max"])
        steps = max(2, min(int(spec.get("steps", 5)), 12))
        return np.linspace(minimum, maximum, steps).tolist()

    return [baseline]


def optimize_scenarios(
    model_id: str,
    base_row: dict[str, Any],
    controls: dict[str, dict[str, Any]],
    *,
    objective: str = "maximize",
    target_value: float | None = None,
    desired_class: Any | None = None,
    max_candidates: int = 2000,
    max_results: int = 10,
) -> dict[str, Any]:
    payload = _load_payload(model_id)
    features = list(payload.get("features") or [])
    task = payload.get("task")

    missing = [feature for feature in features if feature not in base_row]
    if missing:
        raise ValueError(
            f"Variables manquantes dans la référence: {missing}"
        )

    usable = {
        feature: spec
        for feature, spec in controls.items()
        if feature in features and isinstance(spec, dict)
    }
    if not usable:
        raise ValueError(
            "Aucune variable de contrôle valide n'a été fournie."
        )
    if len(usable) > 5:
        raise ValueError(
            "Maximum 5 variables de contrôle par optimisation."
        )

    names = list(usable)
    grids = [
        _control_values(usable[name], base_row[name])
        for name in names
    ]

    combinations = []
    for values in __import__("itertools").product(*grids):
        row = dict(base_row)
        overrides = {}
        for name, value in zip(names, values):
            row[name] = value
            overrides[name] = value
        combinations.append((row, overrides))
        if len(combinations) >= max(10, min(int(max_candidates), 5000)):
            break

    rows = [row for row, _overrides in combinations]
    scored = predict(model_id, rows)
    predictions = scored["predictions"]

    classes = scored.get("classes") or []
    probabilities = scored.get("probabilities")
    desired_index = None

    if task == "classification":
        if not probabilities:
            raise ValueError(
                "Le modèle de classification ne fournit pas de probabilités."
            )
        if desired_class is None:
            baseline_scored = predict(model_id, [base_row])
            base_probs = baseline_scored.get("probabilities", [[]])[0]
            if len(classes) == 2:
                base_pred = baseline_scored["predictions"][0]
                desired_class = (
                    classes[1]
                    if base_pred == classes[0]
                    else classes[0]
                )
            else:
                order = np.argsort(np.asarray(base_probs))[::-1]
                desired_class = classes[int(order[0])]
        if desired_class not in classes:
            raise ValueError(
                f"Classe cible inconnue: {desired_class}"
            )
        desired_index = classes.index(desired_class)

    ranked = []
    for index, ((row, overrides), prediction) in enumerate(
        zip(combinations, predictions)
    ):
        if task == "regression":
            numeric = float(prediction)
            if objective == "maximize":
                score = numeric
                objective_distance = None
            elif objective == "minimize":
                score = -numeric
                objective_distance = None
            elif objective == "target":
                if target_value is None:
                    raise ValueError(
                        "target_value est requis pour objective='target'."
                    )
                objective_distance = abs(numeric - float(target_value))
                score = -objective_distance
            else:
                raise ValueError(
                    "objective doit être maximize, minimize ou target."
                )
            extra = {
                "prediction": round(numeric, 8),
                "objective_distance": (
                    None
                    if objective_distance is None
                    else round(float(objective_distance), 8)
                ),
            }
        else:
            assert probabilities is not None
            assert desired_index is not None
            probability = float(probabilities[index][desired_index])
            score = probability
            extra = {
                "prediction": prediction,
                "target_probability": round(probability, 8),
                "probabilities": [
                    round(float(value), 8)
                    for value in probabilities[index]
                ],
            }

        normalized_change = 0.0
        for feature, value in overrides.items():
            original = base_row[feature]
            try:
                denominator = max(abs(float(original)), 1.0)
                normalized_change += (
                    abs(float(value) - float(original)) / denominator
                )
            except Exception:
                normalized_change += 0.0 if value == original else 1.0

        ranked.append(
            {
                "score": round(float(score), 8),
                "change_cost": round(float(normalized_change), 8),
                "overrides": overrides,
                **extra,
            }
        )

    ranked.sort(
        key=lambda item: (
            -float(item["score"]),
            float(item["change_cost"]),
        )
    )

    baseline = predict(model_id, [base_row])
    return {
        "model_id": model_id,
        "task": task,
        "target": payload.get("target"),
        "objective": objective,
        "target_value": target_value,
        "desired_class": desired_class,
        "controls": usable,
        "searched_candidates": len(ranked),
        "baseline": {
            "prediction": baseline["predictions"][0],
            "probabilities": (
                baseline.get("probabilities", [None])[0]
                if baseline.get("probabilities")
                else None
            ),
        },
        "recommended_scenarios": ranked[
            : max(1, min(int(max_results), 20))
        ],
        "calculation_policy": (
            "bounded_saved_model_grid_search"
        ),
        "warning": (
            "Optimisation du comportement du modèle sauvegardé. "
            "Les scénarios ne constituent pas des recommandations causales "
            "ni une garantie de résultat réel."
        ),
    }
