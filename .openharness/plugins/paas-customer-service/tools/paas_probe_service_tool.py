from __future__ import annotations

import sys
import time
import uuid
from pathlib import Path

from pydantic import BaseModel, Field

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult

_TOOLS_DIR = Path(__file__).resolve().parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

try:
    from ._errors import RegistryError, json_error, json_success
    from ._http import is_mock_url, safe_http_form
    from ._service_registry import load_service_registry
    from ._youdao_auth import MissingYoudaoCredentials, UnsupportedSignType, get_youdao_credentials
    from ._youdao_probe import build_youdao_probe_request, classify_youdao_probe_result
except ImportError:
    from _errors import RegistryError, json_error, json_success
    from _http import is_mock_url, safe_http_form
    from _service_registry import load_service_registry
    from _youdao_auth import MissingYoudaoCredentials, UnsupportedSignType, get_youdao_credentials
    from _youdao_probe import build_youdao_probe_request, classify_youdao_probe_result


class PaaSProbeServiceInput(BaseModel):
    service_id: str = Field(alias="serviceId", description="Registered PaaS service ID.")


class PaaSProbeServiceTool(BaseTool):
    name = "paas_probe_service"
    description = "Probe a registered service demo endpoint using registry-controlled endpoint and method."
    input_model = PaaSProbeServiceInput

    async def execute(self, arguments: PaaSProbeServiceInput, context: ToolExecutionContext) -> ToolResult:
        del context
        try:
            service = load_service_registry().get(arguments.service_id)
        except RegistryError:
            return json_error("unknown_service", f"unknown serviceId: {arguments.service_id}")

        probe = service.probe
        if is_mock_url(probe.url):
            return json_success(_minimal_probe_result(service.id, available=True, error_type="ok"))

        try:
            credentials = get_youdao_credentials(service.id)
            request = build_youdao_probe_request(
                service.id,
                credentials,
                salt=str(uuid.uuid4()),
                curtime=str(int(time.time())),
            )
        except MissingYoudaoCredentials:
            return json_success(_minimal_probe_result(service.id, available=False, error_type="missing_credentials"))
        except UnsupportedSignType:
            return json_success(_minimal_probe_result(service.id, available=False, error_type="unsupported_sign_type"))
        except ValueError:
            return json_success(_minimal_probe_result(service.id, available=False, error_type="unsupported_probe"))

        result = await safe_http_form(
            request.method,
            request.url,
            timeout_ms=probe.timeout_ms,
            form_body=request.form_body,
            headers=request.headers,
        )
        return json_success(classify_youdao_probe_result(service.id, result))


def _minimal_probe_result(service_id: str, *, available: bool, error_type: str) -> dict[str, object]:
    return {
        "serviceId": service_id,
        "available": available,
        "statusCode": None,
        "latencyMs": 0,
        "errorType": error_type,
        "responseKind": "empty",
        "apiErrorCode": None,
    }
