import time

import pandas as pd

from app.core.config import get_settings
from app.services.storage import save_dataframe_source


def _configure(tmp_path, monkeypatch):
    import app.services.metadata_store as metadata_store
    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'metadata.db'}")
    monkeypatch.setattr(settings, "metadata_fallback_sqlite", True)
    metadata_store._ENGINES.clear()
    metadata_store._SELECTED_BACKENDS.clear()


def _wait(runtime, run_id, timeout=5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        run = runtime.get_analysis_run(run_id)
        if run["status"] in {"completed", "failed", "cancelled"}:
            return run
        time.sleep(0.03)
    raise AssertionError("analysis run timed out")


def _result(dataset_id, question="Q"):
    return {
        "session_id": "session-test",
        "question": question,
        "intent": "overview",
        "mode": "auto",
        "answer": "Résultat déterministe.",
        "plan": [],
        "executions": [],
        "findings": [],
        "artifacts": {},
        "critic": {"status": "passed", "checks": [], "failed_tools": []},
        "provenance": {
            "dataset_id": dataset_id,
            "dataset_name": "sample.csv",
            "dataset_version": 1,
            "executed_at": "2026-09-19T12:00:00+00:00",
            "tools_executed": [],
            "calculation_policy": "deterministic_tools_only",
            "llm_used_for_numeric_calculation": False,
            "semantic_grounding": True,
            "semantic_model_version": 1,
            "semantic_matches": [],
        },
    }


def test_ai_runtime_stream_progress_and_cache(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    import app.services.ai_analysis_runtime as runtime

    source = save_dataframe_source(
        pd.DataFrame({"x": range(40), "y": [v * 2 for v in range(40)]}),
        "sample.csv",
    )
    calls = {"n": 0}

    def fake_analyze(df, ctx, *, progress_callback=None, cancel_check=None):
        calls["n"] += 1
        if progress_callback:
            progress_callback({"progress": 35, "stage": "Profilage", "tool": "profile"})
            progress_callback({"progress": 75, "stage": "Corrélations", "tool": "correlations"})
        return _result(source["id"], ctx.question)

    monkeypatch.setattr(runtime, "analyze_dataset", fake_analyze)
    payload = {"question": "Analyse le dataset", "mode": "auto", "horizon": 12}
    first = runtime.submit_analysis_run(source["id"], payload, use_cache=True)
    completed = _wait(runtime, first["id"])
    assert completed["status"] == "completed"
    assert completed["progress"] == 100
    assert completed["result"]["runtime"]["cache_hit"] is False
    assert calls["n"] == 1

    second = runtime.submit_analysis_run(source["id"], payload, use_cache=True)
    assert second["status"] == "completed"
    assert second["cached"] is True
    assert second["result"]["runtime"]["cache_hit"] is True
    assert calls["n"] == 1


def test_ai_runtime_cancellation_is_cooperative(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    import app.services.ai_analysis_runtime as runtime
    from app.services.ai_analyst import AnalysisCancelled

    source = save_dataframe_source(
        pd.DataFrame({"x": range(80), "y": range(80)}),
        "cancel.csv",
    )

    def slow_analyze(df, ctx, *, progress_callback=None, cancel_check=None):
        for index in range(30):
            if cancel_check and cancel_check():
                raise AnalysisCancelled("cancelled")
            if progress_callback:
                progress_callback({
                    "progress": 10 + index,
                    "stage": f"Étape {index}",
                    "tool": "slow_tool",
                })
            time.sleep(0.02)
        return _result(source["id"], ctx.question)

    monkeypatch.setattr(runtime, "analyze_dataset", slow_analyze)
    run = runtime.submit_analysis_run(
        source["id"],
        {"question": "Analyse lente", "mode": "deep"},
        use_cache=False,
    )
    time.sleep(0.08)
    requested = runtime.cancel_analysis_run(run["id"])
    assert requested["status"] in {"cancel_requested", "cancelled"}
    final = _wait(runtime, run["id"])
    assert final["status"] == "cancelled"


def test_identical_inflight_requests_are_deduplicated(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    import app.services.ai_analysis_runtime as runtime

    source = save_dataframe_source(
        pd.DataFrame({"x": range(60), "y": range(60)}),
        "dedup.csv",
    )

    def slow_analyze(df, ctx, *, progress_callback=None, cancel_check=None):
        time.sleep(0.2)
        return _result(source["id"], ctx.question)

    monkeypatch.setattr(runtime, "analyze_dataset", slow_analyze)
    payload = {"question": "Même analyse", "mode": "auto"}
    first = runtime.submit_analysis_run(source["id"], payload, use_cache=False)
    second = runtime.submit_analysis_run(source["id"], payload, use_cache=False)
    assert second["id"] == first["id"]
    assert _wait(runtime, first["id"])["status"] == "completed"
