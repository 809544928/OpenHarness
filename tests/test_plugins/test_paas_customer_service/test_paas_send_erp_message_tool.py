from __future__ import annotations

import json

import pytest

from conftest import load_plugin_module


@pytest.mark.asyncio
async def test_send_erp_message_returns_mock_safe_ticket(tool_context, monkeypatch):
    monkeypatch.delenv("PAAS_ERP_ENDPOINT", raising=False)
    module = load_plugin_module("paas_send_erp_message_tool")
    tool = module.PaaSSendErpMessageTool()
    args = module.PaaSSendErpMessageInput(
        serviceId="ocr",
        userSummary="用户 appKey app_abcdef OCR 报 401",
        probeSummary="online probe succeeded",
        logSummary="request req-123 not found",
        platformContext={
            "conversationId": "qiyu:6383959733",
            "platformSessionId": "6383959733",
            "platformUserId": "user-1",
        },
    )

    result = await tool.execute(args, tool_context)
    payload = json.loads(result.output)

    assert result.is_error is False
    assert payload["erpMessageId"].startswith("mock-erp-")
    assert payload["product"] == "ocr"
    assert "app_abcdef" not in payload["summary"]
