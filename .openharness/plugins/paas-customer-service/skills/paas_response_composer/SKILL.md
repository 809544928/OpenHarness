---
name: paas-response-composer
description: Use when composing short user-visible Qiyu messages for PaaS documentation, clarification, ERP follow-up, or unsupported messages
---

# PaaS Response Composer

## Overview

User-visible messages should be short, clear, action-oriented, and safe. Compose text for `qiyu_send_message` only when the active flow requires a customer-facing message; probe-failure ERP escalation intentionally sends no Qiyu message. Do not expose tool names or raw internal data.

## When to Use

- A flow needs a Qiyu message for clarification, documentation, log-query ERP follow-up, missing-context ERP follow-up, or unsupported scope.
- Tool output must be converted into a safe customer-facing summary.
- A message may contain sensitive identifiers, logs, headers, tokens, internal URLs, or raw exception details.

## General Style

1. Use concise Chinese.
2. Say what happened and what the user can provide next.
3. Avoid internal implementation details and tool names.
4. Do not paste raw logs, stack traces, request payloads, or full upstream responses.
5. Do not expose tokens, headers, signatures, cookies, appSecret, private keys, or internal URLs.
6. Redact full appKey and request identifiers in user-visible summaries unless the user already provided them and exact echoing is necessary; prefer partial or generic references.
7. Send the final text through `qiyu_send_message`.

## Templates

### Ask Service

```text
请问你咨询的是哪个服务？例如 OCR、TTS 或 ASR。
```

### Send Manual

```text
这是 {displayName} 的接入文档：{manualUrl}

你可以先按快速开始完成接入。如果接入过程中遇到具体报错，可以继续把服务名、appKey 和 requestId 发给我们。
```

### Ask Request Context

```text
线上 demo 检测暂未发现服务整体异常。请提供 appKey 和 requestId，如果方便也请补充报错时间，方便客服进一步排查。
```

### Logs Queried and ERP Submitted

```text
已收到你提供的信息，我们已经结合日志摘要提交客服人员继续排查，请稍候。
```

### Request Context Missing but ERP Submitted

```text
已收到反馈。由于暂时缺少 requestId 或 appKey，我们已先按现有信息提交客服人员继续排查；如果后续方便，也可以补充相关信息。
```

### Unsupported

```text
当前问题暂不在智能客服可处理范围内。
```

## Placeholder Rules

| Placeholder | Source |
|---|---|
| `{displayName}` | `paas_resolve_service` or registry-backed tool result. |
| `{manualUrl}` | `paas_get_manual_url` only. |
| Error summary | Redacted tool summary only. |
| ERP/ticket status | `paas_send_erp_message` result only. |

## Length and Format

- Prefer 1-2 short paragraphs.
- Avoid markdown tables in customer messages.
- Do not include code blocks unless the user explicitly asks for a usage example and the content is safe.
- Use stable, neutral wording; do not overpromise a fix time.

## Safety Rules

1. Never mention hidden implementation details such as `paas_probe_service`, log streams, registry paths, environment variables, or idempotency keys.
2. Never paste raw tool output.
3. Never include full appKey, token, cookie, header, signature, or request payload.
4. Never claim an ERP message, Qiyu message, probe, or log query succeeded unless the relevant tool returned success.
5. Do not invent manual URLs or service names.
6. Do not imply a separate customer-session escalation action; ERP submission is the only human-follow-up mechanism.
7. Do not compose or send a probe-failure ERP notification; that branch sends ERP only and finishes silently.

## Common Mistakes

| Mistake | Correct behavior |
|---|---|
| Probe failure → composing a customer notification | Do not compose or send a Qiyu message; the branch sends ERP only and finishes silently. |
| Pasting log highlights directly to user | Send a short summary or submit internally through ERP. |
| “已修复” after ERP sent | Say it has been submitted for follow-up. |
| Including internal ticket URL by default | Only include user-safe links if the tool and policy allow it. |
