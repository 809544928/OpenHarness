from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult

_TOOLS_DIR = Path(__file__).resolve().parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

try:
    from ._config import get_env, mask_secret
    from ._errors import RegistryError, json_error, json_success
    from ._http import safe_http_json
    from ._models import TimeRange
    from ._service_registry import load_service_registry
except ImportError:
    from _config import get_env, mask_secret
    from _errors import RegistryError, json_error, json_success
    from _http import safe_http_json
    from _models import TimeRange
    from _service_registry import load_service_registry


class PaaSQueryLogsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service_id: str = Field(alias="serviceId")
    app_key: str = Field(alias="appKey", min_length=1)
    request_id: str = Field(alias="requestId", min_length=1)
    time_range: TimeRange | None = Field(default=None, alias="timeRange")


class PaaSQueryLogsTool(BaseTool):
    name = "paas_query_logs"
    description = "Query service logs by structured serviceId, appKey, requestId, and optional timeRange."
    input_model = PaaSQueryLogsInput

    async def execute(self, arguments: PaaSQueryLogsInput, context: ToolExecutionContext) -> ToolResult:
        del context
        try:
            service = load_service_registry().get(arguments.service_id)
        except RegistryError:
            return json_error("unknown_service", f"unknown serviceId: {arguments.service_id}")

        endpoint = get_env("PAAS_LOG_ENDPOINT")
        token = get_env("PAAS_LOG_TOKEN")
        masked_app_key = mask_secret(arguments.app_key)
        if endpoint is None:
            return json_success(
                {
                    "serviceId": service.id,
                    "streamName": service.log.stream_name,
                    "matched": False,
                    "entries": 0,
                    "summary": f"mock log lookup for requestId {arguments.request_id} and appKey {masked_app_key}",
                    "highlights": [],
                    "mock": True,
                }
            )

        body: dict[str, Any] = {
            "streamName": service.log.stream_name,
            "appKey": arguments.app_key,
            "requestId": arguments.request_id,
            "timeRange": arguments.time_range.model_dump() if arguments.time_range else None,
        }
        headers = {"Authorization": f"Bearer {token}"} if token else None
        result = await safe_http_json("POST", endpoint, timeout_ms=3000, json_body=body, headers=headers)
        return json_success(
            {
                "serviceId": service.id,
                "streamName": service.log.stream_name,
                "matched": result.ok,
                "entries": 1 if result.ok else 0,
                "summary": f"log query completed for requestId {arguments.request_id} and appKey {masked_app_key}",
                "highlights": [result.response_sample] if result.response_sample else [],
                "mock": False,
                "errorType": result.error_type,
            }
        )
