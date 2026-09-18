import io
import pandas as pd
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_upload_profile_quality(tmp_path, monkeypatch):
    from app.core.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)
    csv = b"age,group,target\n20,A,0\n21,A,0\n, B,1\n40,B,1\n40,B,1\n"
    r = client.post("/api/v1/datasets", files={"file": ("sample.csv", io.BytesIO(csv), "text/csv")})
    assert r.status_code == 200
    dataset_id = r.json()["dataset"]["id"]
    p = client.get(f"/api/v1/datasets/{dataset_id}/profile")
    q = client.get(f"/api/v1/datasets/{dataset_id}/quality")
    assert p.status_code == 200
    assert p.json()["rows"] == 5
    assert q.status_code == 200
    assert q.json()["issues_count"] >= 1


def _advanced_dataset_bytes():
    import numpy as np
    rng = np.random.default_rng(7)
    n = 120
    age = rng.integers(20, 70, n)
    group = rng.choice(["Leger", "Modere", "Severe"], n)
    sex = rng.choice(["F", "M"], n)
    fatigue = 30 + (group == "Severe") * 18 + rng.normal(0, 5, n)
    memory = 110 - 0.25 * age - (group == "Severe") * 13 - 0.22 * fatigue + rng.normal(0, 4, n)
    reaction = 250 + 1.8 * age + (group == "Severe") * 45 + rng.normal(0, 15, n)
    frame = pd.DataFrame({"Age": age, "Sexe": sex, "Severite": group, "Score_Memoire": memory, "Temps_Reaction": reaction, "Score_Fatigue": fatigue})
    return frame.to_csv(index=False).encode("utf-8")


def test_advanced_analytics_endpoints(tmp_path, monkeypatch):
    from app.core.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)
    r = client.post("/api/v1/datasets", files={"file": ("advanced.csv", io.BytesIO(_advanced_dataset_bytes()), "text/csv")})
    assert r.status_code == 200
    dataset_id = r.json()["dataset"]["id"]

    reg = client.post(f"/api/v1/datasets/{dataset_id}/analysis/regression", json={"dependent": "Score_Memoire", "independents": ["Age", "Score_Fatigue", "Severite"]})
    assert reg.status_code == 200, reg.text
    assert reg.json()["r_squared"] > 0.3
    assert len(reg.json()["coefficients"]) >= 3

    a1 = client.post(f"/api/v1/datasets/{dataset_id}/analysis/anova", json={"response": "Score_Memoire", "factor1": "Severite"})
    assert a1.status_code == 200, a1.text
    assert a1.json()["type"] == "one_way"
    assert len(a1.json()["groups"]) == 3

    a2 = client.post(f"/api/v1/datasets/{dataset_id}/analysis/anova", json={"response": "Score_Memoire", "factor1": "Severite", "factor2": "Sexe"})
    assert a2.status_code == 200, a2.text
    assert a2.json()["type"] == "two_way"

    pca = client.post(f"/api/v1/datasets/{dataset_id}/analysis/pca", json={"columns": ["Age", "Score_Memoire", "Temps_Reaction", "Score_Fatigue"], "scale": True})
    assert pca.status_code == 200, pca.text
    assert len(pca.json()["variance"]) == 4

    clu = client.post(f"/api/v1/datasets/{dataset_id}/analysis/clustering", json={"columns": ["Age", "Score_Memoire", "Temps_Reaction", "Score_Fatigue"], "k": 3})
    assert clu.status_code == 200, clu.text
    assert len(clu.json()["profiles"]) == 3
    assert len(clu.json()["comparison"]) >= 2


def test_data_preparation_versioning_and_rollback(tmp_path, monkeypatch):
    from app.core.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)
    csv = b"age,group,score\n20,A,10\n21,A,\n21,A,12\n40,B,99\n40,B,99\n"
    r = client.post("/api/v1/datasets", files={"file": ("prep.csv", io.BytesIO(csv), "text/csv")})
    assert r.status_code == 200
    v1 = r.json()["dataset"]["id"]

    t1 = client.post(f"/api/v1/datasets/{v1}/transform", json={"operation": {"type": "fill_missing", "column": "score", "strategy": "median"}})
    assert t1.status_code == 200, t1.text
    v2 = t1.json()["dataset"]["id"]
    assert t1.json()["dataset"]["version"] == 2
    assert t1.json()["profile"]["columns_count"] == 3

    t2 = client.post(f"/api/v1/datasets/{v2}/transform", json={"operation": {"type": "remove_duplicates", "subset": []}})
    assert t2.status_code == 200, t2.text
    v3 = t2.json()["dataset"]["id"]
    assert t2.json()["dataset"]["version"] == 3
    assert t2.json()["profile"]["rows"] == 4

    versions = client.get(f"/api/v1/datasets/{v3}/versions")
    assert versions.status_code == 200
    assert [x["version"] for x in versions.json()["versions"]] == [1, 2, 3]

    # Rollback is non-destructive: simply reactivate an immutable previous version.
    old_preview = client.get(f"/api/v1/datasets/{v1}/preview")
    assert old_preview.status_code == 200
    assert old_preview.json()["total"] == 5


def test_preparation_operations_unit():
    from app.services.preparation import apply_operation
    frame = pd.DataFrame({
        "age": [20, 21, 22, 80],
        "score": [1.0, None, 3.0, 100.0],
        "group": ["A", "A", "B", "B"],
    })
    filled, _ = apply_operation(frame, {"type": "fill_missing", "column": "score", "strategy": "median"})
    assert filled["score"].isna().sum() == 0
    renamed, _ = apply_operation(filled, {"type": "rename_column", "column": "group", "new_name": "segment"})
    assert "segment" in renamed.columns and "group" not in renamed.columns
    filtered, _ = apply_operation(renamed, {"type": "filter_rows", "column": "age", "operator": "gte", "value": 21})
    assert filtered["age"].min() >= 21
    clipped, meta = apply_operation(filtered, {"type": "clip_outliers_iqr", "column": "score", "factor": 1.5, "mode": "clip"})
    assert meta["type"] == "clip_outliers_iqr"
    normalized, _ = apply_operation(clipped, {"type": "normalize_minmax", "columns": ["age"]})
    assert float(normalized["age"].min()) == 0.0
    assert float(normalized["age"].max()) == 1.0


def test_advanced_preparation_feature_engineering_and_shapes(tmp_path, monkeypatch):
    from app.core.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)
    frame = pd.DataFrame({
        "region": ["N", "N", "S", "S"],
        "segment": ["A", "B", "A", "B"],
        "sales": [10.0, 20.0, 30.0, 40.0],
        "cost": [4.0, 9.0, 12.0, 18.0],
        "date": ["2026-01-01", "2026-02-01", "2026-01-15", "2026-02-15"],
    })
    r = client.post("/api/v1/datasets", files={"file": ("sales.csv", io.BytesIO(frame.to_csv(index=False).encode()), "text/csv")})
    assert r.status_code == 200
    base = r.json()["dataset"]["id"]

    calc = client.post(f"/api/v1/datasets/{base}/transform", json={"operation": {
        "type": "add_calculated_column", "new_name": "margin", "expression": 'col("sales") - col("cost")'
    }})
    assert calc.status_code == 200, calc.text
    v2 = calc.json()["dataset"]["id"]
    assert "margin" in [c["name"] for c in calc.json()["profile"]["columns"]]

    enc = client.post(f"/api/v1/datasets/{v2}/transform", json={"operation": {"type": "one_hot_encode", "columns": ["segment"]}})
    assert enc.status_code == 200, enc.text
    assert any(c["name"].startswith("segment__") for c in enc.json()["profile"]["columns"])

    grouped = client.post(f"/api/v1/datasets/{base}/transform", json={"operation": {
        "type": "groupby_aggregate", "group_by": ["region"], "aggregations": [{"column": "sales", "function": "sum", "alias": "sales_total"}]
    }})
    assert grouped.status_code == 200, grouped.text
    assert grouped.json()["profile"]["rows"] == 2

    pivot = client.post(f"/api/v1/datasets/{base}/transform", json={"operation": {
        "type": "pivot_table", "index": ["region"], "columns": "segment", "values": "sales", "aggfunc": "sum"
    }})
    assert pivot.status_code == 200, pivot.text
    assert pivot.json()["profile"]["rows"] == 2

    melt = client.post(f"/api/v1/datasets/{base}/transform", json={"operation": {
        "type": "melt_unpivot", "id_vars": ["region", "segment"], "value_vars": ["sales", "cost"], "var_name": "metric", "value_name": "amount"
    }})
    assert melt.status_code == 200, melt.text
    assert melt.json()["profile"]["rows"] == 8

    dates = client.post(f"/api/v1/datasets/{base}/transform", json={"operation": {
        "type": "extract_date_parts", "column": "date", "parts": ["year", "month"]
    }})
    assert dates.status_code == 200, dates.text
    names = [c["name"] for c in dates.json()["profile"]["columns"]]
    assert "date__year" in names and "date__month" in names


