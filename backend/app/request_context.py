from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass


request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
correlation_id_var: ContextVar[str | None] = ContextVar("correlation_id", default=None)
session_id_var: ContextVar[str | None] = ContextVar("session_id", default=None)
ip_address_var: ContextVar[str | None] = ContextVar("ip_address", default=None)
user_agent_var: ContextVar[str | None] = ContextVar("user_agent", default=None)


@dataclass(frozen=True)
class AuditRequestContext:
    request_id: str | None
    correlation_id: str | None
    session_id: str | None
    ip_address: str | None
    user_agent: str | None


def get_audit_request_context() -> AuditRequestContext:
    return AuditRequestContext(
        request_id=request_id_var.get(),
        correlation_id=correlation_id_var.get(),
        session_id=session_id_var.get(),
        ip_address=ip_address_var.get(),
        user_agent=user_agent_var.get(),
    )
