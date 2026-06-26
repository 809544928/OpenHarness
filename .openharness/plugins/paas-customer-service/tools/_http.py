from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import httpx

ResponseKind = Literal["json", "audio", "text", "empty", "binary"]


@dataclass(frozen=True)
class SafeHttpResult:
    ok: bool
    status_code: int | None
    latency_ms: int
    error_type: str
    response_sample: str
    json_body: dict[str, Any] | None = None
    content_type: str | None = None
    response_kind: ResponseKind = "empty"


def is_mock_url(url: str | None) -> bool:
    if not url:
        return True
    lowered = url.lower()
    return "example.com" in lowered or "example.invalid" in lowered


async def safe_http_json(
    method: str,
    url: str,
    *,
    timeout_ms: int,
    json_body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    max_sample_chars: int = 500,
) -> SafeHttpResult:
    import time

    started = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=timeout_ms / 1000) as client:
            response = await client.request(method, url, json=json_body, headers=headers)
        latency_ms = int((time.monotonic() - started) * 1000)
        content_type = response.headers.get("content-type")
        response_kind = _classify_response_kind(content_type, response.content)
        sample = response.text[:max_sample_chars] if response_kind in {"json", "text"} else ""
        parsed = _parse_json_dict(response)
        error_type = _http_error_type(response.status_code, parsed, response.text)
        return SafeHttpResult(
            ok=error_type == "ok",
            status_code=response.status_code,
            latency_ms=latency_ms,
            error_type=error_type,
            response_sample=sample,
            json_body=parsed,
            content_type=content_type,
            response_kind=response_kind,
        )
    except httpx.TimeoutException:
        return SafeHttpResult(False, None, int((time.monotonic() - started) * 1000), "timeout", "")
    except httpx.HTTPError:
        return SafeHttpResult(False, None, int((time.monotonic() - started) * 1000), "network_error", "")


async def safe_http_form(
    method: str,
    url: str,
    *,
    timeout_ms: int,
    form_body: dict[str, str],
    headers: dict[str, str] | None = None,
    max_sample_chars: int = 500,
) -> SafeHttpResult:
    import time

    merged_headers = {"Content-Type": "application/x-www-form-urlencoded"}
    if headers:
        merged_headers.update(headers)
    started = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=timeout_ms / 1000) as client:
            response = await client.request(method, url, data=form_body, headers=merged_headers)
        latency_ms = int((time.monotonic() - started) * 1000)
        content_type = response.headers.get("content-type")
        response_kind = _classify_response_kind(content_type, response.content)
        sample = response.text[:max_sample_chars] if response_kind in {"json", "text"} else ""
        parsed = _parse_json_dict(response)
        error_type = _http_error_type(response.status_code, parsed, response.text)
        return SafeHttpResult(
            ok=error_type == "ok",
            status_code=response.status_code,
            latency_ms=latency_ms,
            error_type=error_type,
            response_sample=sample,
            json_body=parsed,
            content_type=content_type,
            response_kind=response_kind,
        )
    except httpx.TimeoutException:
        return SafeHttpResult(
            False,
            None,
            int((time.monotonic() - started) * 1000),
            "timeout",
            "",
            response_kind="empty",
        )
    except httpx.HTTPError:
        return SafeHttpResult(
            False,
            None,
            int((time.monotonic() - started) * 1000),
            "network_error",
            "",
            response_kind="empty",
        )


def _parse_json_dict(response: Any) -> dict[str, Any] | None:
    try:
        raw = response.json()
    except ValueError:
        return None
    return raw if isinstance(raw, dict) else None


def _http_error_type(status_code: int, parsed: dict[str, Any] | None, text: str) -> str:
    if status_code in {401, 403}:
        return "auth_error"
    if 400 <= status_code < 500:
        return "http_4xx"
    if status_code >= 500:
        return "http_5xx"
    if parsed is None and text.strip():
        return "invalid_response"
    return "ok"


def _classify_response_kind(content_type: str | None, body: bytes) -> ResponseKind:
    if not body:
        return "empty"
    lowered = (content_type or "").split(";", 1)[0].strip().lower()
    if lowered.startswith("audio/"):
        return "audio"
    if lowered == "application/json" or lowered.endswith("+json"):
        return "json"
    stripped = body.lstrip()
    if stripped.startswith(b"{") or stripped.startswith(b"["):
        return "json"
    if lowered.startswith("text/"):
        return "text"
    if lowered == "application/octet-stream":
        return "binary"
    try:
        body.decode("utf-8")
    except UnicodeDecodeError:
        return "binary"
    return "text"
