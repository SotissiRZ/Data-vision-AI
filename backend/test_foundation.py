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


def test_v230_semantic_multitable_relationship_and_query(tmp_path, monkeypatch):
    from app.core.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)

    fact = pd.DataFrame({
        "product_id": [1, 1, 2, 3],
        "revenue": [100.0, 50.0, 200.0, 80.0],
        "date": ["2026-01-05", "2026-01-20", "2026-02-03", "2026-02-10"],
    })
    products = pd.DataFrame({"product_id": [1, 2, 3], "category": ["A", "B", "A"]})
    f = client.post("/api/v1/datasets", files={"file": ("sales.csv", io.BytesIO(fact.to_csv(index=False).encode()), "text/csv")})
    d = client.post("/api/v1/datasets", files={"file": ("products.csv", io.BytesIO(products.to_csv(index=False).encode()), "text/csv")})
    assert f.status_code == 200 and d.status_code == 200
    fact_id, dim_id = f.json()["dataset"]["id"], d.json()["dataset"]["id"]

    catalog = client.get(f"/api/v1/datasets/{fact_id}/semantic/tables")
    assert catalog.status_code == 200, catalog.text
    assert dim_id in {x["dataset_id"] for x in catalog.json()["tables"]}

    model = {
        "tables": [
            {"id": "base", "dataset_id": fact_id, "label": "Sales", "role": "fact", "active": True},
            {"id": "product", "dataset_id": dim_id, "label": "Products", "role": "dimension", "active": True},
        ],
        "relationships": [{
            "id": "sales_product", "from_table": "base", "from_column": "product_id",
            "to_table": "product", "to_column": "product_id", "cardinality": "many_to_one",
            "join_type": "left", "active": True,
        }],
        "metrics": [{
            "id": "revenue", "name": "Revenue", "label": "Revenue", "type": "base", "table": "base",
            "column": "revenue", "aggregation": "sum", "unit": "EUR", "description": "Revenue", "synonyms": ["CA"], "certified": True,
        }],
        "dimensions": [
            {"id": "category", "table": "product", "column": "category", "label": "Category", "kind": "categorical", "hidden": False, "certified": True, "synonyms": []},
            {"id": "date", "table": "base", "column": "date", "label": "Date", "kind": "date", "hidden": False, "certified": True, "synonyms": []},
        ],
        "hierarchies": [], "business_glossary": [],
    }
    valid = client.post(f"/api/v1/datasets/{fact_id}/semantic/validate", json=model)
    assert valid.status_code == 200, valid.text
    assert valid.json()["valid"] is True
    saved = client.post(f"/api/v1/datasets/{fact_id}/semantic", json=model)
    assert saved.status_code == 200, saved.text
    assert saved.json()["semantic_version"] == 2

    query = client.post(f"/api/v1/datasets/{fact_id}/semantic/query", json={"metric_id": "revenue", "dimensions": ["category"]})
    assert query.status_code == 200, query.text
    rows = {r["category"]: r["value"] for r in query.json()["result"]}
    assert rows["A"] == 230.0
    assert rows["B"] == 200.0


def test_v230_calculated_metric_and_time_intelligence(tmp_path, monkeypatch):
    from app.core.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)

    frame = pd.DataFrame({
        "date": ["2025-01-15", "2025-02-15", "2026-01-15", "2026-02-15"],
        "revenue": [100.0, 120.0, 150.0, 180.0],
        "cost": [60.0, 72.0, 90.0, 90.0],
    })
    upload = client.post("/api/v1/datasets", files={"file": ("finance.csv", io.BytesIO(frame.to_csv(index=False).encode()), "text/csv")})
    dataset_id = upload.json()["dataset"]["id"]
    model = {
        "tables": [{"id": "base", "dataset_id": dataset_id, "label": "Finance", "role": "fact", "active": True}],
        "relationships": [],
        "metrics": [
            {"id": "revenue", "label": "Revenue", "name": "Revenue", "type": "base", "table": "base", "column": "revenue", "aggregation": "sum", "unit": "EUR", "certified": True, "description": "", "synonyms": []},
            {"id": "cost", "label": "Cost", "name": "Cost", "type": "base", "table": "base", "column": "cost", "aggregation": "sum", "unit": "EUR", "certified": True, "description": "", "synonyms": []},
            {"id": "margin_pct", "label": "Margin %", "name": "Margin %", "type": "calculated", "table": "base", "column": "", "aggregation": "sum", "formula": "(revenue - cost) / revenue * 100", "unit": "%", "certified": True, "description": "", "synonyms": ["marge"]},
        ],
        "dimensions": [{"id": "date", "table": "base", "column": "date", "label": "Date", "kind": "date", "hidden": False, "certified": True, "synonyms": []}],
        "hierarchies": [{"id": "calendar", "name": "Calendar", "levels": ["date", "date"], "certified": True}],
        "business_glossary": [],
    }
    saved = client.post(f"/api/v1/datasets/{dataset_id}/semantic", json=model)
    assert saved.status_code == 200, saved.text

    margin = client.post(f"/api/v1/datasets/{dataset_id}/semantic/query", json={"metric_id": "margin_pct"})
    assert margin.status_code == 200, margin.text
    assert round(margin.json()["value"], 2) == 43.27

    trend = client.post(f"/api/v1/datasets/{dataset_id}/semantic/query", json={
        "metric_id": "revenue", "date_dimension": "date", "time_grain": "month",
        "comparison": "yoy", "time_calculation": "ytd", "rolling_window": 3,
    })
    assert trend.status_code == 200, trend.text
    rows = trend.json()["result"]
    assert len(rows) == 4
    jan_2026 = next(r for r in rows if str(r["date"]).startswith("2026-01"))
    assert jan_2026["comparison_value"] == 100.0
    assert round(jan_2026["delta_pct"], 1) == 50.0
    feb_2026 = next(r for r in rows if str(r["date"]).startswith("2026-02"))
    assert feb_2026["time_value"] == 330.0


