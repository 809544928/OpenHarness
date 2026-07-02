from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


Scenario = Literal["access_docs", "service_error", "other"]
WaitingFor = Literal["service", "request_context"]


class ServiceProbeConfig(BaseModel):
    type: Literal["http"] = "http"
    method: Literal["GET", "POST"]
    url: str
    timeout_ms: int = Field(default=3000, alias="timeoutMs", ge=100, le=30000)
    request_template_ref: str = Field(alias="requestTemplateRef")


class ServiceLogConfig(BaseModel):
    stream_name: str


class ServiceErpConfig(BaseModel):
    product: str
    message: str


class ServiceDefinition(BaseModel):
    id: str
    display_name: str = Field(alias="displayName")
    aliases: list[str]
    manual_url: str = Field(alias="manualUrl")
    probe: ServiceProbeConfig
    log: ServiceLogConfig
    erp: ServiceErpConfig

    @field_validator("aliases")
    @classmethod
    def aliases_must_not_be_empty(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("aliases must not be empty")
        return value


class ServiceRegistryConfig(BaseModel):
    services: list[ServiceDefinition]


class ServiceCandidate(BaseModel):
    service_id: str = Field(alias="serviceId")
    display_name: str = Field(alias="displayName")


class ServiceResolution(BaseModel):
    service_id: str | None = Field(default=None, alias="serviceId")
    confidence: float
    ambiguous: bool
    candidates: list[ServiceCandidate]


class PaaSAgentInput(BaseModel):
    conversation_id: str = Field(alias="conversationId")
    platform_session_id: str = Field(alias="platformSessionId")
    platform_user_id: str | None = Field(default=None, alias="platformUserId")
    staff_id: str | None = Field(default=None, alias="staffId")
    message: str
    history: list[dict[str, str]] = Field(default_factory=list)
    agent_state: dict[str, Any] = Field(default_factory=dict, alias="agentState")


class PlatformContext(BaseModel):
    conversation_id: str = Field(alias="conversationId")
    platform_session_id: str = Field(alias="platformSessionId")
    platform_user_id: str | None = Field(default=None, alias="platformUserId")
    staff_id: str | None = Field(default=None, alias="staffId")


class ToolResultSummary(BaseModel):
    tool: str
    success: bool
    summary: str


class AssistantMessage(BaseModel):
    role: Literal["assistant"] = "assistant"
    content: str


class PaaSAgentState(BaseModel):
    scenario: Scenario | None = None
    service_id: str | None = Field(default=None, alias="serviceId")
    waiting_for: WaitingFor | None = Field(default=None, alias="waitingFor")
    clarification_count: int = Field(default=0, alias="clarificationCount", ge=0)
    probe_result: dict[str, Any] | None = Field(default=None, alias="probeResult")
    log_result: dict[str, Any] | None = Field(default=None, alias="logResult")
    erp_sent: bool = Field(default=False, alias="erpSent")
    erp_message_id: str | None = Field(default=None, alias="erpMessageId")
    terminal: bool = False
    terminal_reason: str | None = Field(default=None, alias="terminalReason")


class PaaSAgentOutput(BaseModel):
    conversation_id: str = Field(alias="conversationId")
    action: str
    tool_results: list[ToolResultSummary] = Field(alias="toolResults")
    assistant_messages: list[AssistantMessage] = Field(default_factory=list, alias="assistantMessages")
    new_state: PaaSAgentState = Field(alias="newState")
    terminal: bool
