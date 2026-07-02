from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from conftest import load_plugin_module


@pytest.mark.asyncio
async def test_qiyu_send_message_posts_default_sdd_request(tool_context, monkeypatch):
    monkeypatch.delenv("QIYU_SEND_MESSAGE_ENDPOINT", raising=False)
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    module = load_plugin_module("qiyu_send_message_tool")
    calls = []

    async def fake_safe_http_json(method, url, *, timeout_ms, json_body=None, headers=None):
        calls.append(
            {
                "method": method,
                "url": url,
                "timeout_ms": timeout_ms,
                "json_body": json_body,
                "headers": headers,
            }
        )
        return module.SafeHttpResult(
            ok=True,
            status_code=200,
            latency_ms=12,
            error_type="ok",
            response_sample='{"code":200}',
            json_body={"code": 200},
            content_type="application/json",
            response_kind="json",
        )

    monkeypatch.setattr(module, "safe_http_json", fake_safe_http_json)
    tool = module.QiyuSendMessageTool()
    args = module.QiyuSendMessageInput(
        conversationId="qiyu:6383959733",
        platformSessionId="6383959733",
        platformUserId="user-1",
        staffId="staff-1",
        messageType="TEXT",
        content="这是 OCR 的接入文档：https://docs.example.com/ocr/quickstart",
    )

    result = await tool.execute(args, tool_context)
    payload = json.loads(result.output)

    assert result.is_error is False
    assert payload == {"sent": True, "mock": False}
    assert calls == [
        {
            "method": "POST",
            "url": "http://localhost:8686/http/ai-customer-service/qiyu-sendMsg",
            "timeout_ms": 3000,
            "json_body": {
                "uid": "user-1",
                "sessionId": "6383959733",
                "content": "这是 OCR 的接入文档：https://docs.example.com/ocr/quickstart",
            },
            "headers": {"Admin-Token": "18298622-9615-4F17-9287-F5EA77CAC96D"},
        }
    ]

    turn_messages = __import__("_turn_messages")
    assert turn_messages.consume_assistant_messages("qiyu:6383959733") == [
        {
            "role": "assistant",
            "content": "这是 OCR 的接入文档：https://docs.example.com/ocr/quickstart",
        }
    ]


@pytest.mark.asyncio
async def test_qiyu_send_message_uses_env_overrides_and_blank_uid(tool_context, monkeypatch):
    monkeypatch.setenv("QIYU_SEND_MESSAGE_ENDPOINT", "http://qiyu.example.invalid/send")
    monkeypatch.setenv("ADMIN_TOKEN", "custom-admin-token")
    module = load_plugin_module("qiyu_send_message_tool")
    calls = []

    async def fake_safe_http_json(method, url, *, timeout_ms, json_body=None, headers=None):
        calls.append({"url": url, "json_body": json_body, "headers": headers})
        return module.SafeHttpResult(
            ok=True,
            status_code=200,
            latency_ms=8,
            error_type="ok",
            response_sample='{"code":200}',
            json_body={"code": 200},
            content_type="application/json",
            response_kind="json",
        )

    monkeypatch.setattr(module, "safe_http_json", fake_safe_http_json)
    tool = module.QiyuSendMessageTool()
    args = module.QiyuSendMessageInput(
        conversationId="qiyu:6383959733",
        platformSessionId="6383959733",
        platformUserId="   ",
        content="请补充 requestId。",
    )

    result = await tool.execute(args, tool_context)
    payload = json.loads(result.output)

    assert result.is_error is False
    assert payload == {"sent": True, "mock": False}
    assert calls == [
        {
            "url": "http://qiyu.example.invalid/send",
            "json_body": {
                "uid": "",
                "sessionId": "6383959733",
                "content": "请补充 requestId。",
            },
            "headers": {"Admin-Token": "custom-admin-token"},
        }
    ]


@pytest.mark.asyncio
async def test_qiyu_send_message_rejects_non_200_code_without_recording(tool_context, monkeypatch):
    module = load_plugin_module("qiyu_send_message_tool")

    async def fake_safe_http_json(method, url, *, timeout_ms, json_body=None, headers=None):
        return module.SafeHttpResult(
            ok=True,
            status_code=200,
            latency_ms=9,
            error_type="ok",
            response_sample='{"code":500}',
            json_body={"code": 500},
            content_type="application/json",
            response_kind="json",
        )

    monkeypatch.setattr(module, "safe_http_json", fake_safe_http_json)
    tool = module.QiyuSendMessageTool()
    args = module.QiyuSendMessageInput(
        conversationId="qiyu:non-200",
        platformSessionId="6383959733",
        platformUserId="user-1",
        content="我们已帮你转人工处理。",
    )

    result = await tool.execute(args, tool_context)
    payload = json.loads(result.output)

    assert result.is_error is True
    assert payload["error"] == "qiyu_send_failed"
    assert payload["errorType"] == "qiyu_code_error"
    assert payload["code"] == 500

    turn_messages = __import__("_turn_messages")
    assert turn_messages.consume_assistant_messages("qiyu:non-200") == []


@pytest.mark.asyncio
async def test_qiyu_send_message_reports_http_failure(tool_context, monkeypatch):
    module = load_plugin_module("qiyu_send_message_tool")

    async def fake_safe_http_json(method, url, *, timeout_ms, json_body=None, headers=None):
        return module.SafeHttpResult(
            ok=False,
            status_code=None,
            latency_ms=3000,
            error_type="timeout",
            response_sample="",
            json_body=None,
            content_type=None,
            response_kind="empty",
        )

    monkeypatch.setattr(module, "safe_http_json", fake_safe_http_json)
    tool = module.QiyuSendMessageTool()
    args = module.QiyuSendMessageInput(
        conversationId="qiyu:6383959733",
        platformSessionId="6383959733",
        platformUserId="user-1",
        content="请补充 requestId。",
    )

    result = await tool.execute(args, tool_context)
    payload = json.loads(result.output)

    assert result.is_error is True
    assert payload["error"] == "qiyu_send_failed"
    assert payload["errorType"] == "timeout"


@pytest.mark.asyncio
async def test_qiyu_send_message_allows_long_content(tool_context, monkeypatch):
    module = load_plugin_module("qiyu_send_message_tool")

    async def fake_safe_http_json(method, url, *, timeout_ms, json_body=None, headers=None):
        return module.SafeHttpResult(
            ok=True,
            status_code=200,
            latency_ms=5,
            error_type="ok",
            response_sample='{"code":200}',
            json_body={"code": 200},
            content_type="application/json",
            response_kind="json",
        )

    monkeypatch.setattr(module, "safe_http_json", fake_safe_http_json)
    tool = module.QiyuSendMessageTool()
    args = module.QiyuSendMessageInput(
        conversationId="qiyu:long",
        platformSessionId="long",
        content="x" * 5000,
    )

    result = await tool.execute(args, tool_context)
    payload = json.loads(result.output)

    assert result.is_error is False
    assert payload == {"sent": True, "mock": False}


def test_qiyu_send_message_rejects_empty_content():
    module = load_plugin_module("qiyu_send_message_tool")

    with pytest.raises(ValidationError):
        module.QiyuSendMessageInput(
            conversationId="qiyu:1",
            platformSessionId="1",
            content="",
        )
