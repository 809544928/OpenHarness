from __future__ import annotations

import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, model_validator

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult

_TOOLS_DIR = Path(__file__).resolve().parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

try:
    from ._config import get_env
    from ._errors import RegistryError, json_error, json_success
    from ._http import SafeHttpResult, is_mock_url, safe_http_json
    from ._service_registry import load_service_registry
except ImportError:
    from _config import get_env
    from _errors import RegistryError, json_error, json_success
    from _http import SafeHttpResult, is_mock_url, safe_http_json
    from _service_registry import load_service_registry

DEFAULT_O2LOG_ENDPOINT = "https://o2log.corp.youdao.com/api/aicloud/_search"
DEFAULT_TIMEZONE = ZoneInfo("Asia/Shanghai")
QUERY_WINDOW_WITH_TIME = timedelta(minutes=30)
DEFAULT_LOOKBACK = timedelta(minutes=120)
O2LOG_TIMEOUT_MS = 3000


class PaaSQueryLogsInput(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    service_id: str = Field(alias="serviceId")
    app_key: str | None = Field(default=None, alias="appKey", min_length=1)
    request_id: str | None = Field(default=None, alias="requestId", min_length=1)
    time_text: str | None = Field(default=None, alias="time", min_length=1)

    @model_validator(mode="after")
    def require_query_context(self) -> PaaSQueryLogsInput:
        if not self.request_id and not self.app_key:
            raise ValueError("requestId or appKey is required")
        return self


class PaaSQueryLogsTool(BaseTool):
    name = "paas_query_logs"
    description = "Query o2log logs by serviceId, requestId/appKey, and optional time."
    input_model = PaaSQueryLogsInput

    async def execute(self, arguments: PaaSQueryLogsInput, context: ToolExecutionContext) -> ToolResult:
        del context
        try:
            service = load_service_registry().get(arguments.service_id)
        except RegistryError:
            return json_error("unknown_service", f"unknown serviceId: {arguments.service_id}")

        query_info, query_info_source = _query_info(arguments)
        window = _resolve_time_window(arguments.time_text)
        body = _build_o2log_body(service.log.stream_name, query_info, window.start_time, window.end_time)
        endpoint = _resolve_o2log_endpoint()

        if is_mock_url(endpoint):
            return json_success(
                _build_output(
                    service_id=service.id,
                    stream_name=service.log.stream_name,
                    query_info=query_info,
                    query_info_source=query_info_source,
                    time_text=arguments.time_text,
                    window=window,
                    mock=True,
                    result=None,
                )
            )

        authorization = _resolve_o2log_authorization()
        headers = {"Authorization": authorization} if authorization else None
        result = await safe_http_json(
            "POST",
            endpoint,
            timeout_ms=O2LOG_TIMEOUT_MS,
            json_body=body,
            headers=headers,
        )
        return json_success(
            _build_output(
                service_id=service.id,
                stream_name=service.log.stream_name,
                query_info=query_info,
                query_info_source=query_info_source,
                time_text=arguments.time_text,
                window=window,
                mock=False,
                result=result,
            )
        )


class _TimeWindow(BaseModel):
    start_time: int = Field(alias="startTime")
    end_time: int = Field(alias="endTime")
    fallback: bool


def _query_info(arguments: PaaSQueryLogsInput) -> tuple[str, str]:
    if arguments.request_id:
        return arguments.request_id, "requestId"
    return arguments.app_key or "", "appKey"


def _resolve_o2log_endpoint() -> str:
    return get_env("PAAS_O2LOG_ENDPOINT") or DEFAULT_O2LOG_ENDPOINT


def _resolve_o2log_authorization() -> str | None:
    return get_env("PAAS_O2LOG_AUTHORIZATION")


def _resolve_time_window(time_text: str | None) -> _TimeWindow:
    parsed = _parse_user_time(time_text)
    if parsed is None:
        end = datetime.fromtimestamp(time.time(), tz=DEFAULT_TIMEZONE)
        start = end - DEFAULT_LOOKBACK
        return _TimeWindow(startTime=_to_o2log_timestamp(start), endTime=_to_o2log_timestamp(end), fallback=True)
    start = parsed - QUERY_WINDOW_WITH_TIME
    end = parsed + QUERY_WINDOW_WITH_TIME
    return _TimeWindow(startTime=_to_o2log_timestamp(start), endTime=_to_o2log_timestamp(end), fallback=False)


def _parse_user_time(time_text: str | None) -> datetime | None:
    if not time_text:
        return None
    match = re.fullmatch(r"(\d{4})年(\d{1,2})月(\d{1,2})日 (\d{2}):(\d{2})", time_text.strip())
    if match is None:
        return None
    year, month, day, hour, minute = map(int, match.groups())
    try:
        return datetime(year, month, day, hour, minute, tzinfo=DEFAULT_TIMEZONE)
    except ValueError:
        return None


def _to_o2log_timestamp(value: datetime) -> int:
    return int(value.timestamp() * 1000) * 1000


def _build_o2log_body(stream_name: str, query_info: str, start_time: int, end_time: int) -> dict[str, Any]:
    escaped_query_info = query_info.replace("'", "''")
    sql = f"SELECT * FROM \"{stream_name}\" WHERE body LIKE '\\''%{escaped_query_info}%\\'' ORDER BY _timestamp DESC"
    return {
        "query": {
            "from": 0,
            "size": 100,
            "sql": sql,
            "start_time": start_time,
            "end_time": end_time,
        }
    }


def _build_output(
    *,
    service_id: str,
    stream_name: str,
    query_info: str,
    query_info_source: str,
    time_text: str | None,
    window: _TimeWindow,
    mock: bool,
    result: SafeHttpResult | None,
) -> dict[str, Any]:
    output: dict[str, Any] = {
        "serviceId": service_id,
        "streamName": stream_name,
        "queryInfo": query_info,
        "queryInfoSource": query_info_source,
        "time": time_text,
        "timeFallback": window.fallback,
        "startTime": window.start_time,
        "endTime": window.end_time,
        "mock": mock,
        "hits": _extract_hits(result.json_body if result and result.ok else None),
    }
    if result is not None:
        query_error = _query_error(result)
        if query_error is not None:
            output["queryError"] = query_error
    return output


def _extract_hits(response: dict[str, Any] | None) -> list[Any]:
    if response is None:
        return []
    hits = response.get("hits")
    return hits if isinstance(hits, list) else []


def _query_error(result: SafeHttpResult) -> dict[str, str] | None:
    if not result.ok:
        return {"type": result.error_type or "http_error"}
    if not isinstance(result.json_body, dict) or not isinstance(result.json_body.get("hits"), list):
        return {"type": "invalid_o2log_response"}
    return None