def test_dataset_combination_catalog_and_replayable_pipeline(tmp_path, monkeypatch):
    from app.core.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)

    left = pd.DataFrame({"id": [1, 2, 3], "value": [10.0, None, 30.0], "group": ["A", "A", "B"]})
    right = pd.DataFrame({"id": [1, 2, 4], "label": ["x", "y", "z"]})
    l = client.post("/api/v1/datasets", files={"file": ("left.csv", io.BytesIO(left.to_csv(index=False).encode()), "text/csv")})
    r = client.post("/api/v1/datasets", files={"file": ("right.csv", io.BytesIO(right.to_csv(index=False).encode()), "text/csv")})
    left_id, right_id = l.json()["dataset"]["id"], r.json()["dataset"]["id"]

    catalog = client.get("/api/v1/datasets/catalog/all")
    assert catalog.status_code == 200
    assert {x["id"] for x in catalog.json()["datasets"]} >= {left_id, right_id}

    merge = client.post(f"/api/v1/datasets/{left_id}/combine", json={
        "other_dataset_id": right_id,
        "operation": {"type": "merge", "left_on": ["id"], "right_on": ["id"], "how": "left"},
    })
    assert merge.status_code == 200, merge.text
    assert merge.json()["profile"]["rows"] == 3
    assert "label" in [c["name"] for c in merge.json()["profile"]["columns"]]

    # Build a simple reusable pipeline on the original left dataset.
    t1 = client.post(f"/api/v1/datasets/{left_id}/transform", json={"operation": {"type": "fill_missing", "column": "value", "strategy": "median"}})
    assert t1.status_code == 200, t1.text
    v2 = t1.json()["dataset"]["id"]
    t2 = client.post(f"/api/v1/datasets/{v2}/transform", json={"operation": {"type": "add_calculated_column", "new_name": "double_value", "expression": 'col("value") * 2'}})
    assert t2.status_code == 200, t2.text
    v3 = t2.json()["dataset"]["id"]

    saved = client.post(f"/api/v1/datasets/{v3}/pipelines", json={"name": "Nettoyage valeur"})
    assert saved.status_code == 200, saved.text
    pipeline_id = saved.json()["pipeline"]["id"]
    assert saved.json()["pipeline"]["steps_count"] == 2

    replay = client.post(f"/api/v1/datasets/{left_id}/pipelines/{pipeline_id}/run")
    assert replay.status_code == 200, replay.text
    names = [c["name"] for c in replay.json()["profile"]["columns"]]
    assert "double_value" in names
    assert replay.json()["profile"]["columns_count"] == 4


def test_v06_statistics_sql_and_visualization(tmp_path, monkeypatch):
    from app.core.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)
    frame = pd.DataFrame({
        "segment": ["A"] * 30 + ["B"] * 30 + ["C"] * 30,
        "x": list(range(90)),
        "y": [v * 2.0 + (v % 3) for v in range(90)],
        "score": [10 + (i % 5) for i in range(30)] + [16 + (i % 5) for i in range(30)] + [25 + (i % 5) for i in range(30)],
        "flag": (["yes", "no"] * 45),
    })
    r = client.post("/api/v1/datasets", files={"file": ("v06.csv", io.BytesIO(frame.to_csv(index=False).encode()), "text/csv")})
    assert r.status_code == 200
    dataset_id = r.json()["dataset"]["id"]

    corr = client.post(f"/api/v1/datasets/{dataset_id}/analysis/correlations", json={"columns": ["x", "y", "score"], "method": "pearson"})
    assert corr.status_code == 200, corr.text
    assert len(corr.json()["matrix"]) == 3
    assert corr.json()["pairs"][0]["coefficient"] > 0.9

    advice = client.post(f"/api/v1/datasets/{dataset_id}/analysis/test-advisor", json={"value": "score", "group": "segment"})
    assert advice.status_code == 200, advice.text
    assert advice.json()["recommended"] in {"anova_oneway", "kruskal_wallis"}

    test = client.post(f"/api/v1/datasets/{dataset_id}/analysis/statistical-test", json={"test": "kruskal_wallis", "value": "score", "group": "segment"})
    assert test.status_code == 200, test.text
    assert test.json()["p_value"] < 0.05

    chi = client.post(f"/api/v1/datasets/{dataset_id}/analysis/statistical-test", json={"test": "chi_square", "x": "segment", "y": "flag"})
    assert chi.status_code == 200, chi.text
    assert "contingency" in chi.json()

    engine = client.get(f"/api/v1/datasets/{dataset_id}/workspace/engine")
    assert engine.status_code == 200, engine.text
    assert engine.json()["dataset"]["rows"] == 90

    sql = client.post(f"/api/v1/datasets/{dataset_id}/workspace/sql", json={"sql": "SELECT segment, AVG(score) AS avg_score FROM dataset GROUP BY segment ORDER BY segment", "limit": 100})
    assert sql.status_code == 200, sql.text
    assert sql.json()["returned_rows"] == 3
    assert "avg_score" in sql.json()["columns"]

    blocked = client.post(f"/api/v1/datasets/{dataset_id}/workspace/sql", json={"sql": "DROP TABLE dataset", "limit": 10})
    assert blocked.status_code == 400

    rec = client.post(f"/api/v1/datasets/{dataset_id}/visualizations/recommend", json={"columns": ["segment", "score"]})
    assert rec.status_code == 200, rec.text
    assert len(rec.json()["recommendations"]) >= 1

    viz = client.post(f"/api/v1/datasets/{dataset_id}/visualizations/build", json={"chart_type": "bar", "x": "segment", "y": "score", "aggregation": "mean"})
    assert viz.status_code == 200, viz.text
    assert viz.json()["type"] == "bar"
    assert len(viz.json()["data"]) == 3


