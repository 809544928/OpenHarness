from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from conftest import load_plugin_module


@pytest.mark.asyncio
async def test_send_erp_message_posts_popo_payload_to_default_endpoint(tool_context, monkeypatch):
    monkeypatch.delenv("PAAS_POPO_ENDPOINT", raising=False)
    monkeypatch.delenv("PAAS_ERP_ENDPOINT", raising=False)
    module = load_plugin_module("paas_send_erp_message_tool")
    captured: dict[str, object] = {}

    async def fake_safe_http_json(method, url, *, timeout_ms, json_body=None, headers=None, max_sample_chars=500):
        captured["method"] = method
        captured["url"] = url
        captured["timeout_ms"] = timeout_ms
        captured["json_body"] = json_body
        captured["headers"] = headers
        captured["max_sample_chars"] = max_sample_chars
        return module.SafeHttpResult(
            ok=True,
            status_code=200,
            latency_ms=12,
            error_type="ok",
            response_sample='{"errcode":0}',
            json_body={"errcode": 0, "errmsg": "ok", "data": {"msgId": "popo-msg-1"}},
            content_type="application/json",
            response_kind="json",
        )

    monkeypatch.setattr(module, "safe_http_json", fake_safe_http_json)
    monkeypatch.setattr(module.time, "time", lambda: 1780000000.123)
    tool = module.PaaSSendErpMessageTool()
    args = module.PaaSSendErpMessageInput(
        serviceId="ocr",
        userSummary="用户 appKey app_abcdef OCR 报 401",
        probeSummary="probe unavailable: serviceId=ocr, statusCode=500",
        logResult={
            "serviceId": "ocr",
            "streamName": "aicloud_ocr",
            "queryInfo": "req-123",
            "response": {"hits": [{"body": "raw log"}]},
        },
        platformContext={
            "conversationId": "qiyu:6383959733",
            "platformSessionId": "6383959733",
            "platformUserId": "user-1",
        },
    )

    result = await tool.execute(args, tool_context)
    payload = json.loads(result.output)
    body = captured["json_body"]

    assert result.is_error is False
    assert captured["method"] == "POST"
    assert captured["url"] == module.DEFAULT_POPO_ENDPOINT
    assert captured["timeout_ms"] == 3000
    assert captured["headers"] is None
    assert body == {
        "message": (
            "[aicloud-customer-service]\n"
            "产品: ocr\n"
            "处理说明: 用户反馈 OCR 服务异常，请客服结合 probe 和日志摘要跟进。\n"
            "用户摘要: 用户 appKey app_abcdef OCR 报 401\n"
            "Probe摘要: probe unavailable: serviceId=ocr, statusCode=500\n"
            "日志结果: {\"serviceId\":\"ocr\",\"streamName\":\"aicloud_ocr\",\"queryInfo\":\"req-123\",\"response\":{\"hits\":[{\"body\":\"raw log\"}]}}\n"
            "会话: qiyu:6383959733\n"
            "平台会话: 6383959733\n"
            "平台用户: user-1"
        ),
        "timestamp": 1780000000123,
    }
    assert payload["erpMessageId"] == "popo-msg-1"
    assert payload["product"] == "ocr"
    assert payload["summary"] == "用户 appKey app_abcdef OCR 报 401"
    assert payload["mock"] is False


@pytest.mark.asyncio
async def test_send_erp_message_prefers_popo_endpoint_env(tool_context, monkeypatch):
    monkeypatch.setenv("PAAS_POPO_ENDPOINT", "https://popo.example.invalid/hook")
    monkeypatch.setenv("PAAS_ERP_ENDPOINT", "https://erp.example.invalid/old")
    module = load_plugin_module("paas_send_erp_message_tool")
    captured: dict[str, object] = {}

    async def fake_safe_http_json(method, url, *, timeout_ms, json_body=None, headers=None, max_sample_chars=500):
        captured["url"] = url
        return module.SafeHttpResult(
            ok=True,
            status_code=200,
            latency_ms=1,
            error_type="ok",
            response_sample='{"errcode":0}',
            json_body={"errcode": 0, "errmsg": "ok", "data": {"msgId": "env-msg"}},
            content_type="application/json",
            response_kind="json",
        )

    monkeypatch.setattr(module, "safe_http_json", fake_safe_http_json)
    tool = module.PaaSSendErpMessageTool()
    args = module.PaaSSendErpMessageInput(
        serviceId="tts",
        userSummary="TTS 报错",
        probeSummary=None,
        logResult=None,
        platformContext={"conversationId": "conv-1"},
    )

    result = await tool.execute(args, tool_context)
    payload = json.loads(result.output)

    assert result.is_error is False
    assert captured["url"] == "https://popo.example.invalid/hook"
    assert payload["erpMessageId"] == "env-msg"


