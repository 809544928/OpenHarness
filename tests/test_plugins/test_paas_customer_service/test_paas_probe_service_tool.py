from __future__ import annotations

import json

import pytest

from conftest import load_plugin_module


EXPECTED_KEYS = {"serviceId", "available", "statusCode", "latencyMs", "errorType", "responseKind", "apiErrorCode"}


@pytest.mark.asyncio
async def test_probe_service_returns_missing_credentials_without_http(monkeypatch, tool_context):
    module = load_plugin_module("paas_probe_service_tool")
    called = False

    async def fake_safe_http_form(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("HTTP should not be called without credentials")

    for name in [
        "YOUDAO_OCR_APP_KEY",
        "YOUDAO_OCR_APP_SECRET",
        "YOUDAO_APP_KEY",
        "YOUDAO_APP_SECRET",
    ]:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(module, "safe_http_form", fake_safe_http_form)

    tool = module.PaaSProbeServiceTool()
    args = module.PaaSProbeServiceInput(serviceId="ocr")

    result = await tool.execute(args, tool_context)
    payload = json.loads(result.output)

    assert result.is_error is False
    assert called is False
    assert set(payload) == EXPECTED_KEYS
    assert payload == {
        "serviceId": "ocr",
        "available": False,
        "statusCode": None,
        "latencyMs": 0,
        "errorType": "missing_credentials",
        "responseKind": "empty",
        "apiErrorCode": None,
    }


@pytest.mark.asyncio
async def test_probe_service_returns_minimal_ocr_success(monkeypatch, tool_context):
    module = load_plugin_module("paas_probe_service_tool")
    http_module = load_plugin_module("_http")
    monkeypatch.setenv("YOUDAO_APP_KEY", "app")
    monkeypatch.setenv("YOUDAO_APP_SECRET", "secret")

    async def fake_safe_http_form(method, url, *, timeout_ms, form_body, headers):
        assert method == "POST"
        assert url == "https://openapi.youdao.com/ocrapi"
        assert form_body["appKey"] == "app"
        assert form_body["sign"]
        assert "secret" not in form_body.values()
        return http_module.SafeHttpResult(
            ok=True,
            status_code=200,
            latency_ms=18,
            error_type="ok",
            response_sample="",
            json_body={"errorCode": "0"},
            content_type="application/json",
            response_kind="json",
        )

    monkeypatch.setattr(module, "safe_http_form", fake_safe_http_form)

    result = await module.PaaSProbeServiceTool().execute(module.PaaSProbeServiceInput(serviceId="ocr"), tool_context)
    payload = json.loads(result.output)

    assert result.is_error is False
    assert set(payload) == EXPECTED_KEYS
    assert payload["available"] is True
    assert payload["errorType"] == "ok"
    assert payload["responseKind"] == "json"
    assert payload["apiErrorCode"] == "0"


@pytest.mark.asyncio
async def test_probe_service_returns_minimal_tts_audio_success(monkeypatch, tool_context):
    module = load_plugin_module("paas_probe_service_tool")
    http_module = load_plugin_module("_http")
    monkeypatch.setenv("YOUDAO_TTS_APP_KEY", "tts-app")
    monkeypatch.setenv("YOUDAO_TTS_APP_SECRET", "tts-secret")

    async def fake_safe_http_form(method, url, *, timeout_ms, form_body, headers):
        assert url == "https://openapi.youdao.com/ttsapi"
        assert form_body["q"] == "您好"
        assert form_body["voiceName"] == "youxiaoqin"
        return http_module.SafeHttpResult(
            ok=True,
            status_code=200,
            latency_ms=20,
            error_type="ok",
            response_sample="",
            json_body=None,
            content_type="audio/mp3",
            response_kind="audio",
        )

    monkeypatch.setattr(module, "safe_http_form", fake_safe_http_form)

    result = await module.PaaSProbeServiceTool().execute(module.PaaSProbeServiceInput(serviceId="tts"), tool_context)
    payload = json.loads(result.output)

    assert set(payload) == EXPECTED_KEYS
    assert payload == {
        "serviceId": "tts",
        "available": True,
        "statusCode": 200,
        "latencyMs": 20,
        "errorType": "ok",
        "responseKind": "audio",
        "apiErrorCode": None,
    }


@pytest.mark.asyncio
async def test_probe_service_rejects_unknown_service(tool_context):
    module = load_plugin_module("paas_probe_service_tool")
    tool = module.PaaSProbeServiceTool()
    args = module.PaaSProbeServiceInput(serviceId="missing")

    result = await tool.execute(args, tool_context)
    payload = json.loads(result.output)

    assert result.is_error is True
    assert payload["error"] == "unknown_service"
