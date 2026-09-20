from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.assistant.activity import ActivityMonitor
from app.assistant.models import AssistantContext, AssistantEvent, AgentTurnRun, AgentTurnStep, AgentIntent
from app.assistant.proactive import ProactiveAlertGate, decorate_proactive_alerts, evaluate_proactive_event
from app.assistant.runtime import build_orchestrator
from app.assistant.tools import build_default_registry
from app.assistant.host_v212 import V212HostAuthorization, bind_v212_host
from app.assistant.executor import GovernedToolExecutor
from app.assistant.action_runs import ActionLifecycleManager, ActionRunStore
from app.assistant.turn_runs import AgentTurnRunStore
from app.assistant.memory import SessionMemoryStore
from app.assistant.planner_runtime import DeterministicPlanner
from app.assistant.critic import DeterministicCritic
from app.assistant.recovery import RecoveryPolicy


def test_proactive_alerts_are_fingerprinted_and_throttled():
    event = AssistantEvent(type="analysis.failed", payload={"reason": "bad input"})
    alerts = decorate_proactive_alerts(
        evaluate_proactive_event(event, AssistantContext(workspaceId="ws")), event
    )
    assert alerts and alerts[0].fingerprint
    assert alerts[0].sourceEventId == event.id
    gate = ProactiveAlertGate()
    now = datetime.now(timezone.utc)
    assert len(gate.filter(alerts, now=now)) == 1
    assert gate.filter(alerts, now=now + timedelta(seconds=5)) == []
    assert len(gate.filter(alerts, now=now + timedelta(seconds=alerts[0].cooldownSeconds + 1))) == 1


def test_slow_query_and_overfit_have_deterministic_advice():
    slow = evaluate_proactive_event(
        AssistantEvent(type="query.slow", payload={"duration_seconds": 12.4}),
        AssistantContext(),
    )
    assert slow and slow[0].action and slow[0].severity == "suggestion"

    overfit = evaluate_proactive_event(
        AssistantEvent(type="ml.overfit.detected", payload={"train_score": .98, "validation_score": .71}),
        AssistantContext(),
    )
    assert overfit and overfit[0].severity == "warning"
    assert "0.980" in overfit[0].message


def test_activity_monitor_detects_stalled_workflow_and_success_resets_retry_loop():
    monitor = ActivityMonitor()
    base = datetime.now(timezone.utc)
    for idx in range(4):
        monitor.add(AssistantEvent(
            type="analysis.failed",
            timestamp=base + timedelta(seconds=idx),
            payload={"code": f"ERR_{idx}", "screen": "statistics"},
        ))
    signals = monitor.detect(now=base + timedelta(seconds=5))
    assert any(item.kind == "stalled_workflow" for item in signals)

    monitor = ActivityMonitor()
    for idx in range(3):
        monitor.add(AssistantEvent(type="analysis.retried", timestamp=base + timedelta(seconds=idx)))
    monitor.add(AssistantEvent(type="analysis.completed", timestamp=base + timedelta(seconds=4)))
    signals = monitor.detect(now=base + timedelta(seconds=5))
    assert not any(item.kind == "retry_loop" for item in signals)


def test_orchestrator_exposes_generated_artifact_attachment(tmp_path):
    registry = build_default_registry()
    bind_v212_host(registry)
    auth = V212HostAuthorization()
    orchestrator = build_orchestrator(
        registry=registry,
        authorization=auth,
        action_lifecycle=ActionLifecycleManager(executor=GovernedToolExecutor(registry, auth), store=ActionRunStore()),
        turn_store=AgentTurnRunStore(),
        planner=DeterministicPlanner(),
        memory=SessionMemoryStore(),
    )
    artifact = tmp_path / "report.pdf"
    artifact.write_bytes(b"%PDF-test")
    run = AgentTurnRun(
        session_id="s",
        request_message="report",
        context=AssistantContext(),
        intent=AgentIntent(name="report", confidence=1.0),
        status="completed",
        final_message="ok",
        steps=[AgentTurnStep(
            id="step-file",
            tool="generate_report",
            label="Rapport",
            status="succeeded",
            result={"artifact_path": str(artifact), "report_id": "r1", "format": "pdf"},
        )],
    )
    response = orchestrator._response_from_run(run)
    assert len(response.attachments) == 1
    assert response.attachments[0].name == "report.pdf"
    assert response.attachments[0].download_path.endswith(f"/{run.id}/artifacts/step-file")
