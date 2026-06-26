from __future__ import annotations

import json
from typing import Any

from openharness.tools.base import ToolResult


class PaaSToolError(RuntimeError):
    """Base exception for PaaS customer-service plugin failures."""


class RegistryError(PaaSToolError):
    """Raised when the service registry is missing, invalid, or cannot resolve a service."""


class ExternalServiceError(PaaSToolError):
    """Raised when an external HTTP dependency fails in a controlled way."""


def json_success(payload: dict[str, Any]) -> ToolResult:
    return ToolResult(output=json.dumps(payload, ensure_ascii=False), is_error=False)


def json_error(
    error: str,
    summary: str,
    *,
    metadata: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> ToolResult:
    payload: dict[str, Any] = {"error": error, "summary": summary}
    if extra:
        payload.update(extra)
    return ToolResult(
        output=json.dumps(payload, ensure_ascii=False),
        is_error=True,
        metadata=metadata or {},
    )