def test_v230_semantic_blocks_fanout_relationship(tmp_path, monkeypatch):
    from app.core.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)

    fact = pd.DataFrame({"product_id": [1, 2], "revenue": [10, 20]})
    bad_dim = pd.DataFrame({"product_id": [1, 1, 2], "category": ["A", "A2", "B"]})
    f = client.post("/api/v1/datasets", files={"file": ("fact.csv", io.BytesIO(fact.to_csv(index=False).encode()), "text/csv")})
    d = client.post("/api/v1/datasets", files={"file": ("bad_dim.csv", io.BytesIO(bad_dim.to_csv(index=False).encode()), "text/csv")})
    fact_id, dim_id = f.json()["dataset"]["id"], d.json()["dataset"]["id"]
    model = {
        "tables": [{"id":"base","dataset_id":fact_id,"label":"Fact","role":"fact","active":True},{"id":"dim","dataset_id":dim_id,"label":"Dim","role":"dimension","active":True}],
        "relationships": [{"id":"bad","from_table":"base","from_column":"product_id","to_table":"dim","to_column":"product_id","cardinality":"many_to_one","join_type":"left","active":True}],
        "metrics": [{"id":"revenue","label":"Revenue","name":"Revenue","type":"base","table":"base","column":"revenue","aggregation":"sum","unit":"","description":"","synonyms":[],"certified":True}],
        "dimensions": [{"id":"category","table":"dim","column":"category","label":"Category","kind":"categorical","hidden":False,"certified":True,"synonyms":[]}],
        "hierarchies": [], "business_glossary": [],
    }
    validation = client.post(f"/api/v1/datasets/{fact_id}/semantic/validate", json=model)
    assert validation.status_code == 200
    assert validation.json()["valid"] is False
    assert any("fan-out" in e for e in validation.json()["errors"])
    saved = client.post(f"/api/v1/datasets/{fact_id}/semantic", json=model)
    assert saved.status_code == 400


def _v240_make_semantic_sales(tmp_path, monkeypatch):
    from app.core.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)

    fact = pd.DataFrame({
        "product_id": [1, 1, 2, 3],
        "revenue": [100.0, 50.0, 200.0, 80.0],
        "date": ["2026-01-05", "2026-01-20", "2026-02-03", "2026-02-10"],
    })
    products = pd.DataFrame({
        "product_id": [1, 2, 3],
        "category_id": [10, 20, 10],
        "category": ["A", "B", "A"],
        "subcategory": ["A1", "B1", "A2"],
    })
    f = client.post("/api/v1/datasets", files={"file": ("sales.csv", io.BytesIO(fact.to_csv(index=False).encode()), "text/csv")})
    d = client.post("/api/v1/datasets", files={"file": ("products.csv", io.BytesIO(products.to_csv(index=False).encode()), "text/csv")})
    assert f.status_code == 200 and d.status_code == 200
    fact_id, dim_id = f.json()["dataset"]["id"], d.json()["dataset"]["id"]
    model = {
        "tables": [
            {"id":"base","dataset_id":fact_id,"label":"Sales","role":"fact","active":True},
            {"id":"product","dataset_id":dim_id,"label":"Products","role":"dimension","active":True},
        ],
        "relationships": [{
            "id":"sales_product","from_table":"base","from_column":"product_id",
            "to_table":"product","to_column":"product_id","cardinality":"many_to_one","join_type":"left","active":True,
        }],
        "metrics": [{
            "id":"revenue","name":"Revenue","label":"Chiffre d'affaires","type":"base","table":"base",
            "column":"revenue","aggregation":"sum","unit":"EUR","description":"CA net","synonyms":["CA","ventes"],"certified":True,
        }],
        "dimensions": [
            {"id":"category","table":"product","column":"category","label":"Catégorie","kind":"categorical","hidden":False,"certified":True,"synonyms":["famille"]},
            {"id":"subcategory","table":"product","column":"subcategory","label":"Sous-catégorie","kind":"categorical","hidden":False,"certified":True,"synonyms":["sous famille"]},
            {"id":"date","table":"base","column":"date","label":"Date","kind":"date","hidden":False,"certified":True,"synonyms":[]},
        ],
        "hierarchies": [{"id":"catalog","name":"Catalogue","levels":["category","subcategory"],"certified":True}],
        "business_glossary": [],
    }
    saved = client.post(f"/api/v1/datasets/{fact_id}/semantic", json=model)
    assert saved.status_code == 200, saved.text
    return fact_id, dim_id


