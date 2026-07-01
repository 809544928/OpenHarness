from __future__ import annotations

import hashlib
import sys
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult

_TOOLS_DIR = Path(__file__).resolve().parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

try:
    from ._config import get_env
    from ._errors import RegistryError, json_error, json_success
    from ._http import SafeHttpResult, safe_http_json
    from ._service_registry import load_service_registry
except ImportError:
    from _config import get_env
    from _errors import RegistryError, json_error, json_success
    from _http import SafeHttpResult, safe_http_json
    from _service_registry import load_service_registry


DEFAULT_POPO_ENDPOINT = (
    "https://open.popo.netease.com/open-apis/robots/v1/hook/"
    "zZVZJrtOORw3LNEvJWUKjQUNLtBmxUBk9CKT3MLCVVNQ17HdJXTLF5DIA7LzbgFjOO5RYWFMdSSqBEltdVblYsrJPIbiBZOP"
)
POPO_MESSAGE_PREFIX = "[aicloud-customer-service]"


class PaaSSendErpMessageInput(BaseModel):
    service_id: str = Field(alias="serviceId")
    user_summary: str = Field(alias="userSummary", max_length=1000)
    probe_summary: str | None = Field(default=None, alias="probeSummary", max_length=1000)
    log_summary: str | None = Field(default=None, alias="logSummary", max_length=1000)
    platform_context: dict[str, Any] = Field(alias="platformContext")


class PaaSSendErpMessageTool(BaseTool):
    name = "paas_send_erp_message"
    description = "Send a summarized PaaS support case to POPo ERP customer-service staff."
    input_model = PaaSSendErpMessageInput

    async def execute(self, arguments: PaaSSendErpMessageInput, context: ToolExecutionContext) -> ToolResult:
        del context
        try:
            service = load_service_registry().get(arguments.service_id)
        except RegistryError:
            return json_error("unknown_service", f"unknown serviceId: {arguments.service_id}")

        user_summary = arguments.user_summary
        probe_summary = arguments.probe_summary
        log_summary = arguments.log_summary
        message = _build_popo_message(
            service,
            user_summary,
            probe_summary,
            log_summary,
            arguments.platform_context,
        )
        body = {"message": message, "timestamp": _current_millis()}
        result = await safe_http_json("POST", _resolve_popo_endpoint(), timeout_ms=3000, json_body=body)
        if not result.ok:
            return json_error("erp_send_failed", "failed to send POPo ERP message", extra={"errorType": result.error_type})

        errcode = _popo_errcode(result.json_body)
        if errcode != 0:
            return json_error(
                "erp_send_failed",
                "POPo ERP returned an error",
                extra={
                    "errorType": "popo_error",
                    "errcode": errcode,
                    "errmsg": _popo_errmsg(result.json_body),
                },
            )

        digest_source = f"{service.id}:{user_summary}:{arguments.platform_context.get('conversationId', '')}"
        fallback_message_id = "popo-" + hashlib.sha1(digest_source.encode("utf-8")).hexdigest()[:12]
        return json_success(
            {
                "erpMessageId": _popo_msg_id(result.json_body) or fallback_message_id,
                "ticketUrl": None,
                "product": service.erp.product,
                "summary": user_summary,
                "mock": False,
            }
        )


def _resolve_popo_endpoint() -> str:
    endpoint = get_env("PAAS_POPO_ENDPOINT") or get_env("PAAS_ERP_ENDPOINT")
    return endpoint or DEFAULT_POPO_ENDPOINT


def _current_millis() -> int:
    return int(time.time() * 1000)


def _build_popo_message(
    service: Any,
    user_summary: str,
    probe_summary: str | None,
    log_summary: str | None,
    platform_context: dict[str, Any],
) -> str:
    lines = [
        POPO_MESSAGE_PREFIX,
        f"产品: {service.erp.product}",
        f"处理说明: {service.erp.message}",
        f"用户摘要: {user_summary}",
    ]
    if probe_summary:
        lines.append(f"Probe摘要: {probe_summary}")
    if log_summary:
        lines.append(f"日志摘要: {log_summary}")
    conversation_id = platform_context.get("conversationId")
    if conversation_id:
        lines.append(f"会话: {conversation_id}")
    platform_session_id = platform_context.get("platformSessionId")
    if platform_session_id:
        lines.append(f"平台会话: {platform_session_id}")
    platform_user_id = platform_context.get("platformUserId")
    if platform_user_id:
        lines.append(f"平台用户: {platform_user_id}")
    return "\n".join(lines)


def _popo_errcode(json_body: dict[str, Any] | None) -> int | None:
    if not json_body:
        return None
    value = json_body.get("errcode")
    return value if isinstance(value, int) else None


def _popo_errmsg(json_body: dict[str, Any] | None) -> str | None:
    if not json_body:
        return None
    value = json_body.get("errmsg")
    return value if isinstance(value, str) else None


def _popo_msg_id(json_body: dict[str, Any] | None) -> str | None:
    if not json_body:
        return None
    data = json_body.get("data")
    if not isinstance(data, dict):
        return None
    msg_id = data.get("msgId")
    return msg_id if isinstance(msg_id, str) and msg_id else None