@pytest.mark.asyncio
async def test_send_erp_message_falls_back_to_erp_endpoint_env(tool_context, monkeypatch):
    monkeypatch.delenv("PAAS_POPO_ENDPOINT", raising=False)
    monkeypatch.setenv("PAAS_ERP_ENDPOINT", "https://erp.example.invalid/old")
    module = load_plugin_module("paas_send_erp_message_tool")
    captured: dict[str, object] = {}

    async def fake_safe_http_json(method, url, *, timeout_ms, json_body=None, headers=None, max_sample_chars=500):
        captured["url"] = url
        return module.SafeHttpResult(
            ok=True,
            status_code=200,
            latency_ms=1,
            error_type="ok",
            response_sample='{"errcode":0}',
            json_body={"errcode": 0, "errmsg": "ok", "data": {"msgId": "erp-env-msg"}},
            content_type="application/json",
            response_kind="json",
        )

    monkeypatch.setattr(module, "safe_http_json", fake_safe_http_json)
    tool = module.PaaSSendErpMessageTool()
    args = module.PaaSSendErpMessageInput(
        serviceId="asr",
        userSummary="ASR 报错",
        probeSummary=None,
        logResult=None,
        platformContext={},
    )

    result = await tool.execute(args, tool_context)
    payload = json.loads(result.output)

    assert result.is_error is False
    assert captured["url"] == "https://erp.example.invalid/old"
    assert payload["erpMessageId"] == "erp-env-msg"


@pytest.mark.asyncio
async def test_send_erp_message_omits_missing_probe_and_log_result(tool_context, monkeypatch):
    monkeypatch.delenv("PAAS_POPO_ENDPOINT", raising=False)
    monkeypatch.delenv("PAAS_ERP_ENDPOINT", raising=False)
    module = load_plugin_module("paas_send_erp_message_tool")
    captured: dict[str, object] = {}

    async def fake_safe_http_json(method, url, *, timeout_ms, json_body=None, headers=None, max_sample_chars=500):
        captured["json_body"] = json_body
        return module.SafeHttpResult(
            ok=True,
            status_code=200,
            latency_ms=1,
            error_type="ok",
            response_sample='{"errcode":0}',
            json_body={"errcode": 0, "errmsg": "ok", "data": {"msgId": "no-summary-msg"}},
            content_type="application/json",
            response_kind="json",
        )

    monkeypatch.setattr(module, "safe_http_json", fake_safe_http_json)
    tool = module.PaaSSendErpMessageTool()
    args = module.PaaSSendErpMessageInput(
        serviceId="tts",
        userSummary="TTS 失败",
        probeSummary=None,
        logResult=None,
        platformContext={},
    )

    result = await tool.execute(args, tool_context)
    body = captured["json_body"]
    message = body["message"]

    assert result.is_error is False
    assert message.startswith("[aicloud-customer-service]")
    assert "Probe摘要:" not in message
    assert "日志结果:" not in message
    assert "用户摘要: TTS 失败" in message


@pytest.mark.asyncio
async def test_send_erp_message_returns_error_for_nonzero_popo_errcode(tool_context, monkeypatch):
    monkeypatch.delenv("PAAS_POPO_ENDPOINT", raising=False)
    monkeypatch.delenv("PAAS_ERP_ENDPOINT", raising=False)
    module = load_plugin_module("paas_send_erp_message_tool")

    async def fake_safe_http_json(method, url, *, timeout_ms, json_body=None, headers=None, max_sample_chars=500):
        return module.SafeHttpResult(
            ok=True,
            status_code=200,
            latency_ms=1,
            error_type="ok",
            response_sample='{"errcode":1001}',
            json_body={"errcode": 1001, "errmsg": "invalid robot"},
            content_type="application/json",
            response_kind="json",
        )

    monkeypatch.setattr(module, "safe_http_json", fake_safe_http_json)
    tool = module.PaaSSendErpMessageTool()
    args = module.PaaSSendErpMessageInput(
        serviceId="ocr",
        userSummary="OCR 报错",
        probeSummary="probe failed",
        logResult={"errorType": "timeout"},
        platformContext={},
    )

    result = await tool.execute(args, tool_context)
    payload = json.loads(result.output)

    assert result.is_error is True
    assert payload == {
        "error": "erp_send_failed",
        "summary": "POPo ERP returned an error",
        "errorType": "popo_error",
        "errcode": 1001,
        "errmsg": "invalid robot",
    }


def test_send_erp_message_schema_rejects_legacy_log_field():
    module = load_plugin_module("paas_send_erp_message_tool")

    with pytest.raises(ValidationError):
        module.PaaSSendErpMessageInput(
            serviceId="ocr",
            userSummary="OCR 报错",
            probeSummary=None,
            **{"log" + "Summary": "old summary"},
            platformContext={},
        )


@pytest.mark.asyncio
async def test_send_erp_message_truncates_long_log_result(tool_context, monkeypatch):
    module = load_plugin_module("paas_send_erp_message_tool")
    captured: dict[str, object] = {}

    async def fake_safe_http_json(method, url, *, timeout_ms, json_body=None, headers=None, max_sample_chars=500):
        captured["json_body"] = json_body
        return module.SafeHttpResult(
            ok=True,
            status_code=200,
            latency_ms=1,
            error_type="ok",
            response_sample='{"errcode":0}',
            json_body={"errcode": 0, "errmsg": "ok", "data": {"msgId": "truncated-msg"}},
            content_type="application/json",
            response_kind="json",
        )

    monkeypatch.setattr(module, "safe_http_json", fake_safe_http_json)
    tool = module.PaaSSendErpMessageTool()
    args = module.PaaSSendErpMessageInput(
        serviceId="ocr",
        userSummary="OCR 报错",
        probeSummary=None,
        logResult={"body": "x" * (module.MAX_LOG_RESULT_CHARS + 100)},
        platformContext={},
    )

    result = await tool.execute(args, tool_context)
    message = captured["json_body"]["message"]

    assert result.is_error is False
    assert "日志结果:" in message
    assert "...(truncated)" in message
    assert len(message) < module.MAX_LOG_RESULT_CHARS + 500
