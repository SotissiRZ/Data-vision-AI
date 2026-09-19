from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_ai_runtime_routes_and_sse_exist():
    routes = (ROOT / "backend/app/api/routes/datasets.py").read_text()
    assert '/{dataset_id}/ai/analyze/run' in routes
    assert '/{dataset_id}/ai/runs/{run_id}/events' in routes
    assert '/{dataset_id}/ai/runs/{run_id}/cancel' in routes
    assert 'StreamingResponse' in routes


def test_ai_analyst_supports_progress_and_cancellation():
    service = (ROOT / "backend/app/services/ai_analyst.py").read_text()
    assert 'progress_callback:' in service
    assert 'cancel_check:' in service
    assert 'class AnalysisCancelled' in service
    assert 'ensure_not_cancelled()' in service


def test_frontend_uses_streaming_runtime():
    page = (ROOT / "frontend/app/page.tsx").read_text()
    api = (ROOT / "frontend/lib/api.ts").read_text()
    assert 'startAIAnalysisRun' in page
    assert 'streamAIAnalysisRun' in page
    assert 'cancelAIAnalysisRun' in page
    assert 'Réutiliser un résultat identique' in page
    assert 'ai-live-progress' in page
    assert 'text/event-stream' in api
