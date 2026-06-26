from __future__ import annotations

import base64
import struct
import wave
from io import BytesIO
from typing import Any, Literal

from pydantic import BaseModel, Field

try:
    from ._http import SafeHttpResult
    from ._youdao_auth import YoudaoCredentials, build_youdao_sign
except ImportError:
    from _http import SafeHttpResult
    from _youdao_auth import YoudaoCredentials, build_youdao_sign

ResponseKind = Literal["json", "audio", "text", "empty", "binary"]


class ProbeRequest(BaseModel):
    service_id: str = Field(alias="serviceId")
    method: str
    url: str
    headers: dict[str, str]
    form_body: dict[str, str] = Field(alias="formBody", repr=False)


_JSON_SUCCESS_SERVICES = {"ocr", "asr"}
_AUTH_ERROR_CODES = {"108", "202", "206", "207"}
_RATE_LIMIT_CODES = {"411", "412", "1411", "2411", "3411", "9411"}
_QUOTA_OR_ACCOUNT_CODES = {"110", "401", "402"}
_PROBE_PAYLOAD_CODES = {
    "1004",
    "1201",
    "2004",
    "2005",
    "2006",
    "2008",
    "2011",
    "2013",
    "3001",
    "3002",
    "3003",
    "3004",
    "3007",
    "3008",
    "9301",
}


def build_youdao_probe_request(
    service_id: str,
    credentials: YoudaoCredentials,
    *,
    salt: str,
    curtime: str,
) -> ProbeRequest:
    if service_id == "ocr":
        return _build_ocr_probe_request(credentials, salt=salt, curtime=curtime)
    if service_id == "asr":
        return _build_asr_probe_request(credentials, salt=salt, curtime=curtime)
    if service_id == "tts":
        return _build_tts_probe_request(credentials, salt=salt, curtime=curtime)
    raise ValueError(f"unsupported Youdao probe service: {service_id}")


def classify_youdao_probe_result(service_id: str, http_result: SafeHttpResult) -> dict[str, Any]:
    api_error_code = _extract_error_code(http_result.json_body)
    error_type = _classify_error_type(service_id, http_result, api_error_code)
    available = error_type == "ok"
    return {
        "serviceId": service_id,
        "available": available,
        "statusCode": http_result.status_code,
        "latencyMs": http_result.latency_ms,
        "errorType": error_type,
        "responseKind": http_result.response_kind,
        "apiErrorCode": api_error_code,
    }


def _build_ocr_probe_request(credentials: YoudaoCredentials, *, salt: str, curtime: str) -> ProbeRequest:
    image = _demo_png_base64()
    form_body = _signed_base_form(credentials, input_field="img", input_value=image, salt=salt, curtime=curtime)
    form_body.update({"langType": "zh-CHS", "detectType": "10012", "imageType": "1", "docType": "json"})
    return ProbeRequest.model_validate(
        {
            "serviceId": "ocr",
            "method": "POST",
            "url": "https://openapi.youdao.com/ocrapi",
            "headers": {"Content-Type": "application/x-www-form-urlencoded"},
            "formBody": form_body,
        }
    )


def _build_asr_probe_request(credentials: YoudaoCredentials, *, salt: str, curtime: str) -> ProbeRequest:
    audio = _demo_wav_base64()
    form_body = _signed_base_form(credentials, input_field="q", input_value=audio, salt=salt, curtime=curtime)
    form_body.update({"langType": "zh-CHS", "format": "wav", "rate": "16000", "channel": "1", "type": "1"})
    return ProbeRequest.model_validate(
        {
            "serviceId": "asr",
            "method": "POST",
            "url": "https://openapi.youdao.com/asrapi",
            "headers": {"Content-Type": "application/x-www-form-urlencoded"},
            "formBody": form_body,
        }
    )


def _build_tts_probe_request(credentials: YoudaoCredentials, *, salt: str, curtime: str) -> ProbeRequest:
    text = "您好"
    form_body = _signed_base_form(credentials, input_field="q", input_value=text, salt=salt, curtime=curtime)
    form_body.update({"format": "mp3", "speed": "1", "volume": "1.00", "voiceName": "youxiaoqin"})
    return ProbeRequest.model_validate(
        {
            "serviceId": "tts",
            "method": "POST",
            "url": "https://openapi.youdao.com/ttsapi",
            "headers": {"Content-Type": "application/x-www-form-urlencoded"},
            "formBody": form_body,
        }
    )


def _signed_base_form(
    credentials: YoudaoCredentials,
    *,
    input_field: str,
    input_value: str,
    salt: str,
    curtime: str,
) -> dict[str, str]:
    sign_type = "v3"
    return {
        "appKey": credentials.app_key,
        input_field: input_value,
        "salt": salt,
        "curtime": curtime,
        "signType": sign_type,
        "sign": build_youdao_sign(sign_type, credentials.app_key, credentials.app_secret, input_value, salt, curtime),
    }


def _classify_error_type(service_id: str, http_result: SafeHttpResult, api_error_code: str | None) -> str:
    if http_result.status_code is None:
        return http_result.error_type
    if http_result.status_code in {401, 403}:
        return "auth_error"
    if http_result.status_code == 429:
        return "rate_limited"
    if http_result.status_code >= 500:
        return "http_5xx"
    if 400 <= http_result.status_code < 500:
        return "http_4xx"
    if service_id in _JSON_SUCCESS_SERVICES:
        if http_result.response_kind != "json" or http_result.json_body is None:
            return "invalid_response"
        return "ok" if api_error_code == "0" else _classify_api_error(api_error_code)
    if service_id == "tts":
        if 200 <= http_result.status_code < 300 and http_result.response_kind == "audio":
            return "ok"
        if http_result.response_kind == "json" and api_error_code is not None:
            return _classify_api_error(api_error_code)
        return "invalid_response"
    return "unsupported_probe"


def _classify_api_error(api_error_code: str | None) -> str:
    if api_error_code in _AUTH_ERROR_CODES:
        return "auth_error"
    if api_error_code in _RATE_LIMIT_CODES:
        return "rate_limited"
    if api_error_code in _QUOTA_OR_ACCOUNT_CODES:
        return "quota_or_account_error"
    if api_error_code in _PROBE_PAYLOAD_CODES:
        return "probe_payload_error"
    return "api_error"


def _extract_error_code(json_body: dict[str, Any] | None) -> str | None:
    if not json_body or "errorCode" not in json_body:
        return None
    return str(json_body["errorCode"])


def _demo_png_base64() -> str:
    return "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="


def _demo_wav_base64() -> str:
    sample_rate = 16000
    frame_count = 1600
    frames = b"".join(struct.pack("<h", 0) for _ in range(frame_count))
    buffer = BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(frames)
    return base64.b64encode(buffer.getvalue()).decode("ascii")
