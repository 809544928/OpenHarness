from __future__ import annotations

import pytest

from openharness.config.settings import Settings
from openharness.ui.runtime import build_runtime, close_runtime


class _StaticApiClient:
    async def stream_message(self, request):
        del request
        if False:
            yield None


@pytest.mark.asyncio
async def test_runtime_registers_paas_customer_service_tools(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setattr("openharness.ui.runtime.load_settings", lambda: Settings(allow_project_plugins=True))

    bundle = await build_runtime(cwd=".", api_client=_StaticApiClient())
    try:
        names = {tool.name for tool in bundle.tool_registry.list_tools()}
    finally:
        await close_runtime(bundle)

    assert {
        "paas_resolve_service",
        "paas_get_manual_url",
        "paas_probe_service",
        "paas_query_logs",
        "paas_send_erp_message",
        "qiyu_send_message",
        "paas_finish_decision",
    }.issubset(names)
