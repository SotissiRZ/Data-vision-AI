from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, AsyncIterator
from uuid import uuid4


@dataclass
class RealtimeMessage:
    id: str
    type: str
    payload: dict[str, Any]
    timestamp: str

    @classmethod
    def create(cls, type: str, payload: dict[str, Any]) -> "RealtimeMessage":
        return cls(
            id=str(uuid4()),
            type=type,
            payload=payload,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )


class AssistantRealtimeHub:
    def __init__(self) -> None:
        self._queues: dict[str, set[asyncio.Queue[RealtimeMessage]]] = defaultdict(set)

    async def publish(self, channel: str, message: RealtimeMessage) -> None:
        for queue in tuple(self._queues.get(channel, ())):
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                # Best effort: stale UI consumers must not block the app.
                pass

    async def subscribe(self, channel: str) -> AsyncIterator[str]:
        queue: asyncio.Queue[RealtimeMessage] = asyncio.Queue(maxsize=100)
        self._queues[channel].add(queue)
        try:
            # initial event prevents some proxies from considering the stream idle
            yield "event: ready\ndata: {}\n\n"
            while True:
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=20)
                    body = json.dumps(asdict(message), ensure_ascii=False)
                    yield f"event: {message.type}\ndata: {body}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            self._queues[channel].discard(queue)