def test_v07_automl_registry_model_card_and_prediction(tmp_path, monkeypatch):
    from app.core.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)

    import numpy as np
    rng = np.random.default_rng(123)
    n = 180
    age = rng.integers(18, 75, n)
    score = rng.normal(50, 12, n)
    segment = rng.choice(["A", "B", "C"], n)
    logits = -3.0 + 0.045 * age + 0.06 * score + (segment == "C") * 0.8
    prob = 1 / (1 + np.exp(-logits))
    target = (rng.random(n) < prob).astype(int)
    frame = pd.DataFrame({"patient_id": [f"P{i:04d}" for i in range(n)], "age": age, "score": score, "segment": segment, "target": target})

    r = client.post("/api/v1/datasets", files={"file": ("automl.csv", io.BytesIO(frame.to_csv(index=False).encode()), "text/csv")})
    assert r.status_code == 200, r.text
    dataset_id = r.json()["dataset"]["id"]

    auto = client.post(f"/api/v1/datasets/{dataset_id}/models/automl", json={
        "target": "target", "task": "classification", "primary_metric": "f1_weighted",
        "cv_folds": 3, "tune": False, "max_candidates": 3,
    })
    assert auto.status_code == 200, auto.text
    body = auto.json()
    assert body["task"] == "classification"
    assert len(body["benchmark"]) == 3
    assert body["rows_train"] > 0 and body["rows_validation"] > 0 and body["rows_test"] > 0
    assert "f1_weighted" in body["metrics"]
    assert body["model_card"]["validation_strategy"]["test_policy"]
    assert any(x["code"] == "identifier_features" for x in body["guardrails"])

    model_id = body["model_id"]
    card = client.get(f"/api/v1/datasets/models/{model_id}/card")
    assert card.status_code == 200, card.text
    assert card.json()["model_id"] == model_id
    assert card.json()["dataset"]["id"] == dataset_id

    registry = client.get(f"/api/v1/datasets/{dataset_id}/models")
    assert registry.status_code == 200, registry.text
    assert registry.json()["count"] >= 1
    assert any(x["model_id"] == model_id for x in registry.json()["models"])

    row = frame.drop(columns=["target"]).iloc[0].to_dict()
    pred = client.post(f"/api/v1/datasets/models/{model_id}/predict", json={"rows": [row]})
    assert pred.status_code == 200, pred.text
    assert len(pred.json()["predictions"]) == 1
    assert "probabilities" in pred.json()


def test_v08_forecasting_anomalies_and_xai(tmp_path, monkeypatch):
    from app.core.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)

    import numpy as np
    rng = np.random.default_rng(2026)
    periods = 48
    dates = pd.date_range("2022-01-01", periods=periods, freq="MS")
    trend = np.arange(periods) * 1.8
    season = 12 * np.sin(np.arange(periods) * 2 * np.pi / 12)
    sales = 120 + trend + season + rng.normal(0, 2.5, periods)
    sales[30] += 70  # obvious anomaly
    frame = pd.DataFrame({"date": dates.astype(str), "sales": sales, "cost": sales * 0.55 + rng.normal(0, 2, periods)})

    up = client.post("/api/v1/datasets", files={"file": ("timeseries.csv", io.BytesIO(frame.to_csv(index=False).encode()), "text/csv")})
    assert up.status_code == 200, up.text
    dataset_id = up.json()["dataset"]["id"]

    fc = client.post(f"/api/v1/datasets/{dataset_id}/analysis/forecast", json={
        "date_column": "date", "target": "sales", "horizon": 6,
        "frequency": "monthly", "method": "auto",
    })
    assert fc.status_code == 200, fc.text
    fbody = fc.json()
    assert len(fbody["forecast"]) == 6
    assert len(fbody["benchmark"]) >= 3
    assert fbody["method"] in {"naive", "seasonal_naive", "linear_trend", "exponential_smoothing"}
    assert fbody["prediction_interval"]["level"] == 0.95

    an = client.post(f"/api/v1/datasets/{dataset_id}/analysis/anomalies", json={
        "columns": ["sales", "cost"], "method": "isolation_forest", "contamination": 0.05,
    })
    assert an.status_code == 200, an.text
    abody = an.json()
    assert abody["anomalies_count"] >= 1
    assert len(abody["anomalies"]) >= 1

    # Separate classification dataset for XAI diagnostics and local explanation.
    n = 220
    age = rng.integers(18, 80, n)
    score = rng.normal(50, 10, n)
    segment = rng.choice(["A", "B", "C"], n)
    logits = -4.0 + 0.05 * age + 0.055 * score + (segment == "C") * 0.9
    probability = 1 / (1 + np.exp(-logits))
    target = (rng.random(n) < probability).astype(int)
    clf = pd.DataFrame({"age": age, "score": score, "segment": segment, "target": target})
    up2 = client.post("/api/v1/datasets", files={"file": ("xai.csv", io.BytesIO(clf.to_csv(index=False).encode()), "text/csv")})
    assert up2.status_code == 200, up2.text
    clf_id = up2.json()["dataset"]["id"]
    train = client.post(f"/api/v1/datasets/{clf_id}/models/automl", json={
        "target": "target", "task": "classification", "primary_metric": "f1_weighted",
        "cv_folds": 3, "tune": False, "max_candidates": 2,
    })
    assert train.status_code == 200, train.text
    model_id = train.json()["model_id"]

    diag = client.get(f"/api/v1/datasets/models/{model_id}/diagnostics")
    assert diag.status_code == 200, diag.text
    dbody = diag.json()
    assert dbody["task"] == "classification"
    assert len(dbody["confusion_matrix"]) == 2
    assert dbody["evaluation_source"] == "final_test_holdout"
    assert len(dbody["permutation_importance"]) >= 1

    row = clf.drop(columns=["target"]).iloc[0].to_dict()
    exp = client.post(f"/api/v1/datasets/models/{model_id}/explain", json={"row": row})
    assert exp.status_code == 200, exp.text
    ebody = exp.json()
    assert len(ebody["contributions"]) == 3
    assert ebody["method"].startswith("one-feature")


def test_v09_ai_analyst_orchestration_and_provenance(tmp_path, monkeypatch):
    from app.core.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)
    frame = pd.DataFrame({
        "age": list(range(20, 80)),
        "segment": (["A", "B", "C"] * 20),
        "score": [40 + i * 1.5 + (i % 4) for i in range(60)],
        "cost": [10 + i * 0.5 for i in range(60)],
    })
    upload = client.post("/api/v1/datasets", files={"file": ("analyst.csv", io.BytesIO(frame.to_csv(index=False).encode()), "text/csv")})
    assert upload.status_code == 200
    dataset_id = upload.json()["dataset"]["id"]

    caps = client.get(f"/api/v1/datasets/{dataset_id}/ai/capabilities")
    assert caps.status_code == 200, caps.text
    assert caps.json()["engine"] == "deterministic_orchestrator"
    assert any(x["name"] == "correlations" for x in caps.json()["tools"])

    analysis = client.post(f"/api/v1/datasets/{dataset_id}/ai/analyze", json={
        "question": "Quelles sont les corrélations les plus importantes entre age, score et cost ?",
        "variables": ["age", "score", "cost"],
        "mode": "fast",
    })
    assert analysis.status_code == 200, analysis.text
    body = analysis.json()
    assert body["intent"] == "correlation"
    assert body["critic"]["status"] == "passed"
    assert body["provenance"]["llm_used_for_numeric_calculation"] is False
    assert "correlations" in body["provenance"]["tools_executed"]
    assert body["artifacts"]["correlations"]["pairs"]


def test_v09_ai_analyst_regression_uses_real_engine(tmp_path, monkeypatch):
    from app.core.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)
    frame = pd.DataFrame({
        "x": list(range(50)),
        "z": [(i % 5) for i in range(50)],
        "target": [3.0 + 2.2 * i + (i % 3) for i in range(50)],
    })
    upload = client.post("/api/v1/datasets", files={"file": ("reg.csv", io.BytesIO(frame.to_csv(index=False).encode()), "text/csv")})
    dataset_id = upload.json()["dataset"]["id"]
    analysis = client.post(f"/api/v1/datasets/{dataset_id}/ai/analyze", json={
        "question": "Fais une régression pour expliquer target par x et z",
        "target": "target",
        "variables": ["x", "z"],
    })
    assert analysis.status_code == 200, analysis.text
    body = analysis.json()
    assert body["intent"] == "regression"
    assert body["artifacts"]["regression"]["r_squared"] > 0.95
    assert "regression" in body["provenance"]["tools_executed"]


