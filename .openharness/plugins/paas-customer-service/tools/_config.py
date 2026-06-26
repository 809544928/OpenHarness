from __future__ import annotations

import os
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]


def get_default_registry_path() -> Path:
    return PLUGIN_ROOT / "config" / "paas-services.example.yaml"


def get_registry_path() -> Path:
    configured = os.environ.get("PAAS_SERVICE_REGISTRY_PATH")
    if configured:
        return Path(configured).expanduser().resolve()
    return get_default_registry_path()


def get_env(name: str) -> str | None:
    value = os.environ.get(name)
    if value is None or not value.strip():
        return None
    return value.strip()


def mask_secret(value: str | None, keep_start: int = 3, keep_end: int = 3) -> str | None:
    if value is None:
        return None
    if len(value) <= keep_start + keep_end:
        return "*" * len(value)
    return f"{value[:keep_start]}***{value[-keep_end:]}"
