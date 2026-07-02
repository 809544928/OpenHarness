from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from conftest import load_plugin_module


def _safe_result(module, body: dict[str, object]):
    return module.SafeHttpResult(
        ok=True,
        status_code=200,
        latency_ms=12,
        error_type="ok",
        response_sample=json.dumps(body, ensure_ascii=False),
        json_body=body,
        content_type="application/json",
        response_kind="json",
    )


@pytest.mark.asyncio
async def test_query_logs_posts_o2log_request_with_request_id_time_window(tool_context, monkeypatch):
    module = load_plugin_module("paas_query_logs_tool")
    captured: dict[str, object] = {}

    async def fake_safe_http_json(method, url, *, timeout_ms, json_body=None, headers=None, max_sample_chars=500):
        captured["method"] = method
        captured["url"] = url
        captured["timeout_ms"] = timeout_ms
        captured["json_body"] = json_body
        captured["headers"] = headers
        captured["max_sample_chars"] = max_sample_chars
        return _safe_result(module, {"hits": [{"body": "raw log"}], "total": 1})

    monkeypatch.setattr(module, "safe_http_json", fake_safe_http_json)
    monkeypatch.setenv("PAAS_O2LOG_AUTHORIZATION", "Basic test-token")
    tool = module.PaaSQueryLogsTool()
    args = module.PaaSQueryLogsInput(
        serviceId="ocr",
        appKey="app_abcdef",
        requestId="req-123",
        time="2026年7月2日 10:30",
    )

    result = await tool.execute(args, tool_context)
    payload = json.loads(result.output)
    body = captured["json_body"]

    assert result.is_error is False
    assert captured["method"] == "POST"
    assert captured["url"] == module.DEFAULT_O2LOG_ENDPOINT
    assert captured["timeout_ms"] == 3000
    assert captured["headers"] == {"Authorization": "Basic test-token"}
    assert body == {
        "query": {
            "from": 0,
            "size": 100,
            "sql": "SELECT * FROM \"aicloud_ocr\" WHERE body LIKE '\\''%req-123%\\'' ORDER BY _timestamp DESC",
            "start_time": 1782957600000000,
            "end_time": 1782961200000000,
        }
    }
    assert payload == {
        "serviceId": "ocr",
        "streamName": "aicloud_ocr",
        "queryInfo": "req-123",
        "queryInfoSource": "requestId",
        "time": "2026年7月2日 10:30",
        "timeFallback": False,
        "startTime": 1782957600000000,
        "endTime": 1782961200000000,
        "mock": False,
        "response": {"hits": [{"body": "raw log"}], "total": 1},
        "errorType": None,
    }


@pytest.mark.asyncio
async def test_query_logs_uses_app_key_when_request_id_missing(tool_context, monkeypatch):
    module = load_plugin_module("paas_query_logs_tool")
    captured: dict[str, object] = {}

    async def fake_safe_http_json(method, url, *, timeout_ms, json_body=None, headers=None, max_sample_chars=500):
        captured["json_body"] = json_body
        return _safe_result(module, {"hits": []})

    monkeypatch.setattr(module, "safe_http_json", fake_safe_http_json)
    tool = module.PaaSQueryLogsTool()
    args = module.PaaSQueryLogsInput(serviceId="tts", appKey="app_abcdef", requestId=None, time="2026年7月2日 10:30")

    result = await tool.execute(args, tool_context)
    payload = json.loads(result.output)
    sql = captured["json_body"]["query"]["sql"]

    assert result.is_error is False
    assert "FROM \"aicloud_tts\"" in sql
    assert "%app_abcdef%" in sql
    assert payload["queryInfo"] == "app_abcdef"
    assert payload["queryInfoSource"] == "appKey"


@pytest.mark.asyncio
async def test_query_logs_escapes_single_quotes_in_query_info(tool_context, monkeypatch):
    module = load_plugin_module("paas_query_logs_tool")
    captured: dict[str, object] = {}

    async def fake_safe_http_json(method, url, *, timeout_ms, json_body=None, headers=None, max_sample_chars=500):
        captured["json_body"] = json_body
        return _safe_result(module, {"hits": []})

    monkeypatch.setattr(module, "safe_http_json", fake_safe_http_json)
    tool = module.PaaSQueryLogsTool()
    args = module.PaaSQueryLogsInput(serviceId="ocr", appKey="app", requestId="req'abc", time="2026年7月2日 10:30")

    result = await tool.execute(args, tool_context)
    sql = captured["json_body"]["query"]["sql"]

    assert result.is_error is False
    assert "%req''abc%" in sql


