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
    from ._models import AssistantMessage, PaaSAgentOutput, PaaSAgentState, ToolResultSummary
    from ._turn_messages import consume_assistant_messages
except ImportError:
    from _errors import json_error, json_success
    from _models import AssistantMessage, PaaSAgentOutput, PaaSAgentState, ToolResultSummary
    from _turn_messages import consume_assistant_messages


class PaaSFinishDecisionInput(BaseModel):
    conversation_id: str = Field(alias="conversationId")
    action: str
    tool_results: list[ToolResultSummary] = Field(default_factory=list, alias="toolResults")
    assistant_messages: list[AssistantMessage] = Field(default_factory=list, alias="assistantMessages")
    new_state: PaaSAgentState = Field(alias="newState")
    terminal: bool


class PaaSFinishDecisionTool(BaseTool):
    name = "paas_finish_decision"
    description = "Validate and return the final Java-parseable PaaS customer-service turn decision."
    input_model = PaaSFinishDecisionInput

    def is_read_only(self, arguments: PaaSFinishDecisionInput) -> bool:
        del arguments
        return True

    async def execute(self, arguments: PaaSFinishDecisionInput, context: ToolExecutionContext) -> ToolResult:
        del context
        error = _validate(arguments)
        if error is not None:
            return json_error("invalid_final_decision", error)
        assistant_messages = arguments.assistant_messages or [
            AssistantMessage.model_validate(item)
            for item in consume_assistant_messages(arguments.conversation_id)
        ]
        output = PaaSAgentOutput.model_validate(
            {
                "conversationId": arguments.conversation_id,
                "action": arguments.action,
                "toolResults": [item.model_dump() for item in arguments.tool_results],
                "assistantMessages": [item.model_dump() for item in assistant_messages],
                "newState": arguments.new_state.model_dump(by_alias=True, exclude_none=True),
                "terminal": arguments.terminal,
            }
        )
        return json_success(output.model_dump(by_alias=True, exclude_none=True))


def _validate(arguments: PaaSFinishDecisionInput) -> str | None:
    state = arguments.new_state
    if not arguments.conversation_id.strip():
        return "conversationId is required"
    if arguments.terminal != state.terminal:
        return "terminal must match newState.terminal"
    if not state.terminal and state.waiting_for is None:
        return "terminal=false requires waitingFor to explain the pending state"
    if state.scenario == "service_error" and state.service_id and state.erp_sent and state.probe_result is None:
        return "service_error with ERP escalation requires a probe result"
    return None
