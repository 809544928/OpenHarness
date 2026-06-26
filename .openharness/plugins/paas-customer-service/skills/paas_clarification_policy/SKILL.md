---
name: paas-clarification-policy
description: Use when a PaaS customer-service flow lacks required service or request context and must ask the user for missing information
---

# PaaS Clarification Policy

## Overview

Ask concise clarification questions only when required information is missing. Preserve enough state for the next turn and keep the flow focused on the required service or request context.

## When to Use

- The service is unclear for an `access_docs` or `service_error` scenario.
- A service error has a clear service and normal probe, but lacks request context.
- The previous turn set `agentState.waitingFor` to `service` or `request_context`.

## Missing Information Types

| `waitingFor` | Meaning | Typical next input |
|---|---|---|
| `service` | The related PaaS service is unclear. | Service name or alias such as OCR, TTS, ASR. |
| `request_context` | Service is clear, but appKey/requestId/time context is missing. | `appKey`, `requestId`, optional error time. |

## Service Clarification

Ask when:

1. Scenario is `access_docs` and service is unclear.
2. Scenario is `service_error` and service is unclear.
3. The previous state is `waitingFor=service` but the new message still does not resolve uniquely.

Keep asking for a concrete registered service until the user provides one. Do not send ERP only because the service is unclear.

Template:

```text
请问你咨询的是哪个服务？例如 OCR、TTS 或 ASR。
```

If `paas_resolve_service` returns candidate display names, use those names instead of the example list.

State:

```json
{
  "waitingFor": "service",
  "clarificationCount": 1,
  "terminal": false,
  "terminalReason": "waiting_for_service"
}
```

## Request Context Clarification

Ask when all conditions are true:

1. Scenario is `service_error`.
2. Service is clear.
3. `paas_probe_service` returned normal or generally available.
4. `appKey` or `requestId` is missing.

Template:

```text
线上 demo 检测暂未发现服务整体异常。请提供 appKey 和 requestId，如果方便也请补充报错时间，方便客服进一步排查。
```

State:

```json
{
  "waitingFor": "request_context",
  "clarificationCount": 1,
  "terminal": false,
  "terminalReason": "waiting_for_request_context"
}
```

## Continuing a Pending Clarification

| Previous `waitingFor` | If user provides required info | If still missing |
|---|---|---|
| `service` | Resolve service again, then continue the original scenario. | Ask again for the concrete registered service. |
| `request_context` | Query logs, send ERP, notify user, finish. | Ask again for appKey/requestId; if the user says they cannot provide them, send ERP with a missing-context summary and finish. |

## Safety Rules

1. Clarification text must be sent through `qiyu_send_message`.
2. Do not ask for secrets, appSecret, token, cookie, signature, private key, full headers, or full request payload.
3. Do not ask for requestId before probe when service is clear.
4. Do not call any separate customer-session escalation flow.
5. Always finish the turn with `paas_finish_decision` after sending the clarification.

## Common Mistakes

| Mistake | Correct behavior |
|---|---|
| Asking multiple questions at once | Ask for only the missing field needed to continue. |
| Asking for requestId before service resolution | Resolve or clarify service first. |
| Ending because the service is still unclear | Keep `waitingFor=service` and ask for a concrete registered service. |
| Returning clarification text without Qiyu send | Call `qiyu_send_message`, then `paas_finish_decision`. |
