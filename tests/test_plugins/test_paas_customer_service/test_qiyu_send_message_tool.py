from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from conftest import load_plugin_module


@pytest.mark.asyncio
async def test_qiyu_send_message_returns_mock_safe_message(tool_context, monkeypatch):
    monkeypatch.delenv("QIYU_SEND_MESSAGE_ENDPOINT", raising=False)
    module = load_plugin_module("qiyu_send_message_tool")
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
    assert payload["sent"] is True
    assert payload["messageId"].startswith("mock-qiyu-")

    turn_messages = __import__("_turn_messages")
    assert turn_messages.consume_assistant_messages("qiyu:6383959733") == [
        {
            "role": "assistant",
            "content": "这是 OCR 的接入文档：https://docs.example.com/ocr/quickstart",
        }
    ]


def test_qiyu_send_message_rejects_too_long_content():
    module = load_plugin_module("qiyu_send_message_tool")

    with pytest.raises(ValidationError):
        module.QiyuSendMessageInput(
            conversationId="qiyu:1",
            platformSessionId="1",
            messageType="TEXT",
            content="x" * 2001,
        )
