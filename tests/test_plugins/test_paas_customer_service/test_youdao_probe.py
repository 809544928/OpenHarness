from __future__ import annotations

import pytest

from conftest import load_plugin_module


def _credentials():
    auth = load_plugin_module("_youdao_auth")
    return auth.YoudaoCredentials(app_key="app", app_secret="secret")


def _http_result(**overrides):
    http = load_plugin_module("_http")
    defaults = {
        "ok": True,
        "status_code": 200,
        "latency_ms": 12,
        "error_type": "ok",
        "response_sample": "",
        "json_body": None,
        "content_type": None,
        "response_kind": "empty",
    }
    defaults.update(overrides)
    return http.SafeHttpResult(**defaults)


def test_build_ocr_probe_request_uses_documented_fields():
    module = load_plugin_module("_youdao_probe")

    request = module.build_youdao_probe_request("ocr-default", "ocr", _credentials(), salt="salt", curtime="1700000000")

    assert request.method == "POST"
    assert request.url == "https://openapi.youdao.com/ocrapi"
    assert request.headers == {"Content-Type": "application/x-www-form-urlencoded"}
    assert request.form_body["appKey"] == "app"
    assert request.form_body["langType"] == "zh-CHS"
    assert request.form_body["detectType"] == "10012"
    assert request.form_body["imageType"] == "1"
    assert request.form_body["docType"] == "json"
    assert request.form_body["signType"] == "v3"
    assert request.form_body["salt"] == "salt"
    assert request.form_body["curtime"] == "1700000000"
    assert request.form_body["img"]
    assert request.form_body["sign"]
    assert "secret" not in repr(request)


def test_build_asr_probe_request_uses_documented_fields():
    module = load_plugin_module("_youdao_probe")

    request = module.build_youdao_probe_request("asr-default", "asr", _credentials(), salt="salt", curtime="1700000000")

    assert request.url == "https://openapi.youdao.com/asrapi"
    assert request.form_body["q"]
    assert request.form_body["langType"] == "zh-CHS"
    assert request.form_body["format"] == "wav"
    assert request.form_body["rate"] == "16000"
    assert request.form_body["channel"] == "1"
    assert request.form_body["type"] == "1"
    assert request.form_body["signType"] == "v3"
    assert request.form_body["sign"]


def test_build_tts_probe_request_uses_documented_fields():
    module = load_plugin_module("_youdao_probe")

    request = module.build_youdao_probe_request("tts-default", "tts", _credentials(), salt="salt", curtime="1700000000")

    assert request.url == "https://openapi.youdao.com/ttsapi"
    assert request.form_body["q"] == "您好,我是小明"
    assert request.form_body["format"] == "mp3"
    assert request.form_body["speed"] == "1"
    assert request.form_body["volume"] == "1.00"
    assert request.form_body["voiceName"] == "youxiaoqin"
    assert request.form_body["signType"] == "v3"
    assert request.form_body["sign"]


def test_build_probe_request_rejects_unknown_template_ref():
    module = load_plugin_module("_youdao_probe")

    with pytest.raises(ValueError) as exc_info:
        module.build_youdao_probe_request("missing-default", "ocr", _credentials(), salt="salt", curtime="1700000000")

    assert "unsupported Youdao probe request template" in str(exc_info.value)
    assert "missing-default" in str(exc_info.value)


def test_build_probe_request_uses_template_ref_not_service_id_for_dispatch():
    module = load_plugin_module("_youdao_probe")

    request = module.build_youdao_probe_request(
        "ocr-default",
        "custom-ocr",
        _credentials(),
        salt="salt",
        curtime="1700000000",
    )

    assert request.service_id == "custom-ocr"
    assert request.url == "https://openapi.youdao.com/ocrapi"
    assert request.form_body["img"]
    assert request.form_body["detectType"] == "10012"


def test_classify_ocr_success_json_error_code_zero():
    module = load_plugin_module("_youdao_probe")
    result = _http_result(json_body={"errorCode": "0"}, response_kind="json", content_type="application/json")

    payload = module.classify_youdao_probe_result("ocr", result)

    assert payload == {
        "serviceId": "ocr",
        "available": True,
        "statusCode": 200,
        "latencyMs": 12,
        "errorType": "ok",
        "responseKind": "json",
        "apiErrorCode": "0",
    }


def test_classify_asr_success_json_error_code_zero():
    module = load_plugin_module("_youdao_probe")
    result = _http_result(json_body={"errorCode": "0"}, response_kind="json", content_type="application/json")

    payload = module.classify_youdao_probe_result("asr", result)

    assert payload["serviceId"] == "asr"
    assert payload["available"] is True
    assert payload["responseKind"] == "json"
    assert payload["apiErrorCode"] == "0"


def test_classify_tts_audio_success():
    module = load_plugin_module("_youdao_probe")
    result = _http_result(json_body=None, response_kind="audio", content_type="audio/mp3")

    payload = module.classify_youdao_probe_result("tts", result)

    assert payload == {
        "serviceId": "tts",
        "available": True,
        "statusCode": 200,
        "latencyMs": 12,
        "errorType": "ok",
        "responseKind": "audio",
        "apiErrorCode": None,
    }


def test_classify_tts_json_error_as_auth_error():
    module = load_plugin_module("_youdao_probe")
    result = _http_result(json_body={"errorCode": 202}, response_kind="json", content_type="application/json")

    payload = module.classify_youdao_probe_result("tts", result)

    assert payload["available"] is False
    assert payload["errorType"] == "auth_error"
    assert payload["responseKind"] == "json"
    assert payload["apiErrorCode"] == "202"


def test_classify_timeout_uses_empty_response():
    module = load_plugin_module("_youdao_probe")
    result = _http_result(ok=False, status_code=None, error_type="timeout", response_kind="empty", latency_ms=3000)

    payload = module.classify_youdao_probe_result("ocr", result)

    assert payload["available"] is False
    assert payload["statusCode"] is None
    assert payload["latencyMs"] == 3000
    assert payload["errorType"] == "timeout"
    assert payload["responseKind"] == "empty"
    assert payload["apiErrorCode"] is None
