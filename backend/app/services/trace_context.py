from __future__ import annotations

import re
import secrets
import uuid
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Mapping

_TRACEPARENT_RE = re.compile(r"^(?P<version>[0-9a-f]{2})-(?P<trace>[0-9a-f]{32})-(?P<span>[0-9a-f]{16})-(?P<flags>[0-9a-f]{2})$", re.I)
_current_trace: ContextVar["TraceContext | None"] = ContextVar("datavision_trace_context", default=None)


@dataclass(frozen=True)
class TraceContext:
    trace_id: str
    span_id: str
    parent_span_id: str | None
    trace_flags: str
    request_id: str

    @property
    def traceparent(self) -> str:
        return f"00-{self.trace_id}-{self.span_id}-{self.trace_flags}"

    def as_dict(self) -> dict[str, str | None]:
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "trace_flags": self.trace_flags,
            "request_id": self.request_id,
            "traceparent": self.traceparent,
        }


def _valid_nonzero_hex(value: str) -> bool:
    return bool(value) and any(ch != "0" for ch in value.lower())


def new_trace_context(headers: Mapping[str, str]) -> TraceContext:
    raw = str(headers.get("traceparent") or "").strip().lower()
    match = _TRACEPARENT_RE.match(raw)
    parent_span_id: str | None = None
    flags = "01"
    if match and match.group("version") != "ff" and _valid_nonzero_hex(match.group("trace")) and _valid_nonzero_hex(match.group("span")):
        trace_id = match.group("trace")
        parent_span_id = match.group("span")
        flags = match.group("flags")
    else:
        trace_id = secrets.token_hex(16)
    request_id = str(headers.get("x-request-id") or "").strip()[:128] or str(uuid.uuid4())
    return TraceContext(
        trace_id=trace_id,
        span_id=secrets.token_hex(8),
        parent_span_id=parent_span_id,
        trace_flags=flags,
        request_id=request_id,
    )


def set_trace_context(ctx: TraceContext) -> Token:
    return _current_trace.set(ctx)


def reset_trace_context(token: Token) -> None:
    _current_trace.reset(token)


def current_trace_context() -> TraceContext | None:
    return _current_trace.get()
