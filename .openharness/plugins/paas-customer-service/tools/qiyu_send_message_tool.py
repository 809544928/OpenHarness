from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult

_TOOLS_DIR = Path(__file__).resolve().parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

try:
    from ._config import get_env
    from ._errors import json_error, json_success
    from ._http import safe_http_json
    from ._turn_messages import record_assistant_message
except ImportError:
    from _config import get_env
    from _errors import json_error, json_success
    from _http import safe_http_json
    from _turn_messages import record_assistant_message


class QiyuSendMessageInput(BaseModel):
    conversation_id: str = Field(alias="conversationId")
    platform_session_id: str = Field(alias="platformSessionId")
    platform_user_id: str | None = Field(default=None, alias="platformUserId")
    staff_id: str | None = Field(default=None, alias="staffId")
    message_type: Literal["TEXT"] = Field(default="TEXT", alias="messageType")
    content: str = Field(min_length=1, max_length=2000)


class QiyuSendMessageTool(BaseTool):
    name = "qiyu_send_message"
    description = "Send a user-visible text message to a Qiyu customer-service session."
    input_model = QiyuSendMessageInput

    async def execute(self, arguments: QiyuSendMessageInput, context: ToolExecutionContext) -> ToolResult:
        del context
        endpoint = get_env("QIYU_SEND_MESSAGE_ENDPOINT")
        token = get_env("QIYU_TOKEN")
        digest = hashlib.sha1(f"{arguments.conversation_id}:{arguments.content}".encode("utf-8")).hexdigest()[:12]
        if endpoint is None:
            record_assistant_message(arguments.conversation_id, arguments.content)
            return json_success({"sent": True, "messageId": f"mock-qiyu-{digest}", "mock": True})
        body = arguments.model_dump(by_alias=True)
        headers = {"Authorization": f"Bearer {token}"} if token else None
        result = await safe_http_json("POST", endpoint, timeout_ms=3000, json_body=body, headers=headers)
        if not result.ok:
            return json_error("qiyu_send_failed", "failed to send Qiyu message", extra={"errorType": result.error_type})
        message_id = result.json_body.get("messageId") if result.json_body else f"qiyu-{digest}"
        record_assistant_message(arguments.conversation_id, arguments.content)
        return json_success({"sent": True, "messageId": message_id, "mock": False})
