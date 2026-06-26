---
name: paas-service-asr
description: Use when handling Youdao ASR speech-recognition service knowledge, aliases, access guidance, common errors, or troubleshooting context
---

# ASR Service Knowledge

## Overview

ASR 语音识别服务用于把短音频转换为文本。本 skill 提供线上接入知识和排障语境；真实文档链接、probe、日志和 ERP 操作必须通过工具完成。

## When to Use

- 用户提到 ASR、语音识别、音频转文字、语音转文本、短语音识别、录音识别。
- 用户询问 ASR 接入、调用、鉴权、参数、demo 或文档。
- 用户反馈 ASR 返回错误码、超时、识别不准、结果为空或调用失败。
- 需要解释 ASR demo probe 的业务含义。

## Aliases

- ASR
- asr
- 语音识别
- 音频转文字
- 语音转文本
- 语音转写
- 录音识别
- 短语音识别

## Online API Contract

| Item | Value |
|---|---|
| Endpoint | `https://openapi.youdao.com/asrapi` |
| Method | `POST` |
| Encoding | UTF-8 |
| Request format | `application/x-www-form-urlencoded` |
| Success response | JSON with `errorCode == "0"` and `result` |

## Required Parameters

| Parameter | Meaning |
|---|---|
| `q` | Base64-encoded audio file. |
| `langType` | Source language, for example `zh-CHS`. |
| `format` | Audio format, such as `wav`, `aac`, or `mp3`. |
| `rate` | Sample rate; recommended value is `16000`. |
| `channel` | Channel count; only mono is supported, use `1`. |
| `type` | Upload type; base64 upload uses `1`. |
| `appKey` | Application ID from secure environment config. |
| `salt` | UUID-like nonce used with `curtime` to prevent replay. |
| `curtime` | Current Unix timestamp in seconds. |
| `signType` | `v3`. |
| `sign` | `sha256(appKey + input + salt + curtime + appSecret)`. |

For v3 signing, `input` is `q` when length is at most 20, otherwise `q[:10] + len(q) + q[-10:]`. Generate the signature before URL-encoding form fields.

## Limits

- Supported formats include wav, aac, and mp3.
- Recommended wav: PCM, 16 kHz, 16-bit, mono.
- Uploaded audio must not exceed 60 seconds or 10 MB.

## Common Errors

| Code or Symptom | Possible meaning | Next step |
|---|---|---|
| `202` | Signature verification failed. | Probe first; if probe is normal, ask for appKey/requestId and escalate with logs. |
| `206` | Timestamp invalid. | Check customer clock/signing if probe is normal. |
| `207` | Replay request. | Check salt/curtime uniqueness if probe is normal. |
| `3001` | Unsupported speech format. | Ask user to check `format`. |
| `3002` | Unsupported sample rate. | Ask user to check `rate`. |
| `3003` | Unsupported channel count. | Ask user to use mono channel `1`. |
| `3004` | Unsupported upload type. | Ask user to use base64 upload `type=1`. |
| `3007` | Audio file too large. | Ask user to check size. |
| `3008` | Audio duration too long. | Ask user to check duration. |
| `9301` | ASR recognition failed. | Escalate with request context if needed. |
| `9411` / `9412` | Rate or duration limit reached. | Probe first; collect request context if probe is normal. |
| Timeout or 5xx | Service or upstream dependency may be abnormal. | Probe service first. |

## Demo Probe Meaning

The ASR demo probe sends fixed non-sensitive base64 WAV audio to the online ASR endpoint. Probe success means the standard ASR path returned JSON `errorCode == "0"`. It does not prove the user's audio quality, app permissions, IP allowlist, quota, format, sample rate, or recognition language is correct.

## Safety Rules

1. Real probe must use `paas_probe_service`.
2. Real log lookup must use `paas_query_logs`.
3. Real documentation URL must use `paas_get_manual_url`.
4. Do not ask the user for appSecret, signature, full headers, full request body, or sensitive audio content.
5. Do not expose raw probe JSON, statusCode, responseKind, apiErrorCode, signatures, base64 payloads, or internal endpoints in user-facing messages.
6. Minimal probe diagnostics may be included only in ERP-facing summaries after redaction.
