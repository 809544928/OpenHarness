---
name: paas-access-docs-flow
description: Use when a PaaS customer asks for service access, integration, quickstart, API usage, or documentation
---

# PaaS Access Docs Flow

## Overview

For access documentation requests, resolve the service, retrieve the registered manual URL, send a short Qiyu message, and finish.

## When to Use

- The user asks “怎么接入”, “怎么调用”, “文档在哪”, “如何配置”, “有没有 demo”, or similar access questions.
- The classified scenario is `access_docs`.
- A previous `waitingFor=service` flow belongs to an access documentation request.

## Required Tools

| Tool | Purpose |
|---|---|
| `paas_resolve_service` | Resolve the target PaaS service. |
| `paas_get_manual_url` | Get the service manual URL from the registry. |
| `qiyu_send_message` | Send clarification or documentation to the user. |
| `paas_finish_decision` | Finish with the Java-parseable structured result. |

## Flow A: Service Unclear

1. Classify scenario as `access_docs`.
2. Call `paas_resolve_service`.
3. If no unique service is found, compose a service clarification question and keep waiting for a concrete registered service.
4. Call `qiyu_send_message` with the clarification.
5. Call `paas_finish_decision` with `terminal=false`.

Expected state:

```json
{
  "scenario": "access_docs",
  "serviceId": null,
  "waitingFor": "service",
  "terminal": false,
  "terminalReason": "waiting_for_service"
}
```

## Flow B: Service Clear

1. Call `paas_resolve_service` and require a unique registered service.
2. Call `paas_get_manual_url` with the returned `serviceId`.
3. Compose the documentation message from the tool result.
4. Call `qiyu_send_message`.
5. Call `paas_finish_decision` with `terminal=true`.

Expected state:

```json
{
  "scenario": "access_docs",
  "serviceId": "<serviceId>",
  "waitingFor": null,
  "terminal": true,
  "terminalReason": "manual_sent"
}
```

## Message Templates

Service unclear:

```text
请问你咨询的是哪个服务？例如 OCR、TTS 或 ASR。
```

Manual sent:

```text
这是 {displayName} 的接入文档：{manualUrl}

你可以先按快速开始完成接入。如果接入过程中遇到具体报错，可以继续把服务名、appKey 和 requestId 发给我们。
```

Use `displayName` and `manualUrl` from tool results only.

## Tool Result Summary

Include at least these summaries in `paas_finish_decision.toolResults`:

| Tool | Success summary |
|---|---|
| `paas_resolve_service` | `service resolved` or `service unclear` |
| `paas_get_manual_url` | `manual URL resolved` |
| `qiyu_send_message` | `manual message sent` or `service clarification sent` |

## Safety Rules

1. Do not invent manual URLs.
2. Do not paste internal docs or private endpoints unless returned by `paas_get_manual_url` and intended for users.
3. Do not execute service examples.
5. Do not end when the service is unclear; keep `waitingFor=service`.

## Common Mistakes

| Mistake | Correct behavior |
|---|---|
| Sending several generic docs when service is unclear | Ask the user to specify the service. |
| Returning a guessed quickstart URL | Call `paas_get_manual_url`. |
| Ending without a Qiyu message | Send through `qiyu_send_message`. |
| Continuing to probe for docs-only request | Do not probe for `access_docs`. |
