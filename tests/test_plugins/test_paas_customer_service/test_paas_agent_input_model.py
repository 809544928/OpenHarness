from __future__ import annotations

from conftest import load_plugin_module


def test_paas_agent_input_accepts_java_camel_case_contract():
    module = load_plugin_module("_models")

    payload = {
        "conversationId": "qiyu:6383959733",
        "platformSessionId": "6383959733",
        "platformUserId": "user-1",
        "staffId": "staff-1",
        "message": "OCR 怎么接入？",
        "history": [
            {"role": "user", "content": "接口报错"},
            {"role": "assistant", "content": "请问你反馈的是哪个服务？"},
        ],
        "agentState": {
            "scenario": "service_error",
            "waitingFor": "service",
            "clarificationCount": 1,
            "terminal": False,
        },
    }

    parsed = module.PaaSAgentInput.model_validate(payload)

    assert parsed.conversation_id == "qiyu:6383959733"
    assert parsed.platform_session_id == "6383959733"
    assert parsed.platform_user_id == "user-1"
    assert parsed.staff_id == "staff-1"
    assert parsed.message == "OCR 怎么接入？"
    assert parsed.history[0]["role"] == "user"
    assert parsed.agent_state["waitingFor"] == "service"
    assert parsed.model_dump(by_alias=True)["agentState"]["clarificationCount"] == 1


def test_paas_agent_input_defaults_optional_java_fields():
    module = load_plugin_module("_models")

    parsed = module.PaaSAgentInput.model_validate(
        {
            "conversationId": "qiyu:demo-1",
            "platformSessionId": "demo-1",
            "message": "你好",
        }
    )

    assert parsed.platform_user_id is None
    assert parsed.staff_id is None
    assert parsed.history == []
    assert parsed.agent_state == {}
