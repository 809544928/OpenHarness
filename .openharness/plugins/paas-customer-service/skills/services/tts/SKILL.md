---
name: paas-service-tts
description: Use when handling Youdao TTS speech-synthesis service knowledge, aliases, access guidance, common errors, or troubleshooting context
---

# TTS Service Knowledge

## Overview

TTS 语音合成服务用于把文本转换为音频。本 skill 提供线上接入知识和排障语境；真实文档链接、probe、日志和 ERP 操作必须通过工具完成。

## When to Use

- 用户提到 TTS、语音合成、文本转语音、文字转语音、语音播报、合成音频。
- 用户询问 TTS 接入、调用、鉴权、参数、demo、发音人或文档。
- 用户反馈 TTS 返回错误码、超时、无音频、音频异常或调用失败。
- 需要解释 TTS demo probe 的业务含义。

## Aliases

- TTS
- tts
- 语音合成
- 文本转语音
- 文字转语音
- 语音播报
- 合成音频

## Online API Contract

| Item | Value |
|---|---|
| Endpoint | `https://openapi.youdao.com/ttsapi` |
| Method | `POST` |
| Encoding | UTF-8 |
| Request format | form-urlencoded form |
| Success response | Binary audio, commonly `Content-Type: audio/mp3` |
| Error response | JSON with `errorCode` |

TTS is different from OCR and ASR: successful synthesis is audio, not JSON. A JSON response from TTS normally means an error even if HTTP status is 200.

## Required Parameters

| Parameter | Meaning |
|---|---|
| `q` | Text to synthesize. UTF-8 length must not exceed 2048. |
| `voiceName` | Speaker name, such as `youxiaoqin`. |
| `appKey` | Application ID from secure environment config. |
| `salt` | UUID-like nonce used with `curtime` to prevent replay. |
| `curtime` | Current Unix timestamp in seconds. |
| `signType` | `v3`. |
| `sign` | `sha256(appKey + input + salt + curtime + appSecret)`. |

Important optional parameters:

| Parameter | Meaning |
|---|---|
| `format` | Target audio format; probe uses `mp3`. |
| `speed` | Speech speed; normal is `1`, allowed range is `0.5` to `2.0`. |
| `volume` | Volume; normal is `1.00`, allowed range is `0.50` to `5.00`. |

For v3 signing, `input` is `q` when length is at most 20, otherwise `q[:10] + len(q) + q[-10:]`. Generate the signature before URL-encoding form fields.

## Common Errors

| Code or Symptom | Possible meaning | Next step |
|---|---|---|
| `202` | Signature verification failed. | Probe first; if probe is normal, ask for appKey/requestId and escalate with logs. |
| `206` | Timestamp invalid. | Check customer clock/signing if probe is normal. |
| `207` | Replay request. | Check salt/curtime uniqueness if probe is normal. |
| `2004` | Text too long. | Ask user to check `q` length. |
| `2005` | Unsupported audio format. | Ask user to check `format`. |
| `2006` | Unsupported speaker type. | Ask user to check `voiceName`. |
| `2008` / `2011` | Speech speed outside allowed range. | Ask user to check `speed`. |
| `2009` | Service permission abnormal. | Probe first; collect request context if probe is normal. |
| `2013` | `voiceName` parameter error. | Ask user to check speaker name. |
| `2301` | Service exception. | Escalate if probe indicates abnormal. |
| `2411` / `2412` | Rate or character limit reached. | Probe first; collect request context if probe is normal. |
| `2413` | Contains inappropriate words. | Ask user to check text content policy. |
| JSON response | TTS failed; inspect `errorCode`. | Do not treat HTTP 200 JSON as success. |
| Audio response | TTS succeeded. | Do not expose audio bytes in user messages. |

## Demo Probe Meaning

The TTS demo probe sends fixed non-sensitive text `您好` with `voiceName=youxiaoqin` to the online TTS endpoint. Probe success means the standard TTS path returned audio, usually `Content-Type: audio/mp3`. It does not prove the user's text, speaker package, app permissions, IP allowlist, quota, playback client, or downstream audio pipeline is correct.

## Safety Rules

1. Real probe must use `paas_probe_service`.
2. Real log lookup must use `paas_query_logs`.
3. Real documentation URL must use `paas_get_manual_url`.
4. Do not ask the user for appSecret, signature, full headers, full request body, or private text unless policy permits secure handling.
5. Do not expose raw probe JSON, statusCode, responseKind, apiErrorCode, signatures, audio bytes, or internal endpoints in user-facing messages.
6. Minimal probe diagnostics may be included only in ERP-facing summaries after redaction.
