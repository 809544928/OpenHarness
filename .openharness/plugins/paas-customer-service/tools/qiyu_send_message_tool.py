from __future__ import annotations

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
    from ._http import SafeHttpResult, safe_http_json
    from ._turn_messages import record_assistant_message
except ImportError:
    from _config import get_env
    from _errors import json_error, json_success
    from _http import SafeHttpResult, safe_http_json
    from _turn_messages import record_assistant_message


DEFAULT_QIYU_SEND_MESSAGE_ENDPOINT = "http://localhost:8686/http/ai-customer-service/qiyu-sendMsg"
DEFAULT_ADMIN_TOKEN = "18298622-9615-4F17-9287-F5EA77CAC96D"


class QiyuSendMessageInput(BaseModel):
    conversation_id: str = Field(alias="conversationId")
    platform_session_id: str = Field(alias="platformSessionId")
    platform_user_id: str | None = Field(default=None, alias="platformUserId")
    staff_id: str | None = Field(default=None, alias="staffId")
    message_type: Literal["TEXT"] = Field(default="TEXT", alias="messageType")
    content: str = Field(min_length=1)


class QiyuSendMessageTool(BaseTool):
    name = "qiyu_send_message"
    description = "Send a user-visible text message to a Qiyu customer-service session."
    input_model = QiyuSendMessageInput

    async def execute(self, arguments: QiyuSendMessageInput, context: ToolExecutionContext) -> ToolResult:
        del context
        body = {
            "uid": _qiyu_uid(arguments.platform_user_id),
            "sessionId": arguments.platform_session_id,
            "content": arguments.content,
        }
        headers = {"Admin-Token": _resolve_admin_token()}
        result = await safe_http_json(
            "POST",
            _resolve_qiyu_endpoint(),
            timeout_ms=3000,
            json_body=body,
            headers=headers,
        )
        if not result.ok:
            return json_error(
                "qiyu_send_failed",
                "failed to send Qiyu message",
                extra={"errorType": result.error_type},
            )
        response_code = _qiyu_response_code(result)
        if response_code != 200:
            return json_error(
                "qiyu_send_failed",
                "Qiyu send endpoint returned a non-success code",
                extra={"errorType": "qiyu_code_error", "code": response_code},
            )
        record_assistant_message(arguments.conversation_id, arguments.content)
        return json_success({"sent": True, "mock": False})


def _resolve_qiyu_endpoint() -> str:
    return get_env("QIYU_SEND_MESSAGE_ENDPOINT") or DEFAULT_QIYU_SEND_MESSAGE_ENDPOINT


def _resolve_admin_token() -> str:
    return get_env("ADMIN_TOKEN") or DEFAULT_ADMIN_TOKEN


def _qiyu_uid(platform_user_id: str | None) -> str:
    if platform_user_id is None:
        return ""
    return platform_user_id.strip()


def _qiyu_response_code(result: SafeHttpResult) -> int | None:
    if not result.json_body:
        return None
    code = result.json_body.get("code")
    return code if isinstance(code, int) else None
