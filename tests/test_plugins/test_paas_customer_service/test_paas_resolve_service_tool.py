from __future__ import annotations

import json

import pytest

from conftest import load_plugin_module


@pytest.mark.asyncio
async def test_resolve_service_tool_returns_unique_service(tool_context):
    module = load_plugin_module("paas_resolve_service_tool")
    tool = module.PaaSResolveServiceTool()
    args = module.PaaSResolveServiceInput(message="OCR 服务一直 401")

    result = await tool.execute(args, tool_context)
    payload = json.loads(result.output)

    assert result.is_error is False
    assert payload["serviceId"] == "ocr"
    assert payload["ambiguous"] is False
    assert payload["candidates"] == [{"serviceId": "ocr", "displayName": "OCR 文字识别"}]


@pytest.mark.asyncio
async def test_resolve_service_tool_returns_candidates_for_unknown(tool_context):
    module = load_plugin_module("paas_resolve_service_tool")
    tool = module.PaaSResolveServiceTool()
    args = module.PaaSResolveServiceInput(message="接口一直报错")

    result = await tool.execute(args, tool_context)
    payload = json.loads(result.output)

    assert result.is_error is False
    assert payload["serviceId"] is None
    assert payload["confidence"] == 0.0
    assert [candidate["serviceId"] for candidate in payload["candidates"]] == ["ocr", "tts", "asr"]
