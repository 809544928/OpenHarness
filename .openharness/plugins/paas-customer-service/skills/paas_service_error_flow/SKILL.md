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
| `paas_query_logs` | Query o2log by structured request context and return compact query context plus `hits`. |
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
4. Do not call `qiyu_send_message` for this branch. Probe failure is a silent ERP escalation from the user's perspective.
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
线上 demo 检测暂未发现服务整体异常。请提供 requestId、appKey、time 等信息，方便客服进一步排查。time 给一个大约模糊有误差的时间即可，但必须是 2026年7月2日 10:30 这种格式；如果暂时没有时间也可以先提供 requestId 或 appKey。
```

## Flow D: Waiting for Request Context, User Provides It

1. Read previous `agentState.waitingFor=request_context` and `serviceId`.
2. Extract `appKey`, `requestId`, and optional `time` from the current message and history.
3. If either `requestId` or `appKey` is available, call `paas_query_logs` with structured fields only.
4. Call `paas_send_erp_message` with user summary, probe summary, and `logResult` equal to the `paas_query_logs` result.
5. Do not call `qiyu_send_message` in this branch; do not send confirmation text to the user.
6. Finish with `terminal=true`.

State:

```json
{
  "scenario": "service_error",
  "serviceId": "<serviceId>",
  "waitingFor": null,
  "logResult": {
    "serviceId": "<serviceId>",
    "streamName": "<streamName>",
    "queryInfo": "<requestId-or-appKey>",
    "queryInfoSource": "requestId",
    "hits": []
  },
  "erpSent": true,
  "terminal": true,
  "terminalReason": "erp_sent_after_log_query"
}
```

Log result semantics:

1. `logResult.hits` is the only field that represents matched user request logs.
2. `hits=[]` means no matching logs were found. It is not evidence of user business auth failure, request failure, service failure, invalid appKey, or signature error.
3. `queryError`, if present, describes the log-platform query itself, not the user's PaaS API call. For example, `queryError.type=auth_error` means o2log query authentication failed; it does not mean OCR/TTS/ASR authentication failed.
4. Only summarize a business error when a concrete item inside `hits` explicitly contains that error.

## Flow E: User Cannot Provide RequestId Or AppKey

If the user says they cannot provide both requestId and appKey:

1. Do not call `paas_query_logs`.
2. Do not send ERP only because request context is missing when probe is normal.
3. Ask once for at least one query key if the conversation can continue, or finish with `terminal=true` and `terminalReason=missing_request_context` if the user clearly cannot provide either value.

## Request Context Extraction

| Field | Accept examples | Notes |
|---|---|---|
| `appKey` | `app_xxx`, `ak-xxx`, user-provided application key | Optional individually; required if `requestId` is missing. |
| `requestId` | `req-abc-123`, trace ID, request ID | Optional individually; preferred for precise log lookup. |
| `time` | `2026年7月2日 10:30` | Optional. Must use this format if supplied; tool falls back to recent 120 minutes if missing or invalid. |

## Rules

1. Do not send ERP before probe if service is clear.
2. Do not ask for requestId before probe.
3. If probe fails, do not ask user for requestId and do not call `qiyu_send_message`; send ERP and finish silently.
4. If logs fail, still send ERP with the compact `logResult` containing `hits: []` and optional query-level error fields.
5. After ERP submission from the log-query branch, finish through `paas_finish_decision` without calling `qiyu_send_message`.
6. After `paas_query_logs`, only inspect `logResult.hits` as the matched log list; do not infer business errors from empty hits, query metadata, query errors, HTTP/tool errors, or missing logs.
7. Logs must be queried by structured fields only; never pass raw SQL, DSL, Lucene queries, or legacy time range fields.
8. User-visible messages must not expose raw logs, appKeys, headers, cookies, tokens, signatures, or internal endpoints.
9. Minimal probe diagnostics are internal and ERP-facing only; probe failure diagnostics must not be sent through `qiyu_send_message`.

## Common Mistakes

| Mistake | Correct behavior |
|---|---|
| “OCR 报 500” → ask for requestId first | Resolve service, then probe. |
| Probe failed → ask user for more info | Send ERP and finish silently without Qiyu. |
| Probe failed → notify user through `qiyu_send_message` | Do not send a Qiyu message for probe failure; only ERP is sent. |
| Probe normal + no requestId → query logs anyway | Ask for request context. |
| `paas_query_logs` returns `hits=[]` → summarize auth failure | Treat this as “no matching logs found”; send ERP and finish without user-facing diagnosis. |
| Logs unavailable → abandon case | Send ERP with safe failure summary. |
