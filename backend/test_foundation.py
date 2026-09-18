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