def test_v240_nlq_uses_multitable_semantic_engine(tmp_path, monkeypatch):
    fact_id, _ = _v240_make_semantic_sales(tmp_path, monkeypatch)
    r = client.post(f"/api/v1/datasets/{fact_id}/workspace/nlq", json={"question":"Quel est le CA par catégorie ?", "limit":50})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["execution_mode"] == "semantic"
    assert body["sql_executable"] is False
    assert "SEMANTIC_MODEL" in body["sql"]
    assert body["semantic_grounding"]["metric_id"] == "revenue"
    rows = {row["category"]: row["value"] for row in body["result"]["rows"]}
    assert rows == {"A": 230.0, "B": 200.0}
    assert body["result"]["engine"] == "semantic_query_engine_v2"


def test_v240_ai_analyst_semantic_first(tmp_path, monkeypatch):
    fact_id, _ = _v240_make_semantic_sales(tmp_path, monkeypatch)
    r = client.post(f"/api/v1/datasets/{fact_id}/ai/analyze", json={"question":"Donne le chiffre d'affaires par catégorie", "mode":"auto"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["intent"] == "semantic_query"
    assert "semantic_query" in body["provenance"]["tools_executed"]
    semantic_findings = [x for x in body["findings"] if x["evidence"].get("tool") == "semantic_query"]
    assert semantic_findings
    assert semantic_findings[0]["evidence"]["metric_id"] == "revenue"
    assert body["critic"]["status"] == "passed"


def test_v240_semantic_dashboard_cross_filter_and_drill(tmp_path, monkeypatch):
    fact_id, _ = _v240_make_semantic_sales(tmp_path, monkeypatch)
    widgets = [
        {"id":"k1","title":"CA","type":"semantic_kpi","size":"small","config":{"metric_id":"revenue"}},
        {"id":"c1","title":"CA catalogue","type":"semantic_chart","size":"medium","config":{"metric_id":"revenue","hierarchy_id":"catalog","hierarchy_level":0,"chart_type":"bar"}},
        {"id":"rows","title":"Lignes","type":"kpi","size":"small","config":{"metric":"rows"}},
    ]
    preview = client.post(f"/api/v1/datasets/{fact_id}/dashboards/preview", json={"filters":[],"widgets":widgets})
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["semantic_widgets"] == 2
    by_id = {x["id"]: x for x in body["widgets"]}
    assert by_id["k1"]["result"]["value"] == 430.0
    assert by_id["c1"]["result"]["drill"]["next_dimension"] == "subcategory"
    cats = {x["label"]: x["value"] for x in by_id["c1"]["result"]["data"]}
    assert cats == {"A":230.0,"B":200.0}

    drilled_widgets = [
        widgets[0],
        {**widgets[1], "config": {**widgets[1]["config"], "hierarchy_level":1}},
        widgets[2],
    ]
    filtered = client.post(f"/api/v1/datasets/{fact_id}/dashboards/preview", json={
        "filters":[{"source":"drill","dimension":"category","operator":"eq","value":"A"}],
        "widgets":drilled_widgets,
    })
    assert filtered.status_code == 200, filtered.text
    fb = filtered.json(); fby = {x["id"]:x for x in fb["widgets"]}
    assert fb["rows_after"] == 3
    assert fby["rows"]["result"]["value"] == 3
    assert fby["k1"]["result"]["value"] == 230.0
    subs = {x["label"]:x["value"] for x in fby["c1"]["result"]["data"]}
    assert subs == {"A1":150.0,"A2":80.0}


def test_v240_semantic_multihop_snowflake_join(tmp_path, monkeypatch):
    from app.core.config import get_settings
    settings = get_settings(); monkeypatch.setattr(settings, "data_root", tmp_path)
    fact = pd.DataFrame({"product_id":[1,2,3],"revenue":[100.,200.,50.]})
    products = pd.DataFrame({"product_id":[1,2,3],"category_id":[10,20,10]})
    cats = pd.DataFrame({"category_id":[10,20],"sector":["Consumer","Enterprise"]})
    a=client.post("/api/v1/datasets", files={"file":("fact.csv",io.BytesIO(fact.to_csv(index=False).encode()),"text/csv")})
    b=client.post("/api/v1/datasets", files={"file":("products.csv",io.BytesIO(products.to_csv(index=False).encode()),"text/csv")})
    c=client.post("/api/v1/datasets", files={"file":("categories.csv",io.BytesIO(cats.to_csv(index=False).encode()),"text/csv")})
    aid,bid,cid=a.json()["dataset"]["id"],b.json()["dataset"]["id"],c.json()["dataset"]["id"]
    model={
        "tables":[{"id":"base","dataset_id":aid,"role":"fact","active":True},{"id":"product","dataset_id":bid,"role":"dimension","active":True},{"id":"category","dataset_id":cid,"role":"dimension","active":True}],
        "relationships":[
            {"id":"r1","from_table":"base","from_column":"product_id","to_table":"product","to_column":"product_id","cardinality":"many_to_one","join_type":"left","active":True},
            {"id":"r2","from_table":"product","from_column":"category_id","to_table":"category","to_column":"category_id","cardinality":"many_to_one","join_type":"left","active":True},
        ],
        "metrics":[{"id":"revenue","name":"Revenue","label":"Revenue","type":"base","table":"base","column":"revenue","aggregation":"sum","certified":True,"synonyms":[]}],
        "dimensions":[{"id":"sector","table":"category","column":"sector","label":"Sector","kind":"categorical","hidden":False,"certified":True,"synonyms":[]}],
        "hierarchies":[],"business_glossary":[],
    }
    saved=client.post(f"/api/v1/datasets/{aid}/semantic", json=model)
    assert saved.status_code==200, saved.text
    q=client.post(f"/api/v1/datasets/{aid}/semantic/query", json={"metric_id":"revenue","dimensions":["sector"]})
    assert q.status_code==200, q.text
    rows={x["sector"]:x["value"] for x in q.json()["result"]}
    assert rows=={"Enterprise":200.0,"Consumer":150.0}


def test_v250_proactive_inbox_detects_metric_change(tmp_path, monkeypatch):
    from app.core.config import get_settings
    settings = get_settings(); monkeypatch.setattr(settings, "data_root", tmp_path)
    frame = pd.DataFrame({
        "date": ["2026-01-01","2026-02-01","2026-03-01","2026-04-01","2026-05-01","2026-06-01"],
        "revenue": [100.0,102.0,99.0,101.0,103.0,180.0],
        "region": ["A","A","B","B","A","B"],
    })
    up = client.post("/api/v1/datasets", files={"file": ("pulse.csv", io.BytesIO(frame.to_csv(index=False).encode()), "text/csv")})
    assert up.status_code == 200, up.text
    dataset_id = up.json()["dataset"]["id"]
    model = {
        "tables":[{"id":"base","dataset_id":dataset_id,"label":"Sales","role":"fact","active":True}],
        "relationships":[],
        "metrics":[{"id":"revenue","name":"Revenue","label":"Chiffre d'affaires","type":"base","table":"base","column":"revenue","aggregation":"sum","unit":"EUR","description":"","synonyms":["CA"],"certified":True}],
        "dimensions":[
            {"id":"date","table":"base","column":"date","label":"Date","kind":"date","hidden":False,"certified":True,"synonyms":[]},
            {"id":"region","table":"base","column":"region","label":"Région","kind":"categorical","hidden":False,"certified":True,"synonyms":[]},
        ],
        "hierarchies":[],"business_glossary":[],
    }
    saved = client.post(f"/api/v1/datasets/{dataset_id}/semantic", json=model)
    assert saved.status_code == 200, saved.text
    auto = client.post(f"/api/v1/datasets/{dataset_id}/proactive/watches/auto", json={"threshold_pct":20,"time_grain":"month"})
    assert auto.status_code == 200, auto.text
    assert auto.json()["count"] == 1
    scan = client.post(f"/api/v1/datasets/{dataset_id}/proactive/scan", json={"auto_configure":False})
    assert scan.status_code == 200, scan.text
    body = scan.json()
    assert body["new_alerts"] == 1
    alert = body["alerts"][0]
    assert alert["metric_id"] == "revenue"
    assert alert["severity"] in {"high","critical"}
    assert alert["delta_pct"] > 50
    assert any(x["type"] == "semantic_breakdown" for x in alert["investigations"])
    inbox = client.get(f"/api/v1/datasets/{dataset_id}/proactive/inbox?status=open")
    assert inbox.status_code == 200
    assert inbox.json()["count"] == 1
    assert inbox.json()["summary"]["open_alerts"] == 1


def test_v250_proactive_alert_dedup_and_status(tmp_path, monkeypatch):
    from app.core.config import get_settings
    settings = get_settings(); monkeypatch.setattr(settings, "data_root", tmp_path)
    frame = pd.DataFrame({
        "date": ["2026-01-01","2026-02-01","2026-03-01","2026-04-01","2026-05-01"],
        "sales": [10.0,10.5,9.8,10.2,30.0],
    })
    up = client.post("/api/v1/datasets", files={"file": ("watch.csv", io.BytesIO(frame.to_csv(index=False).encode()), "text/csv")})
    dataset_id = up.json()["dataset"]["id"]
    sem={
        "tables":[{"id":"base","dataset_id":dataset_id,"role":"fact","active":True}],"relationships":[],
        "metrics":[{"id":"sales","name":"Sales","label":"Sales","type":"base","table":"base","column":"sales","aggregation":"sum","certified":True,"synonyms":[]}],
        "dimensions":[{"id":"date","table":"base","column":"date","label":"Date","kind":"date","hidden":False,"certified":True,"synonyms":[]}],
        "hierarchies":[],"business_glossary":[],
    }
    assert client.post(f"/api/v1/datasets/{dataset_id}/semantic", json=sem).status_code == 200
    first = client.post(f"/api/v1/datasets/{dataset_id}/proactive/scan", json={"auto_configure":True})
    assert first.status_code == 200, first.text
    second = client.post(f"/api/v1/datasets/{dataset_id}/proactive/scan", json={"auto_configure":True})
    assert second.status_code == 200
    assert second.json()["new_alerts"] == 0
    inbox = client.get(f"/api/v1/datasets/{dataset_id}/proactive/inbox?status=open").json()
    assert inbox["count"] == 1
    alert_id = inbox["alerts"][0]["id"]
    changed = client.post(f"/api/v1/datasets/{dataset_id}/proactive/inbox/{alert_id}/status", json={"status":"acknowledged"})
    assert changed.status_code == 200
    assert changed.json()["status"] == "acknowledged"
    assert client.get(f"/api/v1/datasets/{dataset_id}/proactive/inbox?status=open").json()["count"] == 0
    assert client.get(f"/api/v1/datasets/{dataset_id}/proactive/inbox?status=acknowledged").json()["count"] == 1


def test_v260_review_workflow_comments_and_approval(tmp_path, monkeypatch):
    from app.core.config import get_settings
    from app.services import metadata_store
    settings=get_settings(); monkeypatch.setattr(settings,"data_root",tmp_path); monkeypatch.setattr(settings,"database_url",f"sqlite:///{tmp_path/'reviews.db'}")
    metadata_store._ENGINES.clear(); metadata_store._SELECTED_BACKENDS.clear()
    boot=client.post('/api/v1/auth/bootstrap',json={"email":"owner260@datavision.local","password":"EnterprisePass123!","display_name":"Owner 260","organization_name":"Review Org"})
    assert boot.status_code==200,boot.text
    token=boot.json()['access_token']; ws=boot.json()['workspace_id']; owner=boot.json()['user']['id']; h={"Authorization":f"Bearer {token}"}
    ds=client.post(f'/api/v1/workspaces/{ws}/members',headers=h,json={"email":"reviewer260@datavision.local","role":"data_scientist","display_name":"Reviewer 260","password":"ReviewerPass123!"})
    assert ds.status_code==200,ds.text
    reviewer_id=ds.json()['member']['id']
    r=client.post(f'/api/v1/workspaces/{ws}/reviews',headers=h,json={
        "resource_type":"semantic_metric","resource_id":"revenue","title":"Certifier Revenue","description":"Vérifier définition et agrégation.",
        "dataset_id":"dataset-x","resource_version":"semantic-v3","priority":"high","owner_user_id":owner,"reviewer_user_id":reviewer_id,
        "snapshot":{"metric_id":"revenue","aggregation":"sum"}
    })
    assert r.status_code==200,r.text
    review_id=r.json()['review']['id']; assert r.json()['review']['status']=='draft'
    submitted=client.post(f'/api/v1/workspaces/{ws}/reviews/{review_id}/transition',headers=h,json={"action":"submit","note":"Prête pour revue"})
    assert submitted.status_code==200,submitted.text
    assert submitted.json()['review']['status']=='in_review'
    login=client.post('/api/v1/auth/login',json={"email":"reviewer260@datavision.local","password":"ReviewerPass123!"})
    rh={"Authorization":f"Bearer {login.json()['access_token']}"}
    commented=client.post(f'/api/v1/workspaces/{ws}/reviews/{review_id}/comments',headers=rh,json={"body":"Définition vérifiée. @owner260 merci de confirmer la source."})
    assert commented.status_code==200,commented.text
    assert commented.json()['review']['comment_count']==1
    approved=client.post(f'/api/v1/workspaces/{ws}/reviews/{review_id}/transition',headers=rh,json={"action":"approve","note":"Définition et agrégation validées."})
    assert approved.status_code==200,approved.text
    body=approved.json()['review']; assert body['status']=='approved'; assert body['decided_at']
    assert any(e['action']=='approve' for e in body['events'])
    summary=client.get(f'/api/v1/workspaces/{ws}/reviews/summary',headers=h)
    assert summary.status_code==200; assert summary.json()['by_status']['approved']==1
    notifications=client.get(f'/api/v1/workspaces/{ws}/collaboration/notifications',headers=h)
    assert notifications.status_code==200
    assert any(n['notification_type'] in {'mention','review_approve'} for n in notifications.json()['notifications'])


def test_v260_review_changes_requested_and_resolution(tmp_path, monkeypatch):
    from app.core.config import get_settings
    from app.services import metadata_store
    settings=get_settings(); monkeypatch.setattr(settings,"data_root",tmp_path); monkeypatch.setattr(settings,"database_url",f"sqlite:///{tmp_path/'review-changes.db'}")
    metadata_store._ENGINES.clear(); metadata_store._SELECTED_BACKENDS.clear()
    boot=client.post('/api/v1/auth/bootstrap',json={"email":"ownerchanges@datavision.local","password":"EnterprisePass123!","display_name":"Owner","organization_name":"Changes Org"})
    h={"Authorization":f"Bearer {boot.json()['access_token']}"}; ws=boot.json()['workspace_id']
    review=client.post(f'/api/v1/workspaces/{ws}/reviews',headers=h,json={"resource_type":"report","resource_id":"report-42","title":"Rapport Q3","priority":"normal"}).json()['review']
    rid=review['id']
    assert client.post(f'/api/v1/workspaces/{ws}/reviews/{rid}/transition',headers=h,json={"action":"submit"}).status_code==200
    comment=client.post(f'/api/v1/workspaces/{ws}/reviews/{rid}/comments',headers=h,json={"body":"Ajouter la méthodologie et la provenance."})
    cid=comment.json()['review']['comments'][0]['id']
    changed=client.post(f'/api/v1/workspaces/{ws}/reviews/{rid}/transition',headers=h,json={"action":"request_changes","note":"Méthodologie incomplète"})
    assert changed.status_code==200; assert changed.json()['review']['status']=='changes_requested'
    resolved=client.post(f'/api/v1/workspaces/{ws}/reviews/{rid}/comments/{cid}/resolve',headers=h,json={"resolved":True})
    assert resolved.status_code==200; assert resolved.json()['review']['comments'][0]['resolved'] is True
    reopened=client.post(f'/api/v1/workspaces/{ws}/reviews/{rid}/transition',headers=h,json={"action":"reopen","note":"Corrections intégrées"})
    assert reopened.status_code==200; assert reopened.json()['review']['status']=='in_review'


def test_v260_viewer_cannot_create_review_but_can_comment(tmp_path, monkeypatch):
    from app.core.config import get_settings
    from app.services import metadata_store
    settings=get_settings(); monkeypatch.setattr(settings,"data_root",tmp_path); monkeypatch.setattr(settings,"database_url",f"sqlite:///{tmp_path/'review-viewer.db'}")
    metadata_store._ENGINES.clear(); metadata_store._SELECTED_BACKENDS.clear()
    boot=client.post('/api/v1/auth/bootstrap',json={"email":"owner-view@datavision.local","password":"EnterprisePass123!","display_name":"Owner","organization_name":"Viewer Org"})
    oh={"Authorization":f"Bearer {boot.json()['access_token']}"}; ws=boot.json()['workspace_id']
    client.post(f'/api/v1/workspaces/{ws}/members',headers=oh,json={"email":"viewer260@datavision.local","role":"viewer","display_name":"Viewer","password":"ViewerPass123!"})
    review=client.post(f'/api/v1/workspaces/{ws}/reviews',headers=oh,json={"resource_type":"dashboard","resource_id":"dash-1","title":"Dashboard exécutif"}).json()['review']
    rid=review['id']; client.post(f'/api/v1/workspaces/{ws}/reviews/{rid}/transition',headers=oh,json={"action":"submit"})
    login=client.post('/api/v1/auth/login',json={"email":"viewer260@datavision.local","password":"ViewerPass123!"})
    vh={"Authorization":f"Bearer {login.json()['access_token']}"}
    denied=client.post(f'/api/v1/workspaces/{ws}/reviews',headers=vh,json={"resource_type":"report","resource_id":"r","title":"Interdit"})
    assert denied.status_code==403
    comment=client.post(f'/api/v1/workspaces/{ws}/reviews/{rid}/comments',headers=vh,json={"body":"La lecture est claire pour moi."})
    assert comment.status_code==200,comment.text


def test_v260_approved_review_can_be_certified_with_expiry(tmp_path, monkeypatch):
    from app.core.config import get_settings
    from app.services import metadata_store
    settings=get_settings(); monkeypatch.setattr(settings,"data_root",tmp_path); monkeypatch.setattr(settings,"database_url",f"sqlite:///{tmp_path/'review-cert.db'}")
    metadata_store._ENGINES.clear(); metadata_store._SELECTED_BACKENDS.clear()
    boot=client.post('/api/v1/auth/bootstrap',json={"email":"ownercert@datavision.local","password":"EnterprisePass123!","display_name":"Owner","organization_name":"Cert Org"})
    h={"Authorization":f"Bearer {boot.json()['access_token']}"}; ws=boot.json()['workspace_id']
    r=client.post(f'/api/v1/workspaces/{ws}/reviews',headers=h,json={"resource_type":"semantic_metric","resource_id":"revenue","title":"Revenue officiel"})
    rid=r.json()['review']['id']
    assert client.post(f'/api/v1/workspaces/{ws}/reviews/{rid}/transition',headers=h,json={"action":"submit"}).status_code==200
    assert client.post(f'/api/v1/workspaces/{ws}/reviews/{rid}/transition',headers=h,json={"action":"approve","note":"validé"}).status_code==200
    cert=client.post(f'/api/v1/workspaces/{ws}/reviews/{rid}/certify',headers=h,json={"valid_until":"2027-12-31","notes":"Certification annuelle"})
    assert cert.status_code==200,cert.text
    body=cert.json()['certification']; assert body['status']=='active'; assert body['valid_until']=='2027-12-31'; assert body['resource_id']=='revenue'
    listed=client.get(f'/api/v1/workspaces/{ws}/certifications',headers=h)
    assert listed.status_code==200; assert len(listed.json()['certifications'])==1
    summary=client.get(f'/api/v1/workspaces/{ws}/reviews/summary',headers=h).json()
    assert summary['active_certifications']==1
    revoked=client.post(f'/api/v1/workspaces/{ws}/certifications/{body["id"]}/revoke',headers=h,json={"note":"Remplacée"})
    assert revoked.status_code==200; assert revoked.json()['certification']['status']=='revoked'


def test_v270_connector_refresh_incremental_freshness_and_schedule(tmp_path, monkeypatch):
    from app.core.config import get_settings
    from app.services import metadata_store, connector_service
    from app.services.storage import load_dataframe_raw

    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path/'connectors.db'}")
    monkeypatch.setattr(settings, "auth_secret", "test-v270-secret-with-enough-entropy-123456")
    metadata_store._ENGINES.clear(); metadata_store._SELECTED_BACKENDS.clear()

    boot = client.post('/api/v1/auth/bootstrap', json={
        "email":"connector-owner@datavision.local","password":"EnterprisePass123!",
        "display_name":"Connector Owner","organization_name":"Connector Org",
    })
    assert boot.status_code == 200, boot.text
    token = boot.json()['access_token']; ws = boot.json()['workspace_id']
    h = {"Authorization": f"Bearer {token}"}

    created = client.post(f'/api/v1/workspaces/{ws}/connectors', headers=h, json={
        "name":"Warehouse","connector_type":"postgresql","host":"db.internal","port":5432,
        "database":"analytics","username":"reader","password":"UltraSecretPassword!","ssl_mode":"require"
    })
    assert created.status_code == 200, created.text
    connector = created.json()['connector']; connector_id = connector['id']
    assert connector['has_credentials'] is True
    assert 'password_ciphertext' not in connector
    stored = metadata_store.fetch_one('SELECT password_ciphertext FROM data_connectors WHERE id=:id', {'id':connector_id})
    assert stored and 'UltraSecretPassword!' not in stored['password_ciphertext']

    source_resp = client.post(f'/api/v1/workspaces/{ws}/sources', headers=h, json={
        "connector_id":connector_id,"name":"Orders","source_kind":"table","table_name":"public.orders",
        "refresh_mode":"incremental","incremental_column":"id","freshness_sla_minutes":60,"schema_drift_policy":"warn"
    })
    assert source_resp.status_code == 200, source_resp.text
    source_id = source_resp.json()['source']['id']

    def fake_fetch(workspace_id, sid, *, watermark=None, limit=None):
        assert workspace_id == ws and sid == source_id
        if limit is not None:
            return pd.DataFrame({"id":[1,2],"amount":[10.0,20.0]})
        if watermark is None:
            return pd.DataFrame({"id":[1,2],"amount":[10.0,20.0]})
        assert int(watermark) == 2
        return pd.DataFrame({"id":[3],"amount":[30.0]})
    monkeypatch.setattr(connector_service, 'fetch_source_frame', fake_fetch)

    preview = client.get(f'/api/v1/workspaces/{ws}/sources/{source_id}/preview?limit=2', headers=h)
    assert preview.status_code == 200, preview.text
    assert preview.json()['returned_rows'] == 2

    first = client.post(f'/api/v1/workspaces/{ws}/sources/{source_id}/refresh', headers=h, json={"background":False})
    assert first.status_code == 200, first.text
    r1 = first.json()['refresh']; assert r1['rows_fetched'] == 2 and r1['watermark_after'] == 2
    first_dataset = r1['dataset_id']; assert len(load_dataframe_raw(first_dataset)) == 2

    second = client.post(f'/api/v1/workspaces/{ws}/sources/{source_id}/refresh', headers=h, json={"background":False})
    assert second.status_code == 200, second.text
    r2 = second.json()['refresh']; assert r2['rows_fetched'] == 1 and r2['watermark_after'] == 3
    second_dataset = r2['dataset_id']; frame = load_dataframe_raw(second_dataset)
    assert len(frame) == 3 and frame['amount'].sum() == 60.0

    schedule = client.post(f'/api/v1/workspaces/{ws}/sources/{source_id}/schedule', headers=h, json={"enabled":True,"interval_minutes":60})
    assert schedule.status_code == 200, schedule.text
    assert schedule.json()['schedule']['enabled'] is True

    # Force the schedule due and verify atomic claiming: first worker claims, second sees nothing due.
    metadata_store.execute("UPDATE refresh_schedules SET next_run_at='2020-01-01T00:00:00+00:00' WHERE source_id=:id", {'id':source_id})
    claimed = connector_service.claim_due_schedules()
    assert len(claimed) == 1 and claimed[0]['source_id'] == source_id
    assert connector_service.claim_due_schedules() == []

    health = client.get(f'/api/v1/workspaces/{ws}/connectors/health', headers=h)
    assert health.status_code == 200, health.text
    assert health.json()['connectors'] == 1 and health.json()['sources'] == 1
    assert health.json()['freshness']['fresh'] == 1
    runs = client.get(f'/api/v1/workspaces/{ws}/refresh-runs?source_id={source_id}', headers=h)
    assert runs.status_code == 200 and len(runs.json()['runs']) == 2
    assert all(x['status'] == 'completed' for x in runs.json()['runs'])


def test_v270_schema_drift_fail_policy_blocks_destructive_refresh(tmp_path, monkeypatch):
    from app.core.config import get_settings
    from app.services import metadata_store, connector_service

    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path/'connector-drift.db'}")
    monkeypatch.setattr(settings, "auth_secret", "test-v270-drift-secret-with-enough-entropy")
    metadata_store._ENGINES.clear(); metadata_store._SELECTED_BACKENDS.clear()
    boot = client.post('/api/v1/auth/bootstrap', json={
        "email":"drift-owner@datavision.local","password":"EnterprisePass123!","display_name":"Drift Owner","organization_name":"Drift Org"
    })
    token=boot.json()['access_token']; ws=boot.json()['workspace_id']; h={"Authorization":f"Bearer {token}"}
    c=client.post(f'/api/v1/workspaces/{ws}/connectors',headers=h,json={"name":"DB","connector_type":"mysql","host":"mysql.internal","database":"prod","username":"reader","password":"secret","ssl_mode":"prefer"})
    assert c.status_code==200,c.text
    sid=client.post(f'/api/v1/workspaces/{ws}/sources',headers=h,json={
        "connector_id":c.json()['connector']['id'],"name":"Customers","source_kind":"table","table_name":"customers",
        "refresh_mode":"full","schema_drift_policy":"fail"
    }).json()['source']['id']
    calls={'n':0}
    def fake_fetch(*args, **kwargs):
        calls['n']+=1
        if calls['n']==1: return pd.DataFrame({"id":[1,2],"name":["A","B"]})
        return pd.DataFrame({"id":[1,2],"renamed":["A","B"]})
    monkeypatch.setattr(connector_service,'fetch_source_frame',fake_fetch)
    first=client.post(f'/api/v1/workspaces/{ws}/sources/{sid}/refresh',headers=h,json={"background":False})
    assert first.status_code==200,first.text
    second=client.post(f'/api/v1/workspaces/{ws}/sources/{sid}/refresh',headers=h,json={"background":False})
    assert second.status_code==400,second.text
    source=connector_service.get_source(ws,sid)
    assert source['status']=='error'
    runs=connector_service.get_refresh_runs(ws,sid)
    assert runs[0]['status']=='failed'
    assert 'Schema drift' in (runs[0]['error'] or '')