@pytest.mark.asyncio
async def test_query_logs_defaults_to_previous_120_minutes_without_time(tool_context, monkeypatch):
    module = load_plugin_module("paas_query_logs_tool")
    captured: dict[str, object] = {}

    async def fake_safe_http_json(method, url, *, timeout_ms, json_body=None, headers=None, max_sample_chars=500):
        captured["json_body"] = json_body
        return _safe_result(module, {"hits": []})

    monkeypatch.setattr(module, "safe_http_json", fake_safe_http_json)
    monkeypatch.setattr(module.time, "time", lambda: 1782936000.0)
    tool = module.PaaSQueryLogsTool()
    args = module.PaaSQueryLogsInput(serviceId="ocr", appKey="app_abcdef", requestId="req-123")

    result = await tool.execute(args, tool_context)
    payload = json.loads(result.output)

    assert result.is_error is False
    assert captured["json_body"]["query"]["start_time"] == 1782928800000000
    assert captured["json_body"]["query"]["end_time"] == 1782936000000000
    assert payload["time"] is None
    assert payload["timeFallback"] is True


@pytest.mark.asyncio
async def test_query_logs_defaults_to_previous_120_minutes_for_invalid_time(tool_context, monkeypatch):
    module = load_plugin_module("paas_query_logs_tool")

    async def fake_safe_http_json(method, url, *, timeout_ms, json_body=None, headers=None, max_sample_chars=500):
        return _safe_result(module, {"hits": []})

    monkeypatch.setattr(module, "safe_http_json", fake_safe_http_json)
    monkeypatch.setattr(module.time, "time", lambda: 1782936000.0)
    tool = module.PaaSQueryLogsTool()
    args = module.PaaSQueryLogsInput(serviceId="ocr", appKey="app_abcdef", requestId="req-123", time="今天10点")

    result = await tool.execute(args, tool_context)
    payload = json.loads(result.output)

    assert result.is_error is False
    assert payload["time"] == "今天10点"
    assert payload["timeFallback"] is True
    assert payload["startTime"] == 1782928800000000
    assert payload["endTime"] == 1782936000000000


@pytest.mark.asyncio
async def test_query_logs_returns_raw_response_null_on_http_failure(tool_context, monkeypatch):
    module = load_plugin_module("paas_query_logs_tool")

    async def fake_safe_http_json(method, url, *, timeout_ms, json_body=None, headers=None, max_sample_chars=500):
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
    tool = module.PaaSQueryLogsTool()
    args = module.PaaSQueryLogsInput(serviceId="ocr", appKey="app_abcdef", requestId="req-123", time="2026年7月2日 10:30")

    result = await tool.execute(args, tool_context)
    payload = json.loads(result.output)

    assert result.is_error is False
    assert payload["response"] is None
    assert payload["errorType"] == "timeout"
    assert "summary" not in payload
    assert "highlights" not in payload


@pytest.mark.asyncio
async def test_query_logs_mock_shape_matches_real_shape(tool_context, monkeypatch):
    monkeypatch.setenv("PAAS_O2LOG_ENDPOINT", "https://o2log.example.invalid/_search")
    module = load_plugin_module("paas_query_logs_tool")
    tool = module.PaaSQueryLogsTool()
    args = module.PaaSQueryLogsInput(serviceId="ocr", appKey="app_abcdef", requestId="req-123", time="2026年7月2日 10:30")

    result = await tool.execute(args, tool_context)
    payload = json.loads(result.output)

    assert result.is_error is False
    assert payload["serviceId"] == "ocr"
    assert payload["streamName"] == "aicloud_ocr"
    assert payload["queryInfo"] == "req-123"
    assert payload["queryInfoSource"] == "requestId"
    assert payload["mock"] is True
    assert payload["response"] == {"mock": True, "hits": []}
    assert payload["errorType"] is None


def test_query_logs_schema_rejects_raw_query_and_time_range():
    module = load_plugin_module("paas_query_logs_tool")

    with pytest.raises(ValidationError):
        module.PaaSQueryLogsInput(serviceId="ocr", appKey="app", requestId="req", rawQuery="status:500")

    with pytest.raises(ValidationError):
        module.PaaSQueryLogsInput(serviceId="ocr", appKey="app", requestId="req", timeRange={"start": "x"})


def test_query_logs_requires_request_id_or_app_key():
    module = load_plugin_module("paas_query_logs_tool")

    with pytest.raises(ValidationError):
        module.PaaSQueryLogsInput(serviceId="ocr")