def test_v10_nlq_history_reports_and_exports(tmp_path, monkeypatch):
    from app.core.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)

    frame = pd.DataFrame({
        "region": ["Nord", "Nord", "Sud", "Sud", "Est", "Est"],
        "sales": [100.0, 120.0, 80.0, 90.0, 140.0, 160.0],
        "cost": [60.0, 70.0, 50.0, 55.0, 90.0, 95.0],
    })
    upload = client.post("/api/v1/datasets", files={"file": ("report.csv", io.BytesIO(frame.to_csv(index=False).encode()), "text/csv")})
    assert upload.status_code == 200, upload.text
    dataset_id = upload.json()["dataset"]["id"]

    nlq = client.post(f"/api/v1/datasets/{dataset_id}/workspace/nlq", json={"question": "Quelle est la moyenne de sales par region ?", "limit": 100})
    assert nlq.status_code == 200, nlq.text
    nbody = nlq.json()
    assert "AVG" in nbody["sql"]
    assert nbody["result"]["returned_rows"] == 3

    analysis = client.post(f"/api/v1/datasets/{dataset_id}/ai/analyze", json={
        "question": "Quelles sont les corrélations entre sales et cost ?",
        "variables": ["sales", "cost"],
        "mode": "fast",
    })
    assert analysis.status_code == 200, analysis.text
    session_id = analysis.json()["session_id"]

    history = client.get(f"/api/v1/datasets/{dataset_id}/ai/history")
    assert history.status_code == 200, history.text
    assert history.json()["count"] == 1
    assert history.json()["analyses"][0]["session_id"] == session_id

    report = client.post(f"/api/v1/datasets/{dataset_id}/reports", json={
        "title": "Rapport ventes régional",
        "sections": ["overview", "quality", "descriptive", "ai_analysis", "methodology", "provenance"],
        "analysis_session_id": session_id,
    })
    assert report.status_code == 200, report.text
    report_id = report.json()["id"]
    assert report.json()["dataset"]["version"] == 1
    assert report.json()["reproducibility"]["analysis_session_locked"] is True

    listing = client.get(f"/api/v1/datasets/{dataset_id}/reports")
    assert listing.status_code == 200
    assert listing.json()["count"] == 1

    for fmt, content_type in [
        ("md", "text/markdown"),
        ("html", "text/html"),
        ("pdf", "application/pdf"),
        ("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    ]:
        exported = client.get(f"/api/v1/datasets/{dataset_id}/reports/{report_id}/export/{fmt}")
        assert exported.status_code == 200, exported.text
        assert content_type in exported.headers.get("content-type", "")
        assert len(exported.content) > 100


def test_visualization_density_heatmap_and_area():
    from app.services.visualization import build_visualization, recommend_visualizations
    frame = pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=30, freq="D"),
        "sales": [float(i + (i % 4)) for i in range(30)],
        "cost": [float(i * 0.6 + 3) for i in range(30)],
        "region": ["N", "S", "E"] * 10,
    })
    density = build_visualization(frame, chart_type="density", x="sales")
    assert density["type"] == "density"
    assert len(density["data"]) == 120

    heatmap = build_visualization(frame, chart_type="heatmap")
    assert heatmap["type"] == "heatmap"
    assert {"sales", "cost"}.issubset(set(heatmap["columns"]))

    area = build_visualization(frame, chart_type="area", x="date", y="sales", aggregation="mean")
    assert area["type"] == "area"
    assert len(area["data"]) == 30

    recs = recommend_visualizations(frame, ["date", "sales", "cost"])
    assert any(r["type"] == "heatmap" for r in recs)
    assert any(r["type"] == "line" for r in recs)


def test_v102_statistical_effect_sizes_and_visual_payloads():
    from app.services.statistics_engine import statistical_test
    frame = pd.DataFrame({
        "group": ["A"] * 20 + ["B"] * 20,
        "x": list(range(20)) + list(range(10, 30)),
        "y": [v * 2.0 + 1 for v in list(range(20)) + list(range(10, 30))],
    })
    welch = statistical_test(frame, "welch_t", value="x", group="group")
    assert welch["effect_size"]["name"] == "Cohen d"
    assert len(welch["group_summary"]) == 2
    assert "boxplot" in welch["group_summary"][0]

    corr = statistical_test(frame, "pearson", x="x", y="y")
    assert corr["effect_size"]["name"] == "r"
    assert corr["effect_size"]["value"] > 0.99
    assert corr["scatter_points"]


def test_v102_regression_visual_diagnostics():
    from app.services.advanced_analysis import regression_analysis
    frame = pd.DataFrame({
        "x": list(range(60)),
        "z": [(i % 7) for i in range(60)],
        "y": [5 + 1.8 * i + (i % 5) * 0.25 for i in range(60)],
    })
    out = regression_analysis(frame, "y", ["x", "z"])
    assert out["r_squared"] > 0.99
    assert out["residual_histogram"]
    assert out["qq_points"]
    assert "r" in out["qq_line"]
    assert out["influence"]


def test_v110_dashboard_insights_and_saved_visualizations(tmp_path, monkeypatch):
    from app.core.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)
    frame = pd.DataFrame({
        "ID": range(1, 81),
        "Age": list(range(20, 60)) * 2,
        "Score": [float(i * 2 + 5) for i in list(range(20, 60)) * 2],
        "Group": ["A", "B"] * 40,
    })
    frame.loc[0:9, "Score"] = None
    r = client.post("/api/v1/datasets", files={"file": ("dashboard.csv", io.BytesIO(frame.to_csv(index=False).encode()), "text/csv")})
    assert r.status_code == 200
    dataset_id = r.json()["dataset"]["id"]

    dashboard = client.get(f"/api/v1/datasets/{dataset_id}/dashboard")
    assert dashboard.status_code == 200, dashboard.text
    body = dashboard.json()
    assert body["metrics"]["rows"] == 80
    assert body["metrics"]["missing_cells"] == 10
    assert body["insights"]
    assert all("ID" not in {x.get("x"), x.get("y")} for x in body["strong_correlations"])

    built = client.post(f"/api/v1/datasets/{dataset_id}/visualizations/build", json={"chart_type": "bar", "x": "Group", "y": "Age", "aggregation": "mean", "bins": 20})
    assert built.status_code == 200, built.text
    saved = client.post(f"/api/v1/datasets/{dataset_id}/visualizations/saved", json={"title": "Age moyen par groupe", "visualization": built.json()})
    assert saved.status_code == 200, saved.text
    listed = client.get(f"/api/v1/datasets/{dataset_id}/visualizations/saved")
    assert listed.status_code == 200
    assert listed.json()["count"] == 1

    report = client.post(f"/api/v1/datasets/{dataset_id}/reports", json={"title": "Rapport dashboard", "sections": ["overview", "visualizations", "provenance"]})
    assert report.status_code == 200, report.text
    viz_blocks = [b for b in report.json()["blocks"] if b.get("type") == "visualizations"]
    assert len(viz_blocks) == 1
    assert len(viz_blocks[0]["items"]) == 1


