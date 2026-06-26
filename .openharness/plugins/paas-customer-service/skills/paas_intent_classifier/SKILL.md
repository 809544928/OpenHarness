---
name: paas-intent-classifier
description: Use when classifying PaaS customer messages into access documentation, service error, or unsupported scenarios
---

# PaaS Intent Classifier

## Overview

Classify each customer message into exactly one supported PaaS preprocessing scenario: `access_docs`, `service_error`, or `other`.

## When to Use

- A new user message arrives and there is no active `agentState.waitingFor` flow.
- A pending flow is complete and the current turn may start a new PaaS scenario.
- A message must be routed before service resolution or tool calls.

## Scenario Definitions

| Scenario | Use when |
|---|---|
| `access_docs` | User asks how to access, integrate, call, configure, test, authenticate, get examples for, or use a PaaS service. |
| `service_error` | User reports an error, failure, abnormal response, status code, timeout, auth issue, billing-related call failure, production problem, or degraded service behavior. |
| `other` | User asks unrelated questions, chats casually, asks identity questions, requests unsupported business actions, or provides content with no PaaS business intent. |

## Classification Rules

1. If the user asks for documentation, examples, integration, usage, quickstart, SDK, configuration, or authentication steps, choose `access_docs`.
2. If the user reports something broken, slow, rejected, timed out, failing, returning bad data, or producing an error code, choose `service_error`.
3. If the text is ambiguous but contains an error symptom, prefer `service_error`.
4. If the text is ambiguous but asks “怎么接入”, “怎么调用”, “文档在哪”, or “如何配置”, prefer `access_docs`.
5. If no PaaS intent exists, choose `other`.
6. Do not resolve service identity in this skill; classification and service resolution are separate steps.

## Examples

| User message | Scenario | Reason |
|---|---|---|
| OCR 怎么接入？ | `access_docs` | Asks for integration. |
| 语音合成接口怎么调？ | `access_docs` | Asks for API usage. |
| ASR 文档在哪里？ | `access_docs` | Asks for documentation. |
| 接口一直 500 | `service_error` | Reports status code failure. |
| OCR 报 401 | `service_error` | Reports auth/status error. |
| 请求超时了 | `service_error` | Reports timeout. |
| 返回结果不对 | `service_error` | Reports abnormal response. |
| 你是谁？ | `other` | Identity question, not PaaS business flow. |
| 你好 | `other` | Greeting only. |

## Output Contract

Return or use one of these exact scenario values:

```text
access_docs
service_error
other
```

## Common Mistakes

| Mistake | Correct behavior |
|---|---|
| Treating “接口报错” as `other` because no service is named | Classify as `service_error`; service resolution can ask follow-up. |
| Treating “怎么调用” as `other` because it lacks a service | Classify as `access_docs`; service resolution can ask follow-up. |
| Mixing classification with service lookup | Classify first, then use `paas_resolve_service`. |
| Creating new scenario names | Use only the three allowed scenario values. |