def test_v270_connector_refresh_background_job_is_tenant_aware(tmp_path, monkeypatch):
    from app.core.config import get_settings
    from app.services import metadata_store, connector_service, job_service
    settings=get_settings(); monkeypatch.setattr(settings,'data_root',tmp_path); monkeypatch.setattr(settings,'database_url',f"sqlite:///{tmp_path/'connector-job.db'}"); monkeypatch.setattr(settings,'auth_secret','test-v270-job-secret-with-enough-entropy')
    metadata_store._ENGINES.clear(); metadata_store._SELECTED_BACKENDS.clear()
    class FakeRedis:
        def __init__(self): self.items=[]
        def rpush(self,key,value): self.items.append((key,value)); return len(self.items)
    fake=FakeRedis(); monkeypatch.setattr(job_service,'_redis',lambda:fake)
    boot=client.post('/api/v1/auth/bootstrap',json={'email':'job-connector@datavision.local','password':'EnterprisePass123!','display_name':'Owner','organization_name':'Job Connector Org'})
    token=boot.json()['access_token']; ws=boot.json()['workspace_id']; h={'Authorization':f'Bearer {token}'}
    conn=client.post(f'/api/v1/workspaces/{ws}/connectors',headers=h,json={'name':'PG','connector_type':'postgresql','host':'pg.internal','database':'dw','username':'reader','password':'secret','ssl_mode':'require'}).json()['connector']
    source=client.post(f'/api/v1/workspaces/{ws}/sources',headers=h,json={'connector_id':conn['id'],'name':'Facts','source_kind':'table','table_name':'public.facts','refresh_mode':'full'}).json()['source']
    monkeypatch.setattr(connector_service,'fetch_source_frame',lambda *a,**k: pd.DataFrame({'id':[1,2,3],'value':[10,20,30]}))
    queued=client.post(f'/api/v1/workspaces/{ws}/sources/{source["id"]}/refresh',headers=h,json={'background':True})
    assert queued.status_code==200,queued.text
    job_id=queued.json()['job']['id']; assert fake.items and fake.items[-1][1]==job_id
    completed=job_service.run_job(job_id)
    assert completed['status']=='completed',completed
    assert completed['result']['rows_fetched']==3
    current=connector_service.get_source(ws,source['id'])
    assert current['dataset_id']==completed['result']['dataset_id']
    bound=metadata_store.fetch_one('SELECT dataset_id FROM workspace_datasets WHERE workspace_id=:ws AND dataset_id=:ds',{'ws':ws,'ds':current['dataset_id']})
    assert bound is not None