def test_v111_professional_report_structure_and_chart_exports(tmp_path, monkeypatch):
    import zipfile
    from app.core.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)
    frame = pd.DataFrame({
        "region": ["Nord", "Sud", "Est", "Ouest"] * 20,
        "sales": [100 + i * 2.5 for i in range(80)],
        "cost": [65 + i * 1.3 for i in range(80)],
    })
    frame.loc[0:5, "cost"] = None
    upload = client.post("/api/v1/datasets", files={"file": ("executive.csv", io.BytesIO(frame.to_csv(index=False).encode()), "text/csv")})
    assert upload.status_code == 200, upload.text
    dataset_id = upload.json()["dataset"]["id"]
    built = client.post(f"/api/v1/datasets/{dataset_id}/visualizations/build", json={"chart_type":"bar","x":"region","y":"sales","aggregation":"mean","bins":20})
    assert built.status_code == 200, built.text
    saved = client.post(f"/api/v1/datasets/{dataset_id}/visualizations/saved", json={"title":"Ventes moyennes par region","visualization":built.json()})
    assert saved.status_code == 200, saved.text
    viz_id = saved.json()["visualization"]["id"]
    report = client.post(f"/api/v1/datasets/{dataset_id}/reports", json={
        "title":"Performance commerciale regionale",
        "subtitle":"Synthese decisionnelle et qualite des donnees",
        "author":"Equipe Data",
        "organization":"DataVision Lab",
        "template":"executive",
        "sections":["executive_summary","overview","quality","visualizations","methodology","provenance"],
        "visualization_ids":[viz_id],
    })
    assert report.status_code == 200, report.text
    body = report.json()
    assert body["template"] == "executive"
    assert body["section_outline"][0]["key"] == "executive_summary"
    executive = next(b for b in body["blocks"] if b["type"] == "executive_summary")
    assert len(executive["data"]["kpis"]) == 4
    assert body["visualization_ids"] == [viz_id]
    report_id = body["id"]
    html_out = client.get(f"/api/v1/datasets/{dataset_id}/reports/{report_id}/export/html")
    assert html_out.status_code == 200
    assert b"Sommaire" in html_out.content
    assert b"kpi-grid" in html_out.content
    pdf_out = client.get(f"/api/v1/datasets/{dataset_id}/reports/{report_id}/export/pdf")
    assert pdf_out.status_code == 200
    assert len(pdf_out.content) > 4000
    docx_out = client.get(f"/api/v1/datasets/{dataset_id}/reports/{report_id}/export/docx")
    assert docx_out.status_code == 200
    docx_path = tmp_path / "professional.docx"
    docx_path.write_bytes(docx_out.content)
    with zipfile.ZipFile(docx_path) as zf:
        assert any(name.startswith("word/media/") for name in zf.namelist())

def test_v120_intelligent_report_story_auto_visuals_and_limits(tmp_path, monkeypatch):
    from app.core.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)
    frame = pd.DataFrame({
        "record_id": range(1, 121),
        "date": pd.date_range("2026-01-01", periods=120, freq="D"),
        "region": ["Nord", "Sud", "Est", "Ouest"] * 30,
        "sales": [100 + i * 1.8 + (i % 5) * 3 for i in range(120)],
        "cost": [65 + i * 1.1 + (i % 7) * 2 for i in range(120)],
        "score": [40 + i * 0.7 + (i % 3) for i in range(120)],
    })
    frame.loc[0:11, "cost"] = None
    upload = client.post("/api/v1/datasets", files={"file": ("intelligent.csv", io.BytesIO(frame.to_csv(index=False).encode()), "text/csv")})
    assert upload.status_code == 200, upload.text
    dataset_id = upload.json()["dataset"]["id"]

    report = client.post(f"/api/v1/datasets/{dataset_id}/reports", json={
        "title": "Rapport intelligent",
        "template": "analytical",
        "sections": ["executive_summary", "analytical_story", "visualizations", "limitations", "methodology", "provenance"],
        "auto_story": True,
        "auto_visualizations": True,
        "max_visualizations": 6,
        "visualization_ids": [],
    })
    assert report.status_code == 200, report.text
    body = report.json()
    assert body["generation_mode"] == "intelligent"
    assert body["intelligence"]["auto_story"] is True
    assert body["auto_visualization_count"] >= 3

    story = next(b for b in body["blocks"] if b["type"] == "analytical_story")
    assert len(story["data"]["findings"]) >= 2
    assert any("correlation" in (f.get("statement", "") + f.get("evidence", "")).lower() for f in story["data"]["findings"])
    assert "record_id" in story["data"]["identifiers_excluded"]

    visuals = next(b for b in body["blocks"] if b["type"] == "visualizations")
    assert visuals["items"]
    assert all(v.get("source") == "auto_report" for v in visuals["items"])
    assert all(v.get("insight") for v in visuals["items"])
    assert all(v.get("dataset_version") == 1 for v in visuals["items"])

    limits = next(b for b in body["blocks"] if b["type"] == "limitations")
    assert any(x["title"] == "Causalite" for x in limits["items"])
    assert any(x["title"] == "Valeurs manquantes" for x in limits["items"])

    html_out = client.get(f"/api/v1/datasets/{dataset_id}/reports/{body['id']}/export/html")
    assert html_out.status_code == 200
    assert b"story-grid" in html_out.content
    assert b"figure-insight" in html_out.content
    pdf_out = client.get(f"/api/v1/datasets/{dataset_id}/reports/{body['id']}/export/pdf")
    assert pdf_out.status_code == 200
    assert len(pdf_out.content) > 5000

def test_v130_dashboard_builder_filters_persistence_and_cross_filter_payload(tmp_path, monkeypatch):
    from app.core.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)
    frame = pd.DataFrame({
        "region": ["Nord", "Sud", "Nord", "Est", "Sud", "Nord"],
        "sales": [100, 80, 120, 60, 95, 140],
        "cost": [60, 50, 65, 40, 55, 70],
    })
    upload = client.post("/api/v1/datasets", files={"file": ("dash.csv", io.BytesIO(frame.to_csv(index=False).encode()), "text/csv")})
    assert upload.status_code == 200
    dataset_id = upload.json()["dataset"]["id"]

    widgets = [
        {"id":"k1","title":"Observations","type":"kpi","size":"small","config":{"metric":"rows"}},
        {"id":"c1","title":"Ventes par région","type":"chart","size":"medium","config":{"chart_type":"bar","x":"region","y":"sales","aggregation":"mean","bins":20}},
    ]
    preview = client.post(f"/api/v1/datasets/{dataset_id}/dashboards/preview", json={
        "filters":[{"column":"region","operator":"eq","value":"Nord"}], "widgets":widgets,
    })
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["rows_before"] == 6
    assert body["rows_after"] == 3
    kpi = next(w for w in body["widgets"] if w["id"] == "k1")
    assert kpi["result"]["value"] == 3
    chart = next(w for w in body["widgets"] if w["id"] == "c1")
    assert chart["status"] == "ok"
    assert chart["result"]["data"][0]["label"] == "Nord"
    assert chart["result"]["data"][0]["value"] == 120.0

    saved = client.post(f"/api/v1/datasets/{dataset_id}/dashboards", json={
        "name":"Pilotage commercial", "description":"Dashboard de test", "filters":[], "widgets":widgets,
    })
    assert saved.status_code == 200, saved.text
    dashboard_id = saved.json()["dashboard"]["id"]
    listed = client.get(f"/api/v1/datasets/{dataset_id}/dashboards")
    assert listed.status_code == 200
    assert listed.json()["count"] == 1
    detail = client.get(f"/api/v1/datasets/{dataset_id}/dashboards/{dashboard_id}")
    assert detail.status_code == 200
    assert detail.json()["dashboard"]["name"] == "Pilotage commercial"
    updated = client.post(f"/api/v1/datasets/{dataset_id}/dashboards", json={
        "dashboard_id":dashboard_id, "name":"Pilotage commercial v2", "filters":[{"column":"sales","operator":"gte","value":100}], "widgets":widgets,
    })
    assert updated.status_code == 200
    assert updated.json()["dashboard"]["name"] == "Pilotage commercial v2"
    deleted = client.delete(f"/api/v1/datasets/{dataset_id}/dashboards/{dashboard_id}")
    assert deleted.status_code == 200
    assert client.get(f"/api/v1/datasets/{dataset_id}/dashboards").json()["count"] == 0

