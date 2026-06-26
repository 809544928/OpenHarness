from __future__ import annotations

import json

import pytest

from conftest import load_plugin_module


@pytest.mark.asyncio
async def test_get_manual_url_returns_registry_url(tool_context):
    module = load_plugin_module("paas_get_manual_url_tool")
    tool = module.PaaSGetManualUrlTool()
    args = module.PaaSGetManualUrlInput(serviceId="ocr")

    result = await tool.execute(args, tool_context)
    payload = json.loads(result.output)

    assert result.is_error is False
    assert payload == {
        "serviceId": "ocr",
        "displayName": "OCR 文字识别",
        "manualUrl": "https://ai.youdao.com/DOCSIRMA/html/ocr/api/tyocr/",
    }


@pytest.mark.asyncio
async def test_get_manual_url_rejects_unknown_service(tool_context):
    module = load_plugin_module("paas_get_manual_url_tool")
    tool = module.PaaSGetManualUrlTool()
    args = module.PaaSGetManualUrlInput(serviceId="missing")

    result = await tool.execute(args, tool_context)
    payload = json.loads(result.output)

    assert result.is_error is True
    assert payload["error"] == "unknown_service"
    assert "missing" in payload["summary"]
