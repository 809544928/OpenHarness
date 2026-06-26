from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from conftest import load_plugin_module


@pytest.mark.asyncio
async def test_query_logs_returns_mock_safe_summary(tool_context, monkeypatch):
    monkeypatch.delenv("PAAS_LOG_ENDPOINT", raising=False)
    module = load_plugin_module("paas_query_logs_tool")
    tool = module.PaaSQueryLogsTool()
    args = module.PaaSQueryLogsInput(serviceId="ocr", appKey="app_abcdef", requestId="req-123")

    result = await tool.execute(args, tool_context)
    payload = json.loads(result.output)

    assert result.is_error is False
    assert payload["serviceId"] == "ocr"
    assert payload["matched"] is False
    assert payload["streamName"] == "aicloud_ocr"
    assert "abcdef" not in payload["summary"]


def test_query_logs_schema_rejects_raw_query():
    module = load_plugin_module("paas_query_logs_tool")

    with pytest.raises(ValidationError):
        module.PaaSQueryLogsInput(serviceId="ocr", appKey="app", requestId="req", rawQuery="status:500")
