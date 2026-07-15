from __future__ import annotations

import json

import pytest

from conftest import load_plugin_module


@pytest.mark.asyncio
async def test_finish_decision_returns_normalized_json(tool_context):
    module = load_plugin_module("paas_finish_decision_tool")
    tool = module.PaaSFinishDecisionTool()
    args = module.PaaSFinishDecisionInput(
        conversationId="qiyu:6383959733",
        action="manual_sent",
        toolResults=[{"tool": "qiyu_send_message", "success": True, "summary": "sent manual message"}],
        newState={
            "scenario": "access_docs",
            "serviceId": "ocr",
            "waitingFor": None,
            "terminal": True,
            "terminalReason": "manual_sent",
        },
        terminal=True,
    )

    result = await tool.execute(args, tool_context)
    payload = json.loads(result.output)

    assert result.is_error is False
    assert payload["conversationId"] == "qiyu:6383959733"
    assert payload["terminal"] is True
    assert payload["newState"]["terminal"] is True
    assert payload["assistantMessages"] == []


@pytest.mark.asyncio
async def test_finish_decision_includes_recorded_assistant_messages(tool_context):
    turn_messages = __import__("_turn_messages")
    turn_messages.record_assistant_message("qiyu:6383959733", "这是 OCR 的接入文档：https://docs.example.com/ocr/quickstart")

    module = load_plugin_module("paas_finish_decision_tool")
    tool = module.PaaSFinishDecisionTool()
    args = module.PaaSFinishDecisionInput(
        conversationId="qiyu:6383959733",
        action="manual_sent",
        toolResults=[{"tool": "qiyu_send_message", "success": True, "summary": "sent manual message"}],
        newState={
            "scenario": "access_docs",
            "serviceId": "ocr",
            "waitingFor": None,
            "terminal": True,
            "terminalReason": "manual_sent",
        },
        terminal=True,
    )

    result = await tool.execute(args, tool_context)
    payload = json.loads(result.output)

    assert result.is_error is False
    assert payload["assistantMessages"] == [
        {
            "role": "assistant",
            "content": "这是 OCR 的接入文档：https://docs.example.com/ocr/quickstart",
        }
    ]
    assert turn_messages.consume_assistant_messages("qiyu:6383959733") == []


@pytest.mark.asyncio
async def test_finish_decision_preserves_compact_log_result_without_qiyu_message(tool_context):
    module = load_plugin_module("paas_finish_decision_tool")
    tool = module.PaaSFinishDecisionTool()
    log_result = {
        "serviceId": "ocr",
        "streamName": "aicloud_ocr",
        "queryInfo": "aabbccdd",
        "queryInfoSource": "requestId",
        "time": "2026年7月2日 16:30",
        "timeFallback": False,
        "startTime": 1782979200000000,
        "endTime": 1782982800000000,
        "mock": False,
        "hits": [],
    }
    args = module.PaaSFinishDecisionInput(
        conversationId="qiyu:6383959733",
        action="erp_sent",
        toolResults=[
            {"tool": "paas_query_logs", "success": True, "summary": "queried logs; hits=0"},
            {"tool": "paas_send_erp_message", "success": True, "summary": "sent ERP"},
        ],
        newState={
            "scenario": "service_error",
            "serviceId": "ocr",
            "waitingFor": None,
            "probeResult": {"available": True},
            "logResult": log_result,
            "erpSent": True,
            "terminal": True,
            "terminalReason": "erp_sent_after_log_query",
        },
        terminal=True,
    )

    result = await tool.execute(args, tool_context)
    payload = json.loads(result.output)

    assert result.is_error is False
    assert payload["assistantMessages"] == []
    assert payload["newState"]["logResult"] == log_result
    assert payload["newState"]["terminalReason"] == "erp_sent_after_log_query"


@pytest.mark.asyncio
async def test_finish_decision_rejects_terminal_mismatch(tool_context):
    module = load_plugin_module("paas_finish_decision_tool")
    tool = module.PaaSFinishDecisionTool()
    args = module.PaaSFinishDecisionInput(
        conversationId="qiyu:6383959733",
        action="clarify_service",
        toolResults=[],
        newState={"scenario": "access_docs", "waitingFor": "service", "terminal": False},
        terminal=True,
    )

    result = await tool.execute(args, tool_context)
    payload = json.loads(result.output)

    assert result.is_error is True
    assert payload["error"] == "invalid_final_decision"
    assert "terminal" in payload["summary"]


@pytest.mark.asyncio
async def test_finish_decision_rejects_nonterminal_without_waiting_for(tool_context):
    module = load_plugin_module("paas_finish_decision_tool")
    tool = module.PaaSFinishDecisionTool()
    args = module.PaaSFinishDecisionInput(
        conversationId="qiyu:6383959733",
        action="continue",
        toolResults=[],
        newState={"scenario": "service_error", "serviceId": "ocr", "waitingFor": None, "terminal": False},
        terminal=False,
    )

    result = await tool.execute(args, tool_context)
    payload = json.loads(result.output)

    assert result.is_error is True
    assert payload["error"] == "invalid_final_decision"
    assert "waitingFor" in payload["summary"]



@pytest.mark.asyncio
async def test_finish_decision_allows_repeated_service_clarification(tool_context):
    module = load_plugin_module("paas_finish_decision_tool")
    tool = module.PaaSFinishDecisionTool()
    args = module.PaaSFinishDecisionInput(
        conversationId="qiyu:6383959733",
        action="clarify_service",
        toolResults=[{"tool": "qiyu_send_message", "success": True, "summary": "service clarification sent"}],
        newState={
            "scenario": "access_docs",
            "serviceId": None,
            "waitingFor": "service",
            "clarificationCount": 3,
            "terminal": False,
            "terminalReason": "waiting_for_service",
        },
        terminal=False,
    )

    result = await tool.execute(args, tool_context)
    payload = json.loads(result.output)

    assert result.is_error is False
    assert payload["newState"]["waitingFor"] == "service"
    assert payload["newState"]["clarificationCount"] == 3

    module = load_plugin_module("paas_finish_decision_tool")
    tool = module.PaaSFinishDecisionTool()
    args = module.PaaSFinishDecisionInput(
        conversationId="qiyu:6383959733",
        action="erp_sent",
        toolResults=[{"tool": "paas_send_erp_message", "success": True, "summary": "sent ERP"}],
        newState={
            "scenario": "service_error",
            "serviceId": "ocr",
            "waitingFor": None,
            "erpSent": True,
            "terminal": True,
        },
        terminal=True,
    )

    result = await tool.execute(args, tool_context)
    payload = json.loads(result.output)

    assert result.is_error is True
    assert "probe" in payload["summary"]
