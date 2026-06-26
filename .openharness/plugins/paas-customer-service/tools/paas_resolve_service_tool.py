from __future__ import annotations

import sys
from pathlib import Path

from pydantic import BaseModel, Field

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult

_TOOLS_DIR = Path(__file__).resolve().parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

try:
    from ._errors import json_error, json_success
    from ._service_registry import load_service_registry
except ImportError:
    from _errors import json_error, json_success
    from _service_registry import load_service_registry


class PaaSResolveServiceInput(BaseModel):
    message: str = Field(description="Current customer message to inspect for service aliases.")
    candidate: str | None = Field(default=None, description="Optional service word extracted by the model.")


class PaaSResolveServiceTool(BaseTool):
    name = "paas_resolve_service"
    description = "Resolve a PaaS service from the registry by customer message and optional candidate text."
    input_model = PaaSResolveServiceInput

    def is_read_only(self, arguments: PaaSResolveServiceInput) -> bool:
        del arguments
        return True

    async def execute(
        self,
        arguments: PaaSResolveServiceInput,
        context: ToolExecutionContext,
    ) -> ToolResult:
        del context
        try:
            registry = load_service_registry()
            resolution = registry.resolve(arguments.message, arguments.candidate)
            return json_success(resolution.model_dump(by_alias=True))
        except Exception as exc:
            return json_error(
                "service_resolution_failed",
                "failed to resolve service from registry",
                metadata={"exception": type(exc).__name__},
            )
