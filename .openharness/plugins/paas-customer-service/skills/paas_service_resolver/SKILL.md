---
name: paas-service-resolver
description: Use when a PaaS customer message may mention a product, service, API, alias, or ambiguous service name
---

# PaaS Service Resolver

## Overview

Service identity must come from the service registry through `paas_resolve_service`. The model may extract candidate words, but only the tool result can establish the final `serviceId`.

## When to Use

- The scenario is `access_docs` or `service_error`.
- The user message may mention a product, service, API, alias, endpoint, feature name, or ambiguous service name.
- The previous state is waiting for `service` and the user provides a service-like answer.
- A flow needs a registered `serviceId` before calling documentation, probe, log, or ERP tools.

## Required Tool

| Tool | Purpose |
|---|---|
| `paas_resolve_service` | Resolve candidate service words against the registry. |

## Resolution Flow

1. Extract possible service words from the current message and relevant history.
2. Ignore generic words such as “接口”, “服务”, “平台”, “API”, “报错”, and “文档” unless paired with a specific service alias.
3. Call `paas_resolve_service` with the current message and the strongest candidate when available.
4. Use the returned `serviceId` only when `ambiguous=false` and the tool returns a unique registered service.
5. If the tool returns multiple candidates, no candidates, low confidence, or `ambiguous=true`, ask a service clarification question.
6. Never invent, normalize, or translate a service ID without the tool result.

## Tool Input Pattern

```json
{
  "message": "OCR 服务一直报 401",
  "candidate": "OCR"
}
```

If there is no strong candidate, pass the message and omit or set `candidate` to `null` according to the tool schema.

## Ambiguity Rules

| Case | Behavior |
|---|---|
| One high-confidence registered service | Continue with returned `serviceId`. |
| Multiple possible services | Ask the user to choose from the returned candidates. |
| Generic words only | Treat service as unclear. |
| User provides service in later turn | Resolve again using current message plus relevant history. |
| User names a service outside the registry | Treat as unsupported and finish, or ask for a registered service if the active scenario still requires one; do not invent a new ID. |

## Clarification Template

If service is unclear, send a concise question through `qiyu_send_message`:

```text
请问你咨询的是哪个服务？例如 OCR、TTS 或 ASR。
```

When the tool returns candidate display names, prefer the returned list instead of a hardcoded list.

## State Requirements

When asking for service, update state with:

```json
{
  "serviceId": null,
  "waitingFor": "service",
  "terminal": false
}
```

Increment `clarificationCount` for the active scenario.

## Common Mistakes

| Mistake | Correct behavior |
|---|---|
| Mapping “文字识别” to `ocr` from memory | Call `paas_resolve_service` and use its result. |
| Treating “接口报错” as a service | Ask which service. |
| Passing a user-provided service ID directly to probe | Resolve through the registry first. |
| Continuing after `ambiguous=true` | Ask the user to choose. |
