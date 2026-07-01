"""
安全 HTTP 调用基础设施。

本模块提供“永不抛异常”的 HTTP 请求封装，所有结果（成功、超时、网络错误、
HTTP 错误码）统一收拢为 `SafeHttpResult` 数据结构，上层调用方无需 try/except。

提供两种请求模式：
- `safe_http_json`: 发送 JSON 请求体，用于日志查询、ERP 工单、企点消息等场景。
- `safe_http_form`: 发送 form-urlencoded 请求体，用于有道 API 探活（OCR/ASR/TTS）。

同时提供响应类型分类、HTTP 错误码归类、Mock URL 检测等辅助能力。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import httpx

#: 响应内容类型，用于区分 JSON、音频、文本、二进制和空响应。
ResponseKind = Literal["json", "audio", "text", "empty", "binary"]


@dataclass(frozen=True)
class SafeHttpResult:
    """安全的 HTTP 调用结果（不可变数据结构）。

    将所有可能的 HTTP 调用结果统一为一个结构体，包括成功、超时、
    网络错误、HTTP 4xx/5xx、非预期响应等。上层代码通过该结构体
    即可获知调用的完整状态，无需关心底层异常细节。

    Attributes:
        ok: 请求是否成功。等价于 ``error_type == "ok"``。
        status_code: HTTP 状态码，网络异常（超时/网络错误）时为 ``None``。
        latency_ms: 请求耗时（毫秒）。即使请求失败也会记录已消耗的时间。
        error_type: 错误分类字符串。可能的取值包括 ``"ok"``, ``"timeout"``,
            ``"network_error"``, ``"auth_error"``, ``"http_4xx"``,
            ``"http_5xx"``, ``"invalid_response"``。
        response_sample: 响应体截断样本（最多 ``max_sample_chars`` 字符）。
            仅当 ``response_kind`` 为 ``"json"`` 或 ``"text"`` 时填充，
            其余情况为空字符串。
        json_body: 解析后的 JSON 字典。若响应体不是合法 JSON 或解析结果
            不是 dict 类型，则为 ``None``。
        content_type: 响应头中的 Content-Type 值，可能为 ``None``。
        response_kind: 响应内容类型分类。用于区分 JSON 响应、音频响应、
            纯文本、二进制数据或空响应体。
    """

    ok: bool
    status_code: int | None
    latency_ms: int
    error_type: str
    response_sample: str
    json_body: dict[str, Any] | None = None
    content_type: str | None = None
    response_kind: ResponseKind = "empty"


def is_mock_url(url: str | None) -> bool:
    """检测 URL 是否为测试/占位地址。

    当 URL 为空或包含 ``example.com`` / ``example.invalid`` 时
    视为 mock 地址。用于在开发/测试环境中跳过真实 HTTP 调用。

    Args:
        url: 待检测的 URL 字符串。

    Returns:
        ``True`` 表示应跳过真实 HTTP 请求，使用 mock 结果。
    """
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
    """发送 JSON 格式的 HTTP 请求，绝不抛出异常。

    使用 ``httpx.AsyncClient`` 发起异步 HTTP 请求，请求体以 JSON 格式序列化。
    所有异常（超时、网络错误）均被内部捕获并转为 ``SafeHttpResult``，
    上层调用方永远不需要 try/except。

    用于日志查询（``paas_query_logs``）、ERP 工单（``paas_send_erp_message``）
    和企点消息发送（``qiyu_send_message``）等场景。

    Args:
        method: HTTP 方法，如 ``"GET"``、``"POST"``。
        url: 目标 URL。
        timeout_ms: 超时时间（毫秒）。内部会转换为秒后传给 httpx。
        json_body: 可选的 JSON 请求体字典。
        headers: 可选的请求头字典。不自动设置 Content-Type，由调用方传入。
        max_sample_chars: 响应体截断的最大字符数，默认 500。

    Returns:
        ``SafeHttpResult``，封装了调用结果的全部信息。
    """
    import time

    started = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=timeout_ms / 1000) as client:
            response = await client.request(method, url, json=json_body, headers=headers)
        latency_ms = int((time.monotonic() - started) * 1000)
        content_type = response.headers.get("content-type")
        response_kind = _classify_response_kind(content_type, response.content)
        # 仅对 JSON 和文本响应截取样本，音频/二进制响应不采样
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
        # 超时也会记录已消耗的时间，便于排查
        return SafeHttpResult(False, None, int((time.monotonic() - started) * 1000), "timeout", "")
    except httpx.HTTPError:
        # 网络层错误（DNS、连接拒绝、SSL 等）
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
    """发送 form-urlencoded 格式的 HTTP 请求，绝不抛出异常。

    与 ``safe_http_json`` 类似，但会自动设置 ``Content-Type`` 为
    ``application/x-www-form-urlencoded``，请求体以 form 编码发送。
    传入的额外 headers 会合并到默认 Content-Type 之上。

    专门用于有道 API 探活（``paas_probe_service``），因为有道 OCR/ASR/TTS
    的签名算法要求请求体为 form-urlencoded 格式。

    Args:
        method: HTTP 方法，通常为 ``"POST"``。
        url: 目标 URL，如 ``https://openapi.youdao.com/ocrapi``。
        timeout_ms: 超时时间（毫秒）。
        form_body: form-urlencoded 请求体键值对。
        headers: 可选的额外请求头，会合并到默认 Content-Type 之上。
        max_sample_chars: 响应体截断的最大字符数，默认 500。

    Returns:
        ``SafeHttpResult``，封装了调用结果的全部信息。
    """
    import time

    # 有道 API 要求 form-urlencoded 格式，自动设置 Content-Type
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
        # 仅对 JSON 和文本响应截取样本，音频/二进制响应不采样
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
    """安全地将 HTTP 响应体解析为 JSON 字典。

    不仅捕获 JSON 解析异常，还会校验解析结果是否为 dict 类型。
    如果 API 返回的是 JSON 数组（list）而非对象（dict），也会返回 ``None``，
    因为业务代码期望通过 ``.get("errorCode")`` 等字典方法访问字段。

    Args:
        response: httpx Response 对象。

    Returns:
        解析成功且为 dict 类型时返回字典，否则返回 ``None``。
    """
    try:
        raw = response.json()
    except ValueError:
        return None
    return raw if isinstance(raw, dict) else None


def _http_error_type(status_code: int, parsed: dict[str, Any] | None, text: str) -> str:
    """根据 HTTP 状态码和响应内容判断错误类型。

    按优先级依次判断：认证错误（401/403） > 客户端错误（4xx） >
    服务端错误（5xx） > 无效响应（非 JSON） > 正常。

    注意 401/403 在 4xx 范围之前独立判断，因此会被单独归类为
    ``"auth_error"`` 而非通用的 ``"http_4xx"``。

    Args:
        status_code: HTTP 状态码。
        parsed: ``_parse_json_dict`` 的解析结果。
        text: 原始响应文本。

    Returns:
        错误类型字符串：``"auth_error"``, ``"http_4xx"``, ``"http_5xx"``,
        ``"invalid_response"``, 或 ``"ok"``。
    """
    if status_code in {401, 403}:
        return "auth_error"
    if 400 <= status_code < 500:
        return "http_4xx"
    if status_code >= 500:
        return "http_5xx"
    # HTTP 200 但响应不是合法 JSON 字典（如返回了 HTML 页面）
    if parsed is None and text.strip():
        return "invalid_response"
    return "ok"


def _classify_response_kind(content_type: str | None, body: bytes) -> ResponseKind:
    """根据 Content-Type 头和响应体内容推断响应类型。

    分类按优先级从高到低依次为：

    1. 空响应体 → ``"empty"``
    2. Content-Type 以 ``audio/`` 开头 → ``"audio"``（TTS 成功响应）
    3. Content-Type 为 ``application/json`` 或 ``*+json`` → ``"json"``
    4. 响应体以 ``{`` 或 ``[`` 开头 → ``"json"``（Content-Type 缺失时的启发式推断）
    5. Content-Type 以 ``text/`` 开头 → ``"text"``
    6. Content-Type 为 ``application/octet-stream`` → ``"binary"``
    7. 无法以 UTF-8 解码 → ``"binary"``
    8. 其余情况 → ``"text"``

    对 TTS 服务的特殊意义：有道 TTS 成功返回二进制音频（``audio/mp3``），
    失败才返回 JSON。该分类让上层能据此判断 TTS 是否成功：
    ``response_kind == "audio"`` + 2xx → 成功，
    ``response_kind == "json"`` + 有 errorCode → 失败。

    Args:
        content_type: 响应头中的 Content-Type 值，可能为 ``None``。
        body: 原始响应体字节。

    Returns:
        响应类型分类。
    """
    if not body:
        return "empty"
    # 去除 charset 等参数，仅保留 MIME 类型部分
    lowered = (content_type or "").split(";", 1)[0].strip().lower()
    if lowered.startswith("audio/"):
        return "audio"
    if lowered == "application/json" or lowered.endswith("+json"):
        return "json"
    # Content-Type 缺失或不标准时，通过 body 内容启发式判断
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