def test_v270_connector_catalog_hides_infrastructure_from_analyst(tmp_path, monkeypatch):
    from app.core.config import get_settings
    from app.services import metadata_store
    settings=get_settings(); monkeypatch.setattr(settings,'data_root',tmp_path); monkeypatch.setattr(settings,'database_url',f"sqlite:///{tmp_path/'connector-sanitize.db'}"); monkeypatch.setattr(settings,'auth_secret','test-v270-sanitize-secret-with-enough-entropy')
    metadata_store._ENGINES.clear(); metadata_store._SELECTED_BACKENDS.clear()
    boot=client.post('/api/v1/auth/bootstrap',json={'email':'owner-sanitize@datavision.local','password':'EnterprisePass123!','display_name':'Owner','organization_name':'Sanitize Org'})
    owner_token=boot.json()['access_token']; ws=boot.json()['workspace_id']; oh={'Authorization':f'Bearer {owner_token}'}
    conn=client.post(f'/api/v1/workspaces/{ws}/connectors',headers=oh,json={'name':'Sensitive Warehouse','connector_type':'postgresql','host':'secret.internal','database':'finance','username':'private_reader','password':'verysecret','ssl_mode':'require'}).json()['connector']
    source=client.post(f'/api/v1/workspaces/{ws}/sources',headers=oh,json={'connector_id':conn['id'],'name':'Finance source','source_kind':'query','query':'SELECT id, amount FROM finance_ledger','refresh_mode':'full'}).json()['source']
    member=client.post(f'/api/v1/workspaces/{ws}/members',headers=oh,json={'email':'analyst-sanitize@datavision.local','role':'analyst','display_name':'Analyst','password':'AnalystPass123!'})
    assert member.status_code==200
    login=client.post('/api/v1/auth/login',json={'email':'analyst-sanitize@datavision.local','password':'AnalystPass123!'})
    ah={'Authorization':f"Bearer {login.json()['access_token']}"}
    catalog=client.get(f'/api/v1/workspaces/{ws}/connectors',headers=ah)
    assert catalog.status_code==200,catalog.text
    safe=catalog.json()['connectors'][0]
    assert 'host' not in safe and 'username' not in safe and 'database_name' not in safe
    safe_source=catalog.json()['sources'][0]
    assert 'source_query' not in safe_source
    denied=client.get(f'/api/v1/workspaces/{ws}/sources/{source["id"]}/preview',headers=ah)
    assert denied.status_code==403
