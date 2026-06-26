from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult

_TOOLS_DIR = Path(__file__).resolve().parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

try:
    from ._config import get_env, mask_secret
    from ._errors import RegistryError, json_error, json_success
    from ._http import safe_http_json
    from ._service_registry import load_service_registry
except ImportError:
    from _config import get_env, mask_secret
    from _errors import RegistryError, json_error, json_success
    from _http import safe_http_json
    from _service_registry import load_service_registry


class PaaSSendErpMessageInput(BaseModel):
    service_id: str = Field(alias="serviceId")
    user_summary: str = Field(alias="userSummary", max_length=1000)
    probe_summary: str | None = Field(default=None, alias="probeSummary", max_length=1000)
    log_summary: str | None = Field(default=None, alias="logSummary", max_length=1000)
    platform_context: dict[str, Any] = Field(alias="platformContext")


class PaaSSendErpMessageTool(BaseTool):
    name = "paas_send_erp_message"
    description = "Send a summarized PaaS support case to ERP or the internal ticket system."
    input_model = PaaSSendErpMessageInput

    async def execute(self, arguments: PaaSSendErpMessageInput, context: ToolExecutionContext) -> ToolResult:
        del context
        try:
            service = load_service_registry().get(arguments.service_id)
        except RegistryError:
            return json_error("unknown_service", f"unknown serviceId: {arguments.service_id}")

        endpoint = get_env("PAAS_ERP_ENDPOINT")
        token = get_env("PAAS_ERP_TOKEN")
        safe_user_summary = _redact_summary(arguments.user_summary)
        digest_source = f"{service.id}:{safe_user_summary}:{arguments.platform_context.get('conversationId', '')}"
        message_id = "mock-erp-" + hashlib.sha1(digest_source.encode("utf-8")).hexdigest()[:12]
        body = {
            "product": service.erp.product,
            "templateMessage": service.erp.message,
            "userSummary": safe_user_summary,
            "probeSummary": _redact_summary(arguments.probe_summary),
            "logSummary": _redact_summary(arguments.log_summary),
            "platformContext": arguments.platform_context,
        }
        if endpoint is None:
            return json_success(
                {
                    "erpMessageId": message_id,
                    "ticketUrl": None,
                    "product": service.erp.product,
                    "summary": safe_user_summary,
                    "mock": True,
                }
            )

        headers = {"Authorization": f"Bearer {token}"} if token else None
        result = await safe_http_json("POST", endpoint, timeout_ms=3000, json_body=body, headers=headers)
        if not result.ok:
            return json_error("erp_send_failed", "failed to send ERP message", extra={"errorType": result.error_type})
        return json_success(
            {
                "erpMessageId": message_id,
                "ticketUrl": result.json_body.get("ticketUrl") if result.json_body else None,
                "product": service.erp.product,
                "summary": safe_user_summary,
                "mock": False,
            }
        )


def _redact_summary(value: str | None) -> str | None:
    if value is None:
        return None
    words = value.split()
    redacted = [mask_secret(word) if word.lower().startswith("app") and len(word) > 6 else word for word in words]
    return " ".join(redacted)[:1000]
