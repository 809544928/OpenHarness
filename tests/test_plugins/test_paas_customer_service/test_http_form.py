from __future__ import annotations

import pytest

from conftest import load_plugin_module


def test_classify_response_kind_detects_audio():
    module = load_plugin_module("_http")

    assert module._classify_response_kind("audio/mp3", b"abc") == "audio"


def test_classify_response_kind_detects_json_by_content_type():
    module = load_plugin_module("_http")

    assert module._classify_response_kind("application/json; charset=utf-8", b'{"errorCode":"0"}') == "json"


def test_classify_response_kind_detects_json_by_body():
    module = load_plugin_module("_http")

    assert module._classify_response_kind("text/plain", b'{"errorCode":"0"}') == "json"


def test_classify_response_kind_detects_empty():
    module = load_plugin_module("_http")

    assert module._classify_response_kind(None, b"") == "empty"


def test_classify_response_kind_detects_text():
    module = load_plugin_module("_http")

    assert module._classify_response_kind("text/plain", b"hello") == "text"


def test_classify_response_kind_detects_binary():
    module = load_plugin_module("_http")

    assert module._classify_response_kind("application/octet-stream", b"\x00\x01") == "binary"


@pytest.mark.asyncio
async def test_safe_http_form_posts_form_data(monkeypatch):
    module = load_plugin_module("_http")
    captured = {}

    class FakeResponse:
        status_code = 200
        text = '{"errorCode":"0"}'
        content = b'{"errorCode":"0"}'
        headers = {"content-type": "application/json"}

        def json(self):
            return {"errorCode": "0"}

    class FakeClient:
        def __init__(self, timeout):
            captured["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def request(self, method, url, data=None, json=None, headers=None):
            captured.update({"method": method, "url": url, "data": data, "json": json, "headers": headers})
            return FakeResponse()

    monkeypatch.setattr(module.httpx, "AsyncClient", FakeClient)

    result = await module.safe_http_form(
        "POST",
        "https://openapi.youdao.com/ocrapi",
        timeout_ms=1000,
        form_body={"q": "您好"},
        headers={"X-Test": "1"},
    )

    assert captured["method"] == "POST"
    assert captured["data"] == {"q": "您好"}
    assert captured["json"] is None
    assert captured["headers"]["Content-Type"] == "application/x-www-form-urlencoded"
    assert captured["headers"]["X-Test"] == "1"
    assert result.ok is True
    assert result.status_code == 200
    assert result.content_type == "application/json"
    assert result.response_kind == "json"
    assert result.json_body == {"errorCode": "0"}
