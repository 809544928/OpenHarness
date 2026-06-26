from __future__ import annotations

import pytest

from conftest import CONFIG_PATH, load_plugin_module


def test_loads_example_registry_with_three_services():
    registry_module = load_plugin_module("_service_registry")

    registry = registry_module.load_service_registry(CONFIG_PATH)

    assert [service.id for service in registry.list_services()] == ["ocr", "tts", "asr"]
    assert registry.get("ocr").display_name == "OCR 文字识别"
    assert registry.get("tts").manual_url == "https://ai.youdao.com/DOCSIRMA/html/tts/api/yyhc/index.html"


def test_resolves_service_by_alias_in_message():
    registry_module = load_plugin_module("_service_registry")
    registry = registry_module.load_service_registry(CONFIG_PATH)

    result = registry.resolve("OCR 服务一直 401")

    assert result.service_id == "ocr"
    assert result.confidence == pytest.approx(0.98)
    assert result.ambiguous is False
    assert result.candidates[0].service_id == "ocr"


def test_resolves_service_by_candidate_before_message():
    registry_module = load_plugin_module("_service_registry")
    registry = registry_module.load_service_registry(CONFIG_PATH)

    result = registry.resolve("接口报错", candidate="语音合成")

    assert result.service_id == "tts"
    assert result.ambiguous is False


def test_unknown_message_returns_all_candidates_and_no_service():
    registry_module = load_plugin_module("_service_registry")
    registry = registry_module.load_service_registry(CONFIG_PATH)

    result = registry.resolve("接口一直报错")

    assert result.service_id is None
    assert result.confidence == 0.0
    assert result.ambiguous is False
    assert [candidate.service_id for candidate in result.candidates] == ["ocr", "tts", "asr"]


def test_duplicate_aliases_create_ambiguous_resolution(tmp_path):
    config_path = tmp_path / "services.yaml"
    config_path.write_text(
        """
services:
  - id: ocr
    displayName: OCR 文字识别
    aliases: [接口]
    manualUrl: https://docs.example.com/ocr/quickstart
    probe: {type: http, method: POST, url: https://api.example.com/ocr/demo, timeoutMs: 3000}
    log: {stream_name: paas-ocr}
    erp: {product: paas-ocr, message: OCR issue}
  - id: tts
    displayName: TTS 语音合成
    aliases: [接口]
    manualUrl: https://docs.example.com/tts/quickstart
    probe: {type: http, method: POST, url: https://api.example.com/tts/demo, timeoutMs: 3000}
    log: {stream_name: paas-tts}
    erp: {product: paas-tts, message: TTS issue}
""".strip(),
        encoding="utf-8",
    )
    registry_module = load_plugin_module("_service_registry")

    registry = registry_module.load_service_registry(config_path)
    result = registry.resolve("接口报错")

    assert result.service_id is None
    assert result.ambiguous is True
    assert {candidate.service_id for candidate in result.candidates} == {"ocr", "tts"}


def test_missing_service_raises_registry_error():
    registry_module = load_plugin_module("_service_registry")
    registry = registry_module.load_service_registry(CONFIG_PATH)

    with pytest.raises(registry_module.RegistryError):
        registry.get("missing")
