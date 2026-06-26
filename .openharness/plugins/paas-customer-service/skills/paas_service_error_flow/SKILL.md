---
name: paas-service-error-flow
description: Use when a PaaS customer reports API errors, failed calls, status codes, timeout, authentication errors, or abnormal service behavior
---

# PaaS Service Error Flow

## Overview

For service errors, resolve the service first. Once service is clear, probe the online demo before asking for request context or escalating to ERP. Sending ERP is the only human-follow-up mechanism in this flow; do not call a separate customer-session escalation action.

## When to Use

- The user reports API errors, failed calls, bad responses, status codes, timeout, auth errors, or abnormal service behavior.
- The classified scenario is `service_error`.
- The previous state waits for `service` or `request_context` in a service-error flow.

## Required Tools

| Tool | Purpose |
|---|---|
| `paas_resolve_service` | Resolve the affected registered service. |
| `paas_probe_service` | Check the standard demo endpoint health. |
| `paas_query_logs` | Query redacted logs using structured request context. |
| `paas_send_erp_message` | Send a safe summary to ERP or the internal ticket system. |
| `qiyu_send_message` | Notify or clarify with the user. |
| `paas_finish_decision` | Finish with Java-parseable structured result. |

## Flow A: Service Unclear

1. Classify scenario as `service_error`.
2. Call `paas_resolve_service`.
3. If service is unclear, send a service clarification through `qiyu_send_message`.
4. Finish through `paas_finish_decision` with `terminal=false`.

State:

```json
{
  "scenario": "service_error",
  "serviceId": null,
  "waitingFor": "service",
  "terminal": false,
  "terminalReason": "waiting_for_service"
}
```

## Flow B: Service Clear, Probe Fails

1. Resolve service through `paas_resolve_service`.
2. Call `paas_probe_service`.
3. If probe indicates unavailable, timeout, HTTP 5xx, network error, auth error, invalid response, or abnormal response, call `paas_send_erp_message`.
   Use `available` as the primary decision field. Do not send raw probe JSON or individual diagnostic fields such as `statusCode`, `responseKind`, or `apiErrorCode` to the user.
4. Call `qiyu_send_message` to tell the user the issue has been forwarded.
5. Finish with `terminal=true`.

State:

```json
{
  "scenario": "service_error",
  "serviceId": "<serviceId>",
  "waitingFor": null,
  "erpSent": true,
  "terminal": true,
  "terminalReason": "erp_sent_after_probe_failure"
}
```

User message:

```text
我们检测到 {displayName} 当前可能存在异常，已经提交客服人员继续排查，请稍候。
```

Probe diagnostics may be included in `paas_send_erp_message.probeSummary`, for example: `probe unavailable: serviceId=tts, statusCode=200, errorType=auth_error, responseKind=json, apiErrorCode=202, latencyMs=98`. Do not include credentials, signatures, request bodies, response samples, audio bytes, or base64 payloads.

## Flow C: Service Clear, Probe Normal, Missing Request Context

1. Resolve service through `paas_resolve_service`.
2. Call `paas_probe_service`.
3. If probe is normal but `appKey` or `requestId` is missing, ask for request context through `qiyu_send_message`.
4. Finish with `terminal=false`.

State:

```json
{
  "scenario": "service_error",
  "serviceId": "<serviceId>",
  "waitingFor": "request_context",
  "probeResult": {
    "available": true
  },
  "terminal": false,
  "terminalReason": "waiting_for_request_context"
}
```

User message:

```text
线上 demo 检测暂未发现服务整体异常。请提供 appKey 和 requestId，如果方便也请补充报错时间，方便客服进一步排查。
```

## Flow D: Waiting for Request Context, User Provides It

1. Read previous `agentState.waitingFor=request_context` and `serviceId`.
2. Extract `appKey`, `requestId`, and optional error time range from the current message and history.
3. Call `paas_query_logs` with structured fields only.
4. Call `paas_send_erp_message` with user summary, probe summary, and log summary.
5. Call `qiyu_send_message` to tell the user the issue has been forwarded.
6. Finish with `terminal=true`.

State:

```json
{
  "scenario": "service_error",
  "serviceId": "<serviceId>",
  "waitingFor": null,
  "logResult": {
    "matched": true
  },
  "erpSent": true,
  "terminal": true,
  "terminalReason": "erp_sent_after_log_query"
}
```

User message:

```text
已收到你提供的信息，我们已经结合日志摘要提交客服人员继续排查，请稍候。
```

## Flow E: User Cannot Provide RequestId

If the user says they cannot provide requestId or appKey:

1. Do not loop forever.
2. If service is clear, send ERP with user summary, probe summary, and “request context not provided”.
3. Notify the user through `qiyu_send_message`.
4. Finish with `terminal=true`.

## Request Context Extraction

| Field | Accept examples | Notes |
|---|---|---|
| `appKey` | `app_xxx`, `ak-xxx`, user-provided application key | Redact in summaries. |
| `requestId` | `req-abc-123`, trace ID, request ID | Required for precise log lookup. |
| `timeRange` | “今天 10 点左右”, ISO time, approximate error time | Optional; normalize only if tool supports it. |

## Rules

1. Do not send ERP before probe if service is clear.
2. Do not ask for requestId before probe.
3. If probe fails, do not ask user for requestId.
4. If logs fail, still send ERP with log failure summary.
5. After ERP submission, notify user and finish.
6. Logs must be queried by structured fields only; never create raw SQL, DSL, or Lucene queries.
7. User-visible messages must not expose raw logs, appKeys, headers, cookies, tokens, signatures, or internal endpoints.
8. Minimal probe diagnostics are internal and ERP-facing only; `qiyu_send_message` must use coarse natural-language status messages.

## Common Mistakes

| Mistake | Correct behavior |
|---|---|
| “OCR 报 500” → ask for requestId first | Resolve service, then probe. |
| Probe failed → ask user for more info | Send ERP and notify user. |
| Probe normal + no requestId → query logs anyway | Ask for request context. |
| Logs unavailable → abandon case | Send ERP with safe failure summary. |
