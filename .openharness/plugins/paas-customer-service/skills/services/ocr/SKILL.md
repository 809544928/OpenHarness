---
name: paas-service-ocr
description: Use when handling Youdao OCR text-recognition service knowledge, aliases, access guidance, common errors, or troubleshooting context
---

# OCR Service Knowledge

## Overview

OCR 文字识别服务用于从图片、截图、扫描件中识别文字内容。本 skill 提供线上接入知识和排障语境；真实文档链接、probe、日志和 ERP 操作必须通过工具完成。

## When to Use

- 用户提到 OCR、文字识别、图片识别、图像文字识别、图片转文字、扫描件识别、通用文字识别。
- 用户询问 OCR 接入、调用、鉴权、参数、demo 或文档。
- 用户反馈 OCR 返回错误码、超时、识别结果异常或调用失败。
- 需要解释 OCR demo probe 的业务含义。

## Aliases

- OCR
- ocr
- 文字识别
- 图片识别
- 图像文字识别
- 图片转文字
- 扫描件识别
- 通用文字识别

## Online API Contract

| Item | Value |
|---|---|
| Endpoint | `https://openapi.youdao.com/ocrapi` |
| Method | `POST` |
| Encoding | UTF-8 |
| Request format | `application/x-www-form-urlencoded` |
| Success response | JSON with `errorCode == "0"` and `Result` |

## Required Parameters

| Parameter | Meaning |
|---|---|
| `img` | Base64-encoded image. |
| `langType` | Recognition language, for example `zh-CHS`. |
| `detectType` | Recognition type; line recognition uses `10012`. |
| `imageType` | Image transfer type; base64 uses `1`. |
| `docType` | Response type; use `json`. |
| `appKey` | Application ID from secure environment config. |
| `salt` | UUID-like nonce used with `curtime` to prevent replay. |
| `curtime` | Current Unix timestamp in seconds. |
| `signType` | `v3`. |
| `sign` | `sha256(appKey + input + salt + curtime + appSecret)`. |

For v3 signing, `input` is `img` when length is at most 20, otherwise `img[:10] + len(img) + img[-10:]`.

## Limits

- Supported image formats include jpg, png, and bmp.
- Base64-encoded image must be smaller than 2 MB; keeping it under 1 MB is recommended.
- Shortest image side must be greater than 10 px; longest side must be less than 2048 px.

## Common Errors

| Code or Symptom | Possible meaning | Next step |
|---|---|---|
| `202` | Signature verification failed. | Probe first; if probe is normal, ask for appKey/requestId and escalate with logs. |
| `206` | Timestamp invalid. | Check customer clock/signing if probe is normal. |
| `207` | Replay request. | Check salt/curtime uniqueness if probe is normal. |
| `1004` | Image too large. | Ask user to check image size against docs. |
| `1006` | Image empty. | Ask user to verify `img` is present. |
| `1201` | Base64 decode failed. | Ask user to check image base64 encoding. |
| `1301` | OCR paragraph recognition failed. | Escalate with request context if needed. |
| `1411` | Rate limited. | Probe first; collect request context if probe is normal. |
| Timeout or 5xx | Service or upstream dependency may be abnormal. | Probe service first. |

## Demo Probe Meaning

The OCR demo probe sends a fixed non-sensitive base64 image to the online OCR endpoint. Probe success means the standard OCR path returned JSON `errorCode == "0"`. It does not prove the user's image, app permissions, IP allowlist, quota, or request parameters are correct.

## Safety Rules

1. Real probe must use `paas_probe_service`.
2. Real log lookup must use `paas_query_logs`.
3. Real documentation URL must use `paas_get_manual_url`.
4. Do not ask the user for appSecret, signature, full headers, full request body, or sensitive image content.
5. Do not expose raw probe JSON, statusCode, responseKind, apiErrorCode, signatures, base64 payloads, or internal endpoints in user-facing messages.
6. Minimal probe diagnostics may be included only in ERP-facing summaries after redaction.
