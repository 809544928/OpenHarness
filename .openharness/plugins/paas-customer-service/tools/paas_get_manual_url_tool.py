from __future__ import annotations

import sys
from pathlib import Path

from pydantic import BaseModel, Field

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult

_TOOLS_DIR = Path(__file__).resolve().parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

try:
    from ._errors import RegistryError, json_error, json_success
    from ._service_registry import load_service_registry
except ImportError:
    from _errors import RegistryError, json_error, json_success
    from _service_registry import load_service_registry


class PaaSGetManualUrlInput(BaseModel):
    service_id: str = Field(alias="serviceId", description="Registered PaaS service ID.")


class PaaSGetManualUrlTool(BaseTool):
    name = "paas_get_manual_url"
    description = "Return the registry-backed access manual URL for a registered PaaS service."
    input_model = PaaSGetManualUrlInput

    def is_read_only(self, arguments: PaaSGetManualUrlInput) -> bool:
        del arguments
        return True

    async def execute(
        self,
        arguments: PaaSGetManualUrlInput,
        context: ToolExecutionContext,
    ) -> ToolResult:
        del context
        try:
            service = load_service_registry().get(arguments.service_id)
        except RegistryError:
            return json_error(
                "unknown_service",
                f"unknown serviceId: {arguments.service_id}",
            )
        except Exception as exc:
            return json_error(
                "manual_lookup_failed",
                "failed to load manual URL from registry",
                metadata={"exception": type(exc).__name__},
            )
        return json_success(
            {
                "serviceId": service.id,
                "displayName": service.display_name,
                "manualUrl": service.manual_url,
            }
        )