def test_v200_semantic_layer_grounded_nlq_and_trust(tmp_path, monkeypatch):
    from app.core.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)
    frame = pd.DataFrame({
        "region": ["Nord", "Nord", "Sud", "Sud"],
        "revenue": [100.0, 120.0, 80.0, 100.0],
        "cost": [60.0, 70.0, 50.0, 55.0],
    })
    upload = client.post("/api/v1/datasets", files={"file": ("semantic.csv", io.BytesIO(frame.to_csv(index=False).encode()), "text/csv")})
    assert upload.status_code == 200, upload.text
    dataset_id = upload.json()["dataset"]["id"]

    semantic = client.get(f"/api/v1/datasets/{dataset_id}/semantic")
    assert semantic.status_code == 200, semantic.text
    auto = semantic.json()
    assert any(m["column"] == "revenue" for m in auto["metrics"])

    payload = {
        "metrics": [{
            "id": "revenue", "name": "Revenue", "label": "Chiffre d'affaires", "column": "revenue",
            "aggregation": "sum", "unit": "EUR", "description": "Revenu reconnu", "synonyms": ["CA", "ventes"], "certified": True,
        }],
        "dimensions": [{"column": "region", "label": "Région", "description": "Zone commerciale", "synonyms": ["zone"], "hidden": False}],
        "business_glossary": [{"term": "CA", "definition": "Chiffre d'affaires"}],
    }
    saved = client.post(f"/api/v1/datasets/{dataset_id}/semantic", json=payload)
    assert saved.status_code == 200, saved.text
    assert saved.json()["status"] == "governed"
    assert saved.json()["metrics"][0]["certified"] is True

    evaluated = client.post(f"/api/v1/datasets/{dataset_id}/semantic/evaluate", json={"metric_id":"revenue","dimensions":["region"],"filters":[]})
    assert evaluated.status_code == 200, evaluated.text
    assert evaluated.json()["value"] == 400.0

    nlq = client.post(f"/api/v1/datasets/{dataset_id}/workspace/nlq", json={"question":"Quelle est la moyenne du chiffre d'affaires par zone ?", "limit":100})
    assert nlq.status_code == 200, nlq.text
    nbody = nlq.json()
    assert "AVG" in nbody["sql"]
    assert '"region"' in nbody["sql"]
    assert nbody["semantic_grounding"]["metric_id"] == "revenue"
    assert nbody["semantic_grounding"]["certified"] is True

    trust = client.get(f"/api/v1/datasets/{dataset_id}/trust")
    assert trust.status_code == 200, trust.text
    tbody = trust.json()
    assert 0 <= tbody["overall_score"] <= 100
    assert any(x["area"] == "Sémantique" for x in tbody["checks"])


def test_v200_ai_analyst_uses_semantic_synonyms(tmp_path, monkeypatch):
    from app.core.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)
    frame = pd.DataFrame({
        "segment": ["A", "B"] * 30,
        "sales_value": [float(20 + i * 2) for i in range(60)],
        "driver_x": [float(i) for i in range(60)],
    })
    upload = client.post("/api/v1/datasets", files={"file": ("ai_semantic.csv", io.BytesIO(frame.to_csv(index=False).encode()), "text/csv")})
    dataset_id = upload.json()["dataset"]["id"]
    sem = {
        "metrics": [{"id":"sales","name":"Sales","label":"Ventes","column":"sales_value","aggregation":"sum","unit":"","description":"","synonyms":["chiffre commercial"],"certified":True}],
        "dimensions": [{"column":"segment","label":"Segment","description":"","synonyms":["groupe client"],"hidden":False}],
        "business_glossary": [],
    }
    assert client.post(f"/api/v1/datasets/{dataset_id}/semantic", json=sem).status_code == 200
    analyzed = client.post(f"/api/v1/datasets/{dataset_id}/ai/analyze", json={"question":"Fais une régression pour expliquer le chiffre commercial par driver_x", "mode":"fast"})
    assert analyzed.status_code == 200, analyzed.text
    body = analyzed.json()
    assert body["intent"] == "regression"
    assert body["provenance"]["semantic_grounding"] is True
    assert "sales_value" in body["provenance"]["semantic_matches"]
    assert body["artifacts"]["semantic_context"]["certified_metrics"] == ["sales"]
    assert body["artifacts"]["regression"]["dependent"] == "sales_value"


def test_v200_decision_lab_what_if_and_sensitivity(tmp_path, monkeypatch):
    from app.core.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)
    frame = pd.DataFrame({
        "x": [float(i) for i in range(80)],
        "z": [float(i % 5) for i in range(80)],
        "target": [5.0 + 2.0 * i + 0.5 * (i % 5) for i in range(80)],
    })
    upload = client.post("/api/v1/datasets", files={"file": ("whatif.csv", io.BytesIO(frame.to_csv(index=False).encode()), "text/csv")})
    dataset_id = upload.json()["dataset"]["id"]
    trained = client.post(f"/api/v1/datasets/{dataset_id}/models/train", json={"target":"target","task":"regression","algorithm":"linear_regression"})
    assert trained.status_code == 200, trained.text
    model_id = trained.json()["model_id"]
    base = {"x": 10.0, "z": 2.0}
    whatif = client.post(f"/api/v1/datasets/models/{model_id}/what-if", json={"base_row":base,"scenarios":[{"name":"x +10","overrides":{"x":20.0}}]})
    assert whatif.status_code == 200, whatif.text
    wbody = whatif.json()
    assert len(wbody["scenarios"]) == 2
    assert wbody["scenarios"][1]["prediction"] > wbody["scenarios"][0]["prediction"]
    assert "causal" in wbody["warning"].lower()

    sens = client.post(f"/api/v1/datasets/models/{model_id}/sensitivity", json={"base_row":base,"feature":"x","values":[0,10,20,30]})
    assert sens.status_code == 200, sens.text
    points = sens.json()["points"]
    assert len(points) == 4
    assert points[0]["prediction"] < points[-1]["prediction"]


