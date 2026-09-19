from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import RLock
from typing import Any


@dataclass
class ModelCallRecord:
    provider_id: str
    model: str
    task: str
    success: bool
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost_usd: float | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class ModelCallRecorder:
    def __init__(self, max_records: int = 1000) -> None:
        self._records: list[ModelCallRecord] = []
        self._max_records = max_records
        self._lock = RLock()

    def add(self, record: ModelCallRecord) -> None:
        with self._lock:
            self._records.append(record)
            self._records = self._records[-self._max_records:]

    def list(self) -> list[ModelCallRecord]:
        with self._lock:
            return list(self._records)
