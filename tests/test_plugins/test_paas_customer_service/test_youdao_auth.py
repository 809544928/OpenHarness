from __future__ import annotations

import hashlib

import pytest

from conftest import load_plugin_module


def test_truncate_input_keeps_short_values():
    module = load_plugin_module("_youdao_auth")

    assert module.truncate_input("您好") == "您好"
    assert module.truncate_input("12345678901234567890") == "12345678901234567890"


def test_truncate_input_compacts_long_values():
    module = load_plugin_module("_youdao_auth")

    assert module.truncate_input("1234567890ABCDEFGHIJzzzzzzzzzz") == "123456789030zzzzzzzzzz"


def test_build_youdao_sign_v3_uses_documented_order():
    module = load_plugin_module("_youdao_auth")
    expected = hashlib.sha256("app123456789030zzzzzzzzzzsalt1700000000secret".encode("utf-8")).hexdigest()

    actual = module.build_youdao_sign_v3(
        app_key="app",
        app_secret="secret",
        input_value="1234567890ABCDEFGHIJzzzzzzzzzz",
        salt="salt",
        curtime="1700000000",
    )

    assert actual == expected


def test_get_youdao_credentials_prefers_service_specific_env(monkeypatch):
    module = load_plugin_module("_youdao_auth")
    monkeypatch.setenv("YOUDAO_APP_KEY", "shared-key")
    monkeypatch.setenv("YOUDAO_APP_SECRET", "shared-secret")
    monkeypatch.setenv("YOUDAO_OCR_APP_KEY", "ocr-key")
    monkeypatch.setenv("YOUDAO_OCR_APP_SECRET", "ocr-secret")

    credentials = module.get_youdao_credentials("ocr")

    assert credentials.app_key == "ocr-key"
    assert credentials.app_secret == "ocr-secret"


def test_get_youdao_credentials_uses_shared_fallback(monkeypatch):
    module = load_plugin_module("_youdao_auth")
    monkeypatch.delenv("YOUDAO_ASR_APP_KEY", raising=False)
    monkeypatch.delenv("YOUDAO_ASR_APP_SECRET", raising=False)
    monkeypatch.setenv("YOUDAO_APP_KEY", "shared-key")
    monkeypatch.setenv("YOUDAO_APP_SECRET", "shared-secret")

    credentials = module.get_youdao_credentials("asr")

    assert credentials.app_key == "shared-key"
    assert credentials.app_secret == "shared-secret"


def test_get_youdao_credentials_reports_missing_without_secret_values(monkeypatch):
    module = load_plugin_module("_youdao_auth")
    for name in [
        "YOUDAO_TTS_APP_KEY",
        "YOUDAO_TTS_APP_SECRET",
        "YOUDAO_APP_KEY",
        "YOUDAO_APP_SECRET",
    ]:
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(module.MissingYoudaoCredentials) as exc:
        module.get_youdao_credentials("tts")

    assert exc.value.missing == ("app_key", "app_secret")
    assert "secret" not in str(exc.value).lower()


def test_build_youdao_sign_rejects_unsupported_sign_type():
    module = load_plugin_module("_youdao_auth")

    with pytest.raises(module.UnsupportedSignType) as exc:
        module.build_youdao_sign("v4", "app", "secret", "q", "salt", "1700000000")

    assert exc.value.sign_type == "v4"
