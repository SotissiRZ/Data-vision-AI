from app.assistant.planner_config import build_planner_from_env
from app.assistant.planner_runtime import DeterministicPlanner
from app.assistant.tools import build_default_registry


def test_default_planner_is_deterministic(monkeypatch):
    monkeypatch.delenv("DATAVISION_AI_PLANNER_MODE", raising=False)
    planner = build_planner_from_env(build_default_registry())
    assert isinstance(planner, DeterministicPlanner)
