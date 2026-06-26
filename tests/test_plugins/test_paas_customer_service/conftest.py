from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[3] / ".openharness" / "plugins" / "paas-customer-service"
TOOLS_DIR = PLUGIN_ROOT / "tools"
CONFIG_PATH = PLUGIN_ROOT / "config" / "paas-services.example.yaml"


def load_plugin_module(module_name: str) -> Any:
    module_path = TOOLS_DIR / f"{module_name}.py"
    spec_name = f"test_paas_customer_service_{module_name}"
    if str(TOOLS_DIR) not in sys.path:
        sys.path.insert(0, str(TOOLS_DIR))
    spec = importlib.util.spec_from_file_location(spec_name, module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    module.__package__ = ""
    sys.modules[spec_name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def tool_context(tmp_path: Path):
    from openharness.tools.base import ToolExecutionContext

    return ToolExecutionContext(cwd=tmp_path)