def test_v210_enterprise_bootstrap_workspace_rbac_audit_and_policies(tmp_path, monkeypatch):
    from app.core.config import get_settings
    from app.services import metadata_store
    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'enterprise.db'}")
    metadata_store._ENGINES.clear()

    boot = client.post("/api/v1/auth/bootstrap", json={
        "email": "owner@datavision.local",
        "password": "EnterprisePass123!",
        "display_name": "Owner",
        "organization_name": "DataVision Lab",
    })
    assert boot.status_code == 200, boot.text
    token = boot.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    workspace_id = boot.json()["workspace_id"]
    org_id = boot.json()["organization_id"]

    me = client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200, me.text
    assert me.json()["user"]["email"] == "owner@datavision.local"
    assert me.json()["workspaces"][0]["role"] == "owner"

    ws = client.post("/api/v1/workspaces", headers=headers, json={"organization_id": org_id, "name": "Analytics Team"})
    assert ws.status_code == 200, ws.text
    second_ws = ws.json()["workspace"]["id"]

    frame = pd.DataFrame({"region": ["N", "S", "N"], "sales": [100, 80, 120], "secret": [1, 2, 3]})
    upload = client.post("/api/v1/datasets", files={"file": ("governed.csv", io.BytesIO(frame.to_csv(index=False).encode()), "text/csv")})
    assert upload.status_code == 200
    dataset_id = upload.json()["dataset"]["id"]

    bound = client.post(f"/api/v1/workspaces/{second_ws}/datasets", headers=headers, json={"dataset_id": dataset_id})
    assert bound.status_code == 200, bound.text

    policy = client.post(f"/api/v1/workspaces/{second_ws}/policies", headers=headers, json={
        "dataset_id": dataset_id,
        "name": "Analystes - colonnes publiques",
        "allowed_columns": ["region", "sales"],
        "row_filters": [{"column": "sales", "operator": "gte", "value": 90}],
        "applies_to_role": "analyst",
    })
    assert policy.status_code == 200, policy.text
    assert policy.json()["policy"]["allowed_columns"] == ["region", "sales"]

    detail = client.get(f"/api/v1/workspaces/{second_ws}", headers=headers)
    assert detail.status_code == 200, detail.text
    assert detail.json()["workspace"]["datasets_count"] == 1
    assert len(detail.json()["policies"]) == 1

    provisioned = client.post(f"/api/v1/workspaces/{second_ws}/members", headers=headers, json={
        "email": "analyst@datavision.local", "role": "analyst", "display_name": "Analyst",
        "password": "AnalystPass123!",
    })
    assert provisioned.status_code == 200, provisioned.text
    analyst_login = client.post("/api/v1/auth/login", json={"email":"analyst@datavision.local","password":"AnalystPass123!"})
    assert analyst_login.status_code == 200, analyst_login.text
    analyst_headers = {"Authorization": f"Bearer {analyst_login.json()['access_token']}"}
    governed = client.get(f"/api/v1/workspaces/{second_ws}/datasets/{dataset_id}/governed-preview", headers=analyst_headers)
    assert governed.status_code == 200, governed.text
    assert governed.json()["columns"] == ["region", "sales"]
    assert governed.json()["total_rows"] == 2
    simulated = client.get(f"/api/v1/workspaces/{second_ws}/datasets/{dataset_id}/governed-preview?simulate_role=analyst", headers=headers)
    assert simulated.status_code == 200, simulated.text
    assert simulated.json()["effective_role"] == "analyst"
    assert simulated.json()["columns"] == ["region", "sales"]
    denied = client.post(f"/api/v1/workspaces/{second_ws}/policies", headers=analyst_headers, json={
        "dataset_id": dataset_id, "name":"Should fail", "allowed_columns":[], "row_filters":[], "applies_to_role":"viewer"
    })
    assert denied.status_code == 403

    audit = client.get(f"/api/v1/audit?workspace_id={second_ws}", headers=headers)
    assert audit.status_code == 200, audit.text
    event_types = {e["event_type"] for e in audit.json()["events"]}
    assert "workspace.dataset.bind" in event_types
    assert "workspace.policy.save" in event_types
    assert "dataset.governed_preview" in event_types

    login = client.post("/api/v1/auth/login", json={"email": "owner@datavision.local", "password": "EnterprisePass123!"})
    assert login.status_code == 200, login.text
    assert login.json()["access_token"]


def test_v210_jobs_tracking_and_cancellation(tmp_path, monkeypatch):
    from app.core.config import get_settings
    from app.services import metadata_store, job_service
    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'jobs.db'}")
    metadata_store._ENGINES.clear()

    class FakeRedis:
        def __init__(self): self.items = []
        def rpush(self, key, value): self.items.append((key, value)); return len(self.items)
    fake = FakeRedis()
    monkeypatch.setattr(job_service, "_redis", lambda: fake)

    boot = client.post("/api/v1/auth/bootstrap", json={
        "email": "jobs@datavision.local", "password": "EnterprisePass123!",
        "display_name": "Jobs Owner", "organization_name": "Jobs Org",
    })
    assert boot.status_code == 200, boot.text
    headers = {"Authorization": f"Bearer {boot.json()['access_token']}"}
    ws = boot.json()["workspace_id"]
    org = boot.json()["organization_id"]

    submitted = client.post("/api/v1/jobs", headers=headers, json={
        "workspace_id": ws, "organization_id": org, "job_type": "ai_analysis",
        "dataset_id": "dataset-placeholder", "payload": {"question": "Analyse ce dataset"},
    })
    assert submitted.status_code == 200, submitted.text
    job_id = submitted.json()["job"]["id"]
    assert submitted.json()["job"]["status"] == "queued"
    assert fake.items and fake.items[0][1] == job_id

    listed = client.get(f"/api/v1/jobs?workspace_id={ws}", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["jobs"][0]["id"] == job_id

    cancelled = client.post(f"/api/v1/jobs/{job_id}/cancel", headers=headers)
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["job"]["status"] == "cancelled"


def test_v220_tenant_aware_access_applies_to_legacy_analytics_and_sql(tmp_path, monkeypatch):
    from app.core.config import get_settings
    from app.services import metadata_store

    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'tenant-aware.db'}")
    metadata_store._ENGINES.clear()

    boot = client.post("/api/v1/auth/bootstrap", json={
        "email": "owner220@datavision.local",
        "password": "EnterprisePass123!",
        "display_name": "Owner 220",
        "organization_name": "Tenant 220",
    })
    assert boot.status_code == 200, boot.text
    owner_token = boot.json()["access_token"]
    ws = boot.json()["workspace_id"]
    owner_headers = {"Authorization": f"Bearer {owner_token}", "X-Workspace-ID": ws}

    frame = pd.DataFrame({
        "region": ["N", "S", "N", "S"],
        "sales": [100.0, 80.0, 120.0, 200.0],
        "margin": [10.0, 8.0, 12.0, 20.0],
        "secret": [111, 222, 333, 444],
    })
    upload = client.post("/api/v1/datasets", headers=owner_headers, files={"file": ("tenant.csv", io.BytesIO(frame.to_csv(index=False).encode()), "text/csv")})
    assert upload.status_code == 200, upload.text
    dataset_id = upload.json()["dataset"]["id"]

    provisioned = client.post(f"/api/v1/workspaces/{ws}/members", headers={"Authorization": f"Bearer {owner_token}"}, json={
        "email": "analyst220@datavision.local", "role": "analyst", "display_name": "Analyst 220",
        "password": "AnalystPass123!",
    })
    assert provisioned.status_code == 200, provisioned.text
    policy = client.post(f"/api/v1/workspaces/{ws}/policies", headers={"Authorization": f"Bearer {owner_token}"}, json={
        "dataset_id": dataset_id,
        "name": "Public sales only",
        "allowed_columns": ["region", "sales", "margin"],
        "row_filters": [{"column": "sales", "operator": "gte", "value": 100}],
        "applies_to_role": "analyst",
    })
    assert policy.status_code == 200, policy.text

    login = client.post("/api/v1/auth/login", json={"email": "analyst220@datavision.local", "password": "AnalystPass123!"})
    assert login.status_code == 200, login.text
    analyst_headers = {"Authorization": f"Bearer {login.json()['access_token']}", "X-Workspace-ID": ws}

    preview = client.get(f"/api/v1/datasets/{dataset_id}/preview?limit=20", headers=analyst_headers)
    assert preview.status_code == 200, preview.text
    assert preview.headers.get("x-datavision-governed") == "true"
    assert preview.json()["columns"] == ["region", "sales", "margin"]
    assert preview.json()["total"] == 3
    assert all(row["sales"] >= 100 for row in preview.json()["rows"])
    assert all("secret" not in row for row in preview.json()["rows"])

    access = client.get(f"/api/v1/datasets/{dataset_id}/access-context", headers=analyst_headers)
    assert access.status_code == 200, access.text
    assert access.json()["governed"] is True
    assert access.json()["role"] == "analyst"
    assert access.json()["effective_rows"] == 3
    assert access.json()["effective_columns"] == ["region", "sales", "margin"]

    sql = client.post(f"/api/v1/datasets/{dataset_id}/workspace/sql", headers=analyst_headers, json={"sql": "SELECT * FROM dataset ORDER BY sales", "limit": 20})
    assert sql.status_code == 200, sql.text
    assert sql.json()["columns"] == ["region", "sales", "margin"]
    assert len(sql.json()["rows"]) == 3

    correlations = client.post(f"/api/v1/datasets/{dataset_id}/analysis/correlations", headers=analyst_headers, json={"columns": ["sales", "margin"], "method": "pearson"})
    assert correlations.status_code == 200, correlations.text
    hidden_column = client.post(f"/api/v1/datasets/{dataset_id}/analysis/correlations", headers=analyst_headers, json={"columns": ["sales", "secret"], "method": "pearson"})
    assert hidden_column.status_code == 400

    forbidden_transform = client.post(f"/api/v1/datasets/{dataset_id}/transform", headers=analyst_headers, json={"operation": {"type": "rename_column", "column": "sales", "new_name": "sales2"}})
    assert forbidden_transform.status_code == 403


def test_v220_workspace_isolation_catalog_and_version_inheritance(tmp_path, monkeypatch):
    from app.core.config import get_settings
    from app.services import metadata_store

    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'tenant-lineage.db'}")
    metadata_store._ENGINES.clear()

    boot = client.post("/api/v1/auth/bootstrap", json={
        "email": "lineage@datavision.local", "password": "EnterprisePass123!",
        "display_name": "Lineage Owner", "organization_name": "Lineage Org",
    })
    assert boot.status_code == 200, boot.text
    token = boot.json()["access_token"]
    ws = boot.json()["workspace_id"]
    base_headers = {"Authorization": f"Bearer {token}"}
    governed_headers = {"Authorization": f"Bearer {token}", "X-Workspace-ID": ws}

    # Bound upload: middleware + upload route attach it to the active workspace.
    bound_frame = pd.DataFrame({"region": ["N", "S", "N"], "sales": [10, 20, 30], "secret": [1, 2, 3]})
    bound = client.post("/api/v1/datasets", headers=governed_headers, files={"file": ("bound.csv", io.BytesIO(bound_frame.to_csv(index=False).encode()), "text/csv")})
    assert bound.status_code == 200, bound.text
    bound_id = bound.json()["dataset"]["id"]

    # Unbound local upload must remain invisible to the Enterprise workspace.
    other = client.post("/api/v1/datasets", files={"file": ("other.csv", io.BytesIO(pd.DataFrame({"x": [1,2]}).to_csv(index=False).encode()), "text/csv")})
    other_id = other.json()["dataset"]["id"]
    denied = client.get(f"/api/v1/datasets/{other_id}/preview", headers=governed_headers)
    assert denied.status_code == 403

    catalog = client.get("/api/v1/datasets/catalog/all", headers=governed_headers)
    assert catalog.status_code == 200, catalog.text
    catalog_ids = {x["id"] for x in catalog.json()["datasets"]}
    assert bound_id in catalog_ids
    assert other_id not in catalog_ids

    # Owner policy is inherited by a derived immutable version. The RLS filter uses a column
    # that is intentionally omitted from allowed_columns to verify row-first enforcement.
    policy = client.post(f"/api/v1/workspaces/{ws}/policies", headers=base_headers, json={
        "dataset_id": bound_id,
        "name": "Owner inherited policy",
        "allowed_columns": ["region", "sales"],
        "row_filters": [{"column": "secret", "operator": "gte", "value": 2}],
        "applies_to_role": "owner",
    })
    assert policy.status_code == 200, policy.text

    parent_preview = client.get(f"/api/v1/datasets/{bound_id}/preview", headers=governed_headers)
    assert parent_preview.status_code == 200, parent_preview.text
    assert parent_preview.json()["columns"] == ["region", "sales"]
    assert parent_preview.json()["total"] == 2

    transformed = client.post(f"/api/v1/datasets/{bound_id}/transform", headers=governed_headers, json={
        "operation": {"type": "rename_column", "column": "sales", "new_name": "revenue"}
    })
    assert transformed.status_code == 200, transformed.text
    child_id = transformed.json()["dataset"]["id"]

    # Derived version was automatically bound and inherited the row-level policy.
    child_access = client.get(f"/api/v1/datasets/{child_id}/access-context", headers=governed_headers)
    assert child_access.status_code == 200, child_access.text
    assert child_access.json()["policy_count"] >= 1
    assert child_access.json()["effective_rows"] == 2
    # The inherited column rule keeps only columns that still exist after the transform.
    assert child_access.json()["effective_columns"] == ["region"]


def test_v220_background_job_reuses_tenant_access_context(tmp_path, monkeypatch):
    from app.core.config import get_settings
    from app.services import metadata_store, job_service

    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'tenant-job.db'}")
    metadata_store._ENGINES.clear()

    class FakeRedis:
        def __init__(self): self.items=[]
        def rpush(self, key, value): self.items.append((key,value)); return len(self.items)
    fake=FakeRedis()
    monkeypatch.setattr(job_service, "_redis", lambda: fake)

    boot=client.post("/api/v1/auth/bootstrap", json={
        "email":"jobowner@datavision.local","password":"EnterprisePass123!",
        "display_name":"Job Owner","organization_name":"Job Org",
    })
    assert boot.status_code==200, boot.text
    owner_token=boot.json()["access_token"]; ws=boot.json()["workspace_id"]; org=boot.json()["organization_id"]
    owner_headers={"Authorization":f"Bearer {owner_token}","X-Workspace-ID":ws}

    dates=pd.date_range("2024-01-01", periods=24, freq="D")
    frame=pd.DataFrame({"date":dates.astype(str),"sales":[float(i+1) for i in range(24)],"secret":[1000+i for i in range(24)]})
    upload=client.post("/api/v1/datasets", headers=owner_headers, files={"file":("jobs.csv",io.BytesIO(frame.to_csv(index=False).encode()),"text/csv")})
    assert upload.status_code==200, upload.text
    dataset_id=upload.json()["dataset"]["id"]

    member=client.post(f"/api/v1/workspaces/{ws}/members", headers={"Authorization":f"Bearer {owner_token}"}, json={
        "email":"jobanalyst@datavision.local","role":"analyst","display_name":"Job Analyst","password":"AnalystPass123!"
    })
    assert member.status_code==200, member.text
    pol=client.post(f"/api/v1/workspaces/{ws}/policies", headers={"Authorization":f"Bearer {owner_token}"}, json={
        "dataset_id":dataset_id,"name":"Recent only","allowed_columns":["date","sales"],
        "row_filters":[{"column":"sales","operator":"gte","value":7}],"applies_to_role":"analyst"
    })
    assert pol.status_code==200, pol.text
    login=client.post("/api/v1/auth/login", json={"email":"jobanalyst@datavision.local","password":"AnalystPass123!"})
    analyst_token=login.json()["access_token"]
    analyst_headers={"Authorization":f"Bearer {analyst_token}"}

    submitted=client.post("/api/v1/jobs", headers=analyst_headers, json={
        "workspace_id":ws,"organization_id":org,"job_type":"forecast","dataset_id":dataset_id,
        "payload":{"date_column":"date","target":"sales","horizon":3,"frequency":"daily","method":"naive"}
    })
    assert submitted.status_code==200, submitted.text
    job_id=submitted.json()["job"]["id"]
    completed=job_service.run_job(job_id)
    assert completed["status"]=="completed", completed
    history=completed["result"]["history"]
    # RLS removed sales 1..6 before the worker reached forecasting.
    assert len(history)==18
    assert min(float(x["value"]) for x in history)>=7
