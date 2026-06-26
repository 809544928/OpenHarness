# PaaS 智能客服 OpenHarness 执行文档

## 0. 执行目标

本执行文档用于把 `docs/SDD/design.md` 中的方案 B：

> 服务知识放 Skill，真实调用做通用 Tool

落地为一个 OpenHarness 插件：

```text
.openharness/plugins/paas-customer-service/
```

第一版目标是打通最小闭环：

1. 用户问接入文档。
2. 用户反馈服务报错。
3. OpenHarness 能识别服务、追问、调用 probe、查日志、发 ERP、发七鱼消息。
4. 每轮最终输出 Java 可解析的最小 JSON。
5. Skill 只写知识、规则、话术、流程。
6. Tool 执行真实外部调用。

---

## 1. 推荐最终目录结构

建议按下面结构创建：

```text
.openharness/plugins/paas-customer-service/
  plugin.json
  skills/
    paas_customer_service_router/SKILL.md
    paas_intent_classifier/SKILL.md
    paas_service_resolver/SKILL.md
    paas_clarification_policy/SKILL.md
    paas_access_docs_flow/SKILL.md
    paas_service_error_flow/SKILL.md
    paas_response_composer/SKILL.md
    services/
      ocr/SKILL.md
      tts/SKILL.md
      asr/SKILL.md
  tools/
    _models.py
    _service_registry.py
    _idempotency.py
    _errors.py
    _config.py
    _http.py
    paas_resolve_service_tool.py
    paas_get_manual_url_tool.py
    paas_probe_service_tool.py
    paas_query_logs_tool.py
    paas_send_erp_message_tool.py
    qiyu_send_message_tool.py
    paas_finish_decision_tool.py
  config/
    paas-services.example.yaml
```

本功能不新增 `src/openharness/paas` 或其他主源码目录。所有业务 Skill、外部调用 Tool、服务注册表、PaaS 模型、幂等与错误处理都收敛在 `.openharness/plugins/paas-customer-service/` 插件内；主源码只依赖 OpenHarness 现有插件加载机制。

测试目录：

```text
tests/test_plugins/test_paas_customer_service/
  test_service_registry.py
  test_paas_resolve_service_tool.py
  test_paas_get_manual_url_tool.py
  test_paas_probe_service_tool.py
  test_paas_query_logs_tool.py
  test_paas_send_erp_message_tool.py
  test_qiyu_send_message_tool.py
  test_paas_finish_decision_tool.py
  test_paas_cli_integration.py
```

---

## 2. 总体执行顺序

建议按下面顺序做，不要一口气把所有 Skill 和 Tool 都写完。

### Phase 1：先写总 Skill 和最终出口 Tool

目标：先保证 Agent 有统一身份、流程约束和最终 JSON 出口。

需要完成：

1. 写 `plugin.json`。
2. 写总入口 Skill：`paas_customer_service_router/SKILL.md`。
3. 定义输入输出模型。
4. 实现 `paas_finish_decision`。
5. 验证 OpenHarness 最终能输出 Java 可解析 JSON。

### Phase 2：服务注册表 + 服务识别 + 接入文档场景

目标：先打通最简单业务：用户问 “OCR 怎么接入？”。

需要完成：

1. 写 `.openharness/plugins/paas-customer-service/config/paas-services.example.yaml`。
2. 实现 `service_registry.py`。
3. 实现 `paas_resolve_service`。
4. 实现 `paas_get_manual_url`。
5. 写 `paas_intent_classifier`、`paas_service_resolver`、`paas_access_docs_flow`。
6. 写 OCR/TTS/ASR 服务知识 Skill 的最小版本。
7. 验证 “怎么接入？” 会追问服务，“OCR 怎么接入？” 会发 OCR 文档链接并结束。

### Phase 3：七鱼消息 Tool

目标：所有用户可见回复都通过 `qiyu_send_message` 发出。

需要完成：

1. 实现 `qiyu_send_message`。
2. 实现幂等键。
3. 实现错误处理。
4. 修改文档场景流程，使追问和文档回复都调用七鱼 Tool。
5. 验证 Java 不需要解析 `replyToUser`，只保存 OpenHarness 摘要。

### Phase 4：服务报错场景

目标：打通 “OCR 报错” 的完整客服闭环。

需要完成：

1. 实现 `paas_probe_service`。
2. 实现 `paas_query_logs`。
3. 实现 `paas_send_erp_message`。
4. 写 `paas_service_error_flow`。
5. 写 `paas_response_composer`。
6. 验证 probe 异常、probe 正常追问 requestId、收到 requestId 后查日志并发 ERP。

### Phase 5：治理、白名单、安全和验收

目标：让 PaaS Agent 只能使用专用工具，不能自由 Bash/curl。

需要完成：

1. 限制 PaaS Agent 可见工具集合。
2. 禁止 Bash、文件写入、子代理、任意 MCP。
3. 给 probe 增加超时、限流、熔断。
5. 补完整 CLI 集成测试。
6. 确认 Java 只解析最小 JSON，不解析自然语言。

---

## 3. 第一步：创建插件骨架

### 3.1 创建目录

```text
.openharness/plugins/paas-customer-service/
  plugin.json
  skills/
  tools/
```

### 3.2 编写 `plugin.json`

路径：

```text
.openharness/plugins/paas-customer-service/plugin.json
```

内容框架：

```json
{
  "name": "paas-customer-service",
  "version": "1.0.0",
  "description": "PaaS customer-service preprocessing agent for service docs, demo probes, log lookup, ERP escalation, and Qiyu messaging.",
  "enabled_by_default": true,
  "skills_dir": "skills",
  "tools_dir": "tools"
}
```

注意：

1. 项目插件默认可能不加载。
2. 部署时需要确认 `allow_project_plugins=true`。
3. 如果生产不允许项目插件，可以后续改成用户级插件或内置工具。

---

## 4. 第二步：写总入口 Skill

### 4.1 文件路径

```text
.openharness/plugins/paas-customer-service/skills/paas_customer_service_router/SKILL.md
```

### 4.2 作用

这是整个 PaaS 客服 Agent 的总规则入口。

它不负责写某个服务的详细接入说明，而是规定：

1. Agent 是什么角色。
2. 每轮必须怎么判断场景。
3. 什么时候追问。
4. 什么时候调用 Tool。
5. 什么时候结束。
6. 每轮必须调用 `paas_finish_decision` 输出最终结构化结果。
7. 不能自己 Bash/curl。
8. 不能编造服务、URL、日志、ERP 结果。

### 4.3 推荐 SKILL.md 框架

```markdown
---
name: paas-customer-service-router
description: Use when handling PaaS customer-service preprocessing messages from Qiyu or another customer-service platform
---

# PaaS Customer Service Router

## Overview

You are a PaaS customer-service preprocessing agent.

Your job is to classify the user message, identify the related PaaS service, decide whether to ask a clarification question, call approved tools when real external actions are needed, and finish every turn with a structured decision.

## Hard Rules

1. You MUST use registered tools for real external actions.
2. You MUST NOT run curl, Bash, shell commands, or copied examples from skills.
3. You MUST NOT invent service IDs.
4. You MUST NOT invent manual URLs.
5. You MUST NOT invent probe, log, ERP, or Qiyu results.
6. You MUST send user-visible messages through `qiyu_send_message`.
7. You MUST finish each turn through `paas_finish_decision`.
8. Java only saves your final structured result; Java does not send fallback user messages.

## Allowed Scenarios

| Scenario | Meaning |
|---|---|
| `access_docs` | User asks how to access, integrate, call, configure, or use a service. |
| `service_error` | User reports errors, failures, status codes, bad responses, timeout, auth problems, or abnormal service behavior. |
| `other` | Message is unrelated or cannot be handled by the PaaS preprocessing agent. |

## Top-Level Flow

1. Read current message, history, and agentState.
2. If `agentState.waitingFor` exists, continue the pending flow first.
3. Classify scenario.
4. Resolve service through `paas_resolve_service` when service identity matters.
5. If service is unclear, ask a clarification question through `qiyu_send_message`.
6. For access docs, use `paas_get_manual_url`.
7. For service errors, call `paas_probe_service` after service is clear.
8. If probe fails, send ERP and notify user.
9. If probe succeeds but request context is missing, ask for appKey/requestId.
10. If request context is available, query logs, send ERP, notify user.
11. Finish through `paas_finish_decision`.

## Flow Rules

### Access Docs

- If service is unclear, ask which service the user wants.
- If service is clear, get manual URL from `paas_get_manual_url`.
- Send the document message through `qiyu_send_message`.
- Finish with `terminal=true`.

### Service Error

- If service is unclear, ask for service name.
- If service is clear, call `paas_probe_service` first.
- If probe is unavailable, failed, timed out, or abnormal, send ERP.
- If probe is normal and requestId/appKey is missing, ask for request context.
- If requestId/appKey exists, call `paas_query_logs`, then send ERP.
- After ERP, notify user and finish with `terminal=true`.

### Other

- Do not call probe, logs, or ERP.
- Optionally send a short unsupported-scope message.
- Finish with `terminal=true`.

## Final Decision Requirement

Every turn MUST end by calling `paas_finish_decision`.

The final result must include:

- `conversationId`
- `action`
- `toolResults`
- `newState`
- `terminal`

## Common Mistakes

| Mistake | Correct behavior |
|---|---|
| Writing a manual URL from memory | Use `paas_get_manual_url`. |
| Guessing service ID from text | Use `paas_resolve_service`. |
| Running curl from a service skill | Never do this; call the proper Tool. |
| Returning natural language only | Always finish with `paas_finish_decision`. |
| Asking Java to send the message | Use `qiyu_send_message`. |
```

---

## 5. 第三步：写意图识别 Skill

### 5.1 文件路径

```text
.openharness/plugins/paas-customer-service/skills/paas_intent_classifier/SKILL.md
```

### 5.2 作用

负责把用户消息归类成：

```text
access_docs
service_error
other
```

### 5.3 框架

```markdown
---
name: paas-intent-classifier
description: Use when classifying PaaS customer messages into access documentation, service error, or unsupported scenarios
---

# PaaS Intent Classifier

## Overview

Classify each user message into one of three PaaS customer-service scenarios.

## Scenario Definitions

| Scenario | Use when |
|---|---|
| `access_docs` | User asks how to access, integrate, call, configure, test, or use a PaaS service. |
| `service_error` | User reports an error, failure, abnormal response, status code, timeout, auth issue, billing-related call failure, or production problem. |
| `other` | User asks unrelated questions, chats casually, asks identity questions, or gives insufficient non-PaaS content. |

## Examples

| User message | Scenario |
|---|---|
| OCR 怎么接入？ | `access_docs` |
| 语音合成接口怎么调？ | `access_docs` |
| 接口一直 500 | `service_error` |
| OCR 报 401 | `service_error` |
| 请求超时了 | `service_error` |
| 你是谁？ | `other` |
| 你好 | `other` |

## Rules

1. If the user asks for documentation, examples, integration, or usage, choose `access_docs`.
2. If the user reports something broken, choose `service_error`.
3. If the text is ambiguous but mentions an error symptom, prefer `service_error`.
4. If no PaaS business intent exists, choose `other`.
```

---

## 6. 第四步：写服务识别 Skill

### 6.1 文件路径

```text
.openharness/plugins/paas-customer-service/skills/paas_service_resolver/SKILL.md
```

### 6.2 作用

规定如何从用户文本中提取候选服务词，并调用：

```text
paas_resolve_service
```

### 6.3 框架

```markdown
---
name: paas-service-resolver
description: Use when a PaaS customer message may mention a product, service, API, alias, or ambiguous service name
---

# PaaS Service Resolver

## Overview

Service identity must come from the service registry through `paas_resolve_service`.

## Resolution Flow

1. Extract possible service words from the user message.
2. Call `paas_resolve_service` with the current message and candidate if available.
3. Use the returned `serviceId` only when `ambiguous=false`.
4. If no unique service is resolved, ask a clarification question.
5. Never invent a service ID.

## Tool to Use

```json
{
  "tool": "paas_resolve_service",
  "input": {
    "message": "<current user message>",
    "candidate": "<optional candidate service word>"
  }
}
```

## Ambiguity Rules

| Case | Behavior |
|---|---|
| One high-confidence service | Continue with returned `serviceId`. |
| Multiple possible services | Ask user to choose. |
| Generic words only, such as “接口”, “服务”, “平台” | Treat as unclear. |
| User provides service in later turn | Resolve again using current message and history. |

## Clarification Example

If service is unclear:

```text
请问你反馈的是 OCR、TTS、ASR 中的哪一个服务？
```

The exact candidate list should come from the tool result when available.
```

---

## 7. 第五步：写追问策略 Skill

### 7.1 文件路径

```text
.openharness/plugins/paas-customer-service/skills/paas_clarification_policy/SKILL.md
```

### 7.2 作用

统一规定什么时候追问、最多追问几次、状态怎么写。

### 7.3 框架

```markdown
---
name: paas-clarification-policy
description: Use when a PaaS customer-service flow lacks required service or request context and must ask the user for missing information
---

# PaaS Clarification Policy

## Overview

Ask concise clarification questions when required information is missing.

## Missing Information Types

| waitingFor | Meaning |
|---|---|
| `service` | The related PaaS service is unclear. |
| `request_context` | Service is clear, but appKey/requestId/time context is missing. |

## Clarification Limits

- Ask at most 2 clarification questions for the same scenario.
- If the limit is reached, submit ERP follow-up or finish according to erp_followup policy.

## Service Clarification

Ask when:

1. Scenario is `access_docs` and service is unclear.
2. Scenario is `service_error` and service is unclear.

Example:

```text
请问你要咨询的是 OCR、TTS 还是 ASR 服务？
```

## Request Context Clarification

Ask when:

1. Scenario is `service_error`.
2. Service is clear.
3. Probe is normal.
4. requestId/appKey is missing.

Example:

```text
线上 demo 检测暂未发现服务整体异常。请提供 appKey 和 requestId，如果方便也可以补充报错时间，方便客服进一步排查。
```

## State Updates

When asking for service:

```json
{
  "waitingFor": "service",
  "clarificationCount": 1,
  "terminal": false
}
```

When asking for request context:

```json
{
  "waitingFor": "request_context",
  "clarificationCount": 1,
  "terminal": false
}
```
```

---

## 8. 第六步：写接入文档流程 Skill

### 8.1 文件路径

```text
.openharness/plugins/paas-customer-service/skills/paas_access_docs_flow/SKILL.md
```

### 8.2 作用

处理：

```text
OCR 怎么接入？
TTS 怎么调用？
语音识别文档在哪里？
```

### 8.3 框架

```markdown
---
name: paas-access-docs-flow
description: Use when a PaaS customer asks for service access, integration, quickstart, API usage, or documentation
---

# PaaS Access Docs Flow

## Overview

For access documentation requests, resolve the service, get the manual URL from the registry, send a short message, and finish.

## Required Tools

1. `paas_resolve_service`
2. `paas_get_manual_url`
3. `qiyu_send_message`
4. `paas_finish_decision`

## Flow: Service Unclear

1. Resolve service.
2. If no unique service is found, ask which service the user wants.
3. Send clarification through `qiyu_send_message`.
4. Finish with `terminal=false`.

Expected state:

```json
{
  "scenario": "access_docs",
  "serviceId": null,
  "waitingFor": "service",
  "terminal": false
}
```

## Flow: Service Clear

1. Resolve service.
2. Call `paas_get_manual_url`.
3. Compose a short document message.
4. Send through `qiyu_send_message`.
5. Finish with `terminal=true`.

## Message Template

```text
这是 {displayName} 的接入文档：{manualUrl}

你可以先按快速开始完成鉴权、参数配置和 demo 调用。如果接入过程中遇到具体报错，可以把服务名、appKey 和 requestId 发给我们继续排查。
```

## Final State

```json
{
  "scenario": "access_docs",
  "serviceId": "<serviceId>",
  "waitingFor": null,
  "terminal": true,
  "terminalReason": "manual_sent"
}
```

## Mistakes to Avoid

| Mistake | Correct behavior |
|---|---|
| Returning a guessed document URL | Call `paas_get_manual_url`. |
| Sending several generic docs when service is unclear | Ask the user to specify the service. |
| Ending without sending Qiyu message | Use `qiyu_send_message`. |
```

---

## 9. 第七步：写服务报错流程 Skill

### 9.1 文件路径

```text
.openharness/plugins/paas-customer-service/skills/paas_service_error_flow/SKILL.md
```

### 9.2 作用

处理：

```text
OCR 报 500
接口一直 401
请求超时
服务返回错误码
```

### 9.3 框架

```markdown
---
name: paas-service-error-flow
description: Use when a PaaS customer reports API errors, failed calls, status codes, timeout, authentication errors, or abnormal service behavior
---

# PaaS Service Error Flow

## Overview

For service errors, resolve the service first. Once the service is clear, probe the online demo before asking for request context or escalating to ERP.

## Required Tools

1. `paas_resolve_service`
2. `paas_probe_service`
3. `paas_query_logs`
4. `paas_send_erp_message`
5. `qiyu_send_message`
6. `paas_finish_decision`

## Flow A: Service Unclear

1. Classify scenario as `service_error`.
2. Call `paas_resolve_service`.
3. If service is unclear, ask user for service name.
4. Finish with `terminal=false`.

State:

```json
{
  "scenario": "service_error",
  "serviceId": null,
  "waitingFor": "service",
  "terminal": false
}
```

## Flow B: Service Clear, Probe Fails

1. Resolve service.
2. Call `paas_probe_service`.
3. If probe indicates unavailable, timeout, 5xx, network error, or abnormal response:
   - Call `paas_send_erp_message`.
   - Call `qiyu_send_message` to tell user the issue has been forwarded.
   - Finish with `terminal=true`.

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

## Flow C: Service Clear, Probe Normal, Missing Request Context

1. Resolve service.
2. Call `paas_probe_service`.
3. If probe is normal but requestId/appKey is missing:
   - Ask user for appKey/requestId.
   - Finish with `terminal=false`.

State:

```json
{
  "scenario": "service_error",
  "serviceId": "<serviceId>",
  "waitingFor": "request_context",
  "probeResult": {
    "available": true
  },
  "terminal": false
}
```

## Flow D: Waiting for Request Context, User Provides It

1. Read previous `agentState.waitingFor=request_context`.
2. Extract appKey, requestId, and optional time range.
3. Call `paas_query_logs`.
4. Call `paas_send_erp_message`.
5. Call `qiyu_send_message` to tell user the issue has been forwarded.
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

## Flow E: User Cannot Provide RequestId

If the user says they cannot provide requestId:

1. Do not loop forever.
2. Send ERP with user summary and probe summary.
3. Mention requestId was not provided.
4. Notify user.
5. Finish with `terminal=true`.

## Rules

1. Do not send ERP before probe if service is clear.
2. Do not ask for requestId before probe.
3. If probe fails, do not ask user for requestId.
4. If logs fail, still send ERP with log failure summary.
5. After ERP, notify user and finish.
```

---

## 10. 第八步：移除独立 ERP 跟进策略 Skill

不再创建独立的人工转接策略 Skill。服务报错流程中需要客服人员继续处理时，统一调用 `paas_send_erp_message` 提交 ERP；其他场景直接结束。

---

## 11. 第九步：写用户话术 Skill

### 11.1 文件路径

```text
.openharness/plugins/paas-customer-service/skills/paas_response_composer/SKILL.md
```

### 11.2 作用

统一规定发给用户的话术格式。

### 11.3 框架

```markdown
---
name: paas-response-composer
description: Use when composing short user-visible Qiyu messages for PaaS documentation, clarification, error escalation, or unsupported messages
---

# PaaS Response Composer

## Overview

User-visible messages should be short, clear, and action-oriented.

## General Style

1. Use concise Chinese.
2. Do not expose internal tool names.
3. Do not expose raw logs.
4. Do not expose tokens, headers, signatures, or internal URLs.
5. Tell the user what happened and what they can provide next.

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

### Probe Failure Escalated

```text
我们检测到 {displayName} 当前可能存在异常，已经提交客服人员继续排查，请稍候。
```

### Logs Queried and Escalated

```text
已收到你提供的信息，我们已经结合日志摘要提交客服人员继续排查，请稍候。
```

### Unsupported

```text
当前问题暂不在智能客服可处理范围内，我们会直接结束。
```

## Rules

1. Never mention hidden implementation details.
2. Never paste raw tool output.
3. Never include full appKey, token, cookie, or request payload.
4. Send messages through `qiyu_send_message`.
```

---

## 12. 第十步：写具体服务知识 Skill

每个服务一个 Skill。

### 12.1 OCR 示例路径

```text
.openharness/plugins/paas-customer-service/skills/services/ocr/SKILL.md
```

### 12.2 作用

服务知识 Skill 只提供：

1. 服务简介。
2. 别名。
3. 接入说明。
4. 常见错误码解释。
5. 排障建议。
6. demo probe 的业务含义。
7. curl 示例模板。

但不能执行真实请求，不能包含真实密钥。

### 12.3 OCR Skill 框架

```markdown
---
name: paas-service-ocr
description: Use when handling OCR text-recognition service knowledge, aliases, access guidance, common errors, or troubleshooting context
---

# OCR Service Knowledge

## Overview

OCR 文字识别服务用于从图片中识别文字内容。

## Aliases

- OCR
- ocr
- 文字识别
- 图片识别
- 图像文字识别

## Access Guidance

Access documentation must come from `paas_get_manual_url`.

This skill may explain concepts, but must not invent manual URLs.

## Common Parameters

| Parameter | Meaning |
|---|---|
| `appKey` | Application key used for service authentication. |
| `requestId` | Request identifier used for troubleshooting and log lookup. |
| `image` | Image input or image URL, depending on the actual API contract. |

## Common Errors

| Symptom | Possible meaning | Next step |
|---|---|---|
| 401 | Authentication failed, appKey invalid, signature expired, or permission missing. | Ask for appKey and requestId after probe succeeds. |
| 400 | Request parameter or image format may be invalid. | Ask user to check required parameters and image format. |
| 500 | Service or upstream dependency may be abnormal. | Probe service first. |
| Timeout | Network, service load, or upstream timeout. | Probe service first. |

## Demo Probe Meaning

The OCR demo probe checks whether the standard OCR demo endpoint is generally available.

Probe results do not prove the user's specific request is correct.

## Curl Example Template

The following curl is only an explanation template.

The agent MUST NOT execute it directly.

```bash
curl -X POST "https://example.invalid/ocr/demo" \
  -H "Authorization: <token-from-secure-config>" \
  -H "Content-Type: application/json" \
  -d '{"image":"<demo-image>"}'
```

## Safety Rules

1. Do not include real token, cookie, appSecret, or production signature.
2. Do not execute curl from this skill.
3. Real probe must use `paas_probe_service`.
4. Real log lookup must use `paas_query_logs`.
```

TTS / ASR 可以复制这个结构改服务名和错误说明。

---

## 13. 第十一步：写服务注册表配置

### 13.1 路径

```text
.openharness/plugins/paas-customer-service/config/paas-services.example.yaml
```

### 13.2 框架

```yaml
services:
  - id: ocr
    displayName: OCR 文字识别
    aliases:
      - ocr
      - OCR
      - 文字识别
      - 图片识别
    manualUrl: "https://docs.example.com/ocr/quickstart"
    probe:
      type: http
      method: POST
      url: "https://api.example.com/ocr/demo"
      timeoutMs: 3000
      requestTemplateRef: "ocr-default"
    log:
      stream_name: "paas-ocr"
    erp:
      product: "paas-ocr"
      message: "用户反馈 OCR 服务异常，请客服结合 probe 和日志摘要跟进。"

  - id: tts
    displayName: TTS 语音合成
    aliases:
      - tts
      - TTS
      - 语音合成
      - 文本转语音
    manualUrl: "https://docs.example.com/tts/quickstart"
    probe:
      type: http
      method: POST
      url: "https://api.example.com/tts/demo"
      timeoutMs: 3000
      requestTemplateRef: "tts-default"
    log:
      stream_name: "paas-tts"
    erp:
      product: "paas-tts"
      message: "用户反馈 TTS 服务异常，请客服结合 probe 和日志摘要跟进。"

  - id: asr
    displayName: ASR 语音识别
    aliases:
      - asr
      - ASR
      - 语音识别
      - 音频转文字
    manualUrl: "https://docs.example.com/asr/quickstart"
    probe:
      type: http
      method: POST
      url: "https://api.example.com/asr/demo"
      timeoutMs: 3000
      requestTemplateRef: "asr-default"
    log:
      stream_name: "paas-asr"
    erp:
      product: "paas-asr"
      message: "用户反馈 ASR 服务异常，请客服结合 probe 和日志摘要跟进。"
```

---

## 14. 第十二步：定义公共 PaaS 模型

### 14.1 路径

```text
.openharness/plugins/paas-customer-service/tools/_models.py
```

`_models.py` 是插件内部私有模块，不进入 `src/openharness`。OpenHarness 插件加载器会扫描 `tools/*.py` 中的 Tool，但跳过 `_` 开头的文件，因此 `_models.py`、`_service_registry.py`、`_idempotency.py`、`_errors.py` 等可以作为插件内部共享代码使用。

### 14.2 建议模型

需要定义：

1. `PaaSAgentInput`
2. `PaaSAgentOutput`
3. `PaaSAgentState`
4. `ToolResultSummary`
5. `ServiceDefinition`
6. `ServiceProbeConfig`
7. `ServiceLogConfig`
8. `ServiceErpConfig`

### 14.3 模型字段框架

```python
class PaaSAgentInput(BaseModel):
    conversation_id: str = Field(alias="conversationId")
    platform_session_id: str = Field(alias="platformSessionId")
    platform_user_id: str | None = Field(default=None, alias="platformUserId")
    staff_id: str | None = Field(default=None, alias="staffId")
    message: str
    history: list[dict[str, str]] = Field(default_factory=list)
    agent_state: dict[str, Any] = Field(default_factory=dict, alias="agentState")


class PaaSAgentState(BaseModel):
    scenario: str | None = None
    service_id: str | None = None
    waiting_for: str | None = None
    clarification_count: int = 0
    probe_result: dict[str, Any] | None = None
    log_result: dict[str, Any] | None = None
    erp_sent: bool = False
    erp_message_id: str | None = None
    terminal: bool = False
    terminal_reason: str | None = None


class ToolResultSummary(BaseModel):
    tool: str
    success: bool
    summary: str


class PaaSAgentOutput(BaseModel):
    conversation_id: str
    action: str
    tool_results: list[ToolResultSummary]
    new_state: PaaSAgentState
    terminal: bool
```

注意：本插件与 Java 交互统一使用 camelCase JSON。Python 模型内部可使用 snake_case，但必须通过 Pydantic alias 接受和输出 camelCase。

### 14.4 Java 上游调用 OpenHarness 的入参 JSON

Java 每轮调用 OpenHarness 时传入一个 JSON 对象，作为 Agent 的当前 turn 上下文。最小格式如下：

```json
{
  "conversationId": "qiyu:6383959733",
  "platformSessionId": "6383959733",
  "platformUserId": "81275614-ff4c-490e-9517-0934f4fc9325@顺风车乘客",
  "staffId": "4126122",
  "message": "OCR 怎么接入？",
  "history": [],
  "agentState": {
    "terminal": false
  }
}
```

顶层字段契约：

| key | 必填 | 类型 | 含义 |
|---|---:|---|---|
| `conversationId` | 是 | string | Java 和客服平台侧稳定会话 ID，建议带平台前缀，例如 `qiyu:6383959733`。 |
| `platformSessionId` | 是 | string | 七鱼或其他客服平台原始会话 ID，供七鱼发消息和ERP 跟进 Tool 使用。 |
| `platformUserId` | 否 | string/null | 客服平台用户 ID，供七鱼、ERP 上下文和排查追踪使用。 |
| `staffId` | 否 | string/null | 当前客服、机器人或坐席 ID；没有时可省略。 |
| `message` | 是 | string | 用户本轮最新消息。 |
| `history` | 否 | array | 最近若干轮消息，建议每项包含 `role` 和 `content`；可传空数组。 |
| `agentState` | 否 | object | 上轮最终输出的 `newState`；没有上轮状态时可传 `{}` 或 `{ "terminal": false }`。 |

`history` 建议格式：

```json
[
  {"role": "user", "content": "接口报错"},
  {"role": "assistant", "content": "请问你反馈的是 OCR、TTS 还是 ASR 服务？"}
]
```

Java 必须把本轮最终输出中的 `newState` 持久化，并在下一轮原样作为 `agentState` 传回。Java 不解析自然语言，不判断业务分支，也不发送兜底用户消息；用户可见消息统一由 `qiyu_send_message` Tool 发送。

---

## 15. 第十三步：实现 Tool 框架

下面是每个 Tool 的用途和参数框架。

### 15.1 `paas_resolve_service`

文件：

```text
.openharness/plugins/paas-customer-service/tools/paas_resolve_service_tool.py
```

作用：从服务注册表中解析服务。

入参：

```json
{
  "message": "OCR 服务一直报 401",
  "candidate": "OCR"
}
```

出参：

```json
{
  "serviceId": "ocr",
  "confidence": 0.98,
  "ambiguous": false,
  "candidates": [
    {
      "serviceId": "ocr",
      "displayName": "OCR 文字识别"
    }
  ]
}
```

必须实现的校验：

1. 只能返回注册表中存在的服务。
2. 多义时 `ambiguous=true`。
3. 低置信度时不强行返回服务。
4. 不允许模型自由传入服务 ID 后绕过注册表。

### 15.2 `paas_get_manual_url`

文件：

```text
.openharness/plugins/paas-customer-service/tools/paas_get_manual_url_tool.py
```

作用：按服务 ID 获取接入文档。

入参：

```json
{
  "serviceId": "ocr"
}
```

出参：

```json
{
  "serviceId": "ocr",
  "displayName": "OCR 文字识别",
  "manualUrl": "https://docs.example.com/ocr/quickstart"
}
```

必须实现的校验：

1. `serviceId` 必须存在于注册表。
2. URL 只能来自注册表。
3. 找不到时返回工具错误，不让模型编造 URL。

### 15.3 `paas_probe_service`

文件：

```text
.openharness/plugins/paas-customer-service/tools/paas_probe_service_tool.py
```

作用：执行服务 demo probe，判断线上服务是否可用。

入参：

```json
{
  "serviceId": "ocr",
}
```

出参：

```json
{
  "serviceId": "ocr",
  "available": true,
  "statusCode": 200,
  "latencyMs": 128,
  "errorType": null,
  "responseSample": "{\"code\":0,\"message\":\"ok\"}"
}
```

必须实现的校验：

1. endpoint、method、timeout 来自注册表。
2. 凭据来自环境变量、安全配置或本地安全配置。
3. 用户输入不能控制真实 endpoint。
4. 必须设置超时。
5. 必须限制响应体长度。
7. 必须分类：`ok`、`http_4xx`、`http_5xx`、`timeout`、`network_error`、`invalid_response`、`auth_error`。

### 15.4 `paas_query_logs`

文件：

```text
.openharness/plugins/paas-customer-service/tools/paas_query_logs_tool.py
```

作用：根据结构化字段查日志，返回摘要。

入参：

```json
{
  "serviceId": "ocr",
  "appKey": "app_xxx",
  "requestId": "req-abc-123",
  "timeRange": {
    "start": "2026-06-23T10:00:00Z",
    "end": "2026-06-23T11:00:00Z"
  }
}
```

出参：

```json
{
  "serviceId": "ocr",
  "matched": true,
  "entries": 3,
  "summary": "found OCR auth errors around requestId req-abc-123",
  "highlights": [
    "401 invalid appKey at 2026-06-23T10:12:03Z",
    "upstream request rejected by auth gateway"
  ]
}
```

禁止参数：

```json
{
  "rawQuery": "...",
  "dsl": "...",
  "sql": "...",
  "lucene": "..."
}
```

必须实现的校验：

1. 只能按 `serviceId + appKey + requestId + timeRange` 查询。
2. 日志流来自注册表。
4. 返回条数必须限制。
5. 返回长度必须限制。
6. 查询失败时返回错误摘要，不抛给模型原始异常。

### 15.5 `paas_send_erp_message`

文件：

```text
.openharness/plugins/paas-customer-service/tools/paas_send_erp_message_tool.py
```

作用：把用户反馈、probe 摘要、日志摘要发送到 ERP 或内部工单系统。

入参：

```json
{
  "serviceId": "ocr",
  "userSummary": "用户反馈 OCR 报 401，已提供 requestId。",
  "probeSummary": "online probe succeeded",
  "logSummary": "found 3 auth error entries",
  "platformContext": {
    "conversationId": "qiyu:6383959733",
    "platformSessionId": "6383959733",
    "platformUserId": "81275614-ff4c-490e-9517-0934f4fc9325@顺风车乘客"
  },
}
```

出参：

```json
{
  "erpMessageId": "erp-10086",
  "ticketUrl": "https://erp.example.com/tickets/erp-10086",
  "sentAt": "2026-06-23T10:20:00Z"
}
```

必须实现的校验：

1. 必须幂等。
2. ERP product/message 模板来自注册表。
4. 不携带完整 appKey、token、header、cookie。
5. 失败时返回明确错误类型。

### 15.6 `qiyu_send_message`

文件：

```text
.openharness/plugins/paas-customer-service/tools/qiyu_send_message_tool.py
```

作用：给七鱼会话发送用户可见文本。

入参：

```json
{
  "conversationId": "qiyu:6383959733",
  "platformSessionId": "6383959733",
  "platformUserId": "81275614-ff4c-490e-9517-0934f4fc9325@顺风车乘客",
  "staffId": "4126122",
  "messageType": "TEXT",
  "content": "请问你反馈的是 OCR、TTS 还是 ASR 服务？",
}
```

出参：

```json
{
  "sent": true,
  "messageId": "qiyu-msg-10086"
}
```

必须实现的校验：

1. 必须幂等。
2. content 长度限制。
3. 七鱼鉴权由 Tool 内部处理。
4. 不返回 token、签名、完整响应体。


### 15.7 `paas_finish_decision`

文件：

```text
.openharness/plugins/paas-customer-service/tools/paas_finish_decision_tool.py
```

作用：作为每轮最终出口，保证 Java 可以解析固定 JSON。

入参：

```json
{
  "conversationId": "qiyu:6383959733",
  "action": "clarify_service",
  "toolResults": [
    {
      "tool": "qiyu_send_message",
      "success": true,
      "summary": "sent service clarification"
    }
  ],
  "newState": {
    "scenario": "service_error",
    "serviceId": null,
    "waitingFor": "service",
    "clarificationCount": 1,
    "terminal": false
  },
  "terminal": false
}
```

出参直接返回 Java 需要的最终 JSON。

必须实现的校验：

1. `conversationId` 必填。
2. `terminal` 必须等于 `newState.terminal`。
3. `scenario` 必须是枚举：`access_docs`、`service_error`、`other`。
4. `waitingFor` 必须是枚举或 null：`service`、`request_context`。
5. 如果 `terminal=false`，通常必须有 `waitingFor`。
6. 如果服务报错且服务明确，但没有 probe 结果，不允许直接 ERP 或结束。
7. 非终态必须设置 `waitingFor`，服务不明确时继续追问服务。

---

## 16. 第十四步：每个 Tool 的通用代码骨架

具体项目里的 `BaseTool` 结构要按现有代码适配，但每个 Tool 建议统一有：

```python
from pydantic import BaseModel, Field

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult


class ExampleInput(BaseModel):
    service_id: str = Field(..., description="Registered PaaS service ID.")


class ExampleTool(BaseTool):
    name = "example_tool"
    description = "..."

    input_model = ExampleInput

    async def execute(self, arguments: ExampleInput, context: ToolExecutionContext) -> ToolResult:
        del context
        try:
            # 1. validate
            # 2. load registry/config from the plugin directory
            # 3. perform action
            # 4. return JSON text that Java can parse
            return ToolResult(
                output=json.dumps(
                    {"summary": "..."},
                    ensure_ascii=False,
                ),
                is_error=False,
            )
        except Exception as exc:
            return ToolResult(
                output=json.dumps(
                    {
                        "error": "tool_error",
                        "summary": "operation failed",
                    },
                    ensure_ascii=False,
                ),
                is_error=True,
                metadata={"exception": type(exc).__name__},
            )
```

实现时按当前 OpenHarness 的 `BaseTool` 实际接口编写：`execute(arguments, context)` 返回 `ToolResult(output: str, is_error: bool = False, metadata: dict = ...)`。`output` 建议始终是 `json.dumps(..., ensure_ascii=False)` 后的 JSON 字符串，不直接返回 dict。

---

## 17. 第十五步：测试顺序

### 17.1 先测注册表

```bash
pytest tests/test_plugins/test_paas_customer_service/test_service_registry.py -v
```

覆盖：

1. 加载 YAML。
2. 服务 ID 唯一。
3. alias 匹配。
4. 找不到服务。
5. 多义服务。

### 17.2 再测每个 Tool

```bash
pytest tests/test_plugins/test_paas_customer_service/test_paas_resolve_service_tool.py -v
pytest tests/test_plugins/test_paas_customer_service/test_paas_get_manual_url_tool.py -v
pytest tests/test_plugins/test_paas_customer_service/test_paas_probe_service_tool.py -v
pytest tests/test_plugins/test_paas_customer_service/test_paas_query_logs_tool.py -v
pytest tests/test_plugins/test_paas_customer_service/test_paas_send_erp_message_tool.py -v
pytest tests/test_plugins/test_paas_customer_service/test_qiyu_send_message_tool.py -v
pytest tests/test_plugins/test_paas_customer_service/test_paas_finish_decision_tool.py -v
```

### 17.3 最后测 CLI 集成

```bash
pytest tests/test_plugins/test_paas_customer_service/test_paas_cli_integration.py -v
```

建议覆盖 7 个场景：

| 输入 | 期望 |
|---|---|
| 怎么接入？ | 追问服务，`terminal=false` |
| OCR 怎么接入？ | 发文档，`terminal=true` |
| 接口报错 | 追问服务，`waitingFor=service` |
| OCR 报 500，probe 异常 | 发 ERP，`terminal=true` |
| OCR 报 401，probe 正常，缺 requestId | 追问 requestId/appKey |
| 上轮等待 requestId，本轮提供 requestId | 查日志，发 ERP，结束 |
| 你是谁？ | other，直接结束，不调用 probe/log/ERP |

---

## 18. 第十六步：手工烟测输入输出

### 18.1 输入文件

```json
{
  "conversationId": "qiyu:demo-1",
  "platformSessionId": "demo-1",
  "platformUserId": "user-1",
  "staffId": "staff-1",
  "message": "OCR 怎么接入？",
  "history": [],
  "agentState": {
    "terminal": false
  }
}
```

保存到：

```text
/tmp/paas-input.json
```

### 18.2 执行

```bash
PAAS_SERVICE_REGISTRY_PATH=.openharness/plugins/paas-customer-service/config/paas-services.example.yaml \
oh --print --output-format json --prompt-file /tmp/paas-input.json
```

### 18.3 期望输出

```json
{
  "conversationId": "qiyu:demo-1",
  "action": "manual_sent",
  "toolResults": [
    {
      "tool": "paas_get_manual_url",
      "success": true,
      "summary": "manual URL resolved"
    },
    {
      "tool": "qiyu_send_message",
      "success": true,
      "summary": "manual message sent"
    }
  ],
  "newState": {
    "scenario": "access_docs",
    "serviceId": "ocr",
    "waitingFor": null,
    "terminal": true,
    "terminalReason": "manual_sent"
  },
  "terminal": true
}
```

---

## 19. 推荐落地顺序清单

### 第一组：框架和总控

1. 创建插件目录。
2. 写 `plugin.json`。
3. 写 `paas_customer_service_router/SKILL.md`。
4. 写 `.openharness/plugins/paas-customer-service/tools/_models.py`。
5. 写 `paas_finish_decision_tool.py`。
6. 写 `test_paas_finish_decision_tool.py`。

### 第二组：服务注册表

1. 写 `.openharness/plugins/paas-customer-service/config/paas-services.example.yaml`。
2. 写 `service_registry.py`。
3. 写 `errors.py`。
4. 写 `test_service_registry.py`。

### 第三组：服务识别和文档场景

1. 写 `paas_intent_classifier/SKILL.md`。
2. 写 `paas_service_resolver/SKILL.md`。
3. 写 `paas_access_docs_flow/SKILL.md`。
4. 写 `paas_resolve_service_tool.py`。
5. 写 `paas_get_manual_url_tool.py`。
6. 写 OCR/TTS/ASR 服务知识 Skill 最小版本。
7. 写对应单元测试。
8. 跑通 “OCR 怎么接入？”。

### 第四组：七鱼消息

1. 写 `idempotency.py`。
3. 写 `qiyu_send_message_tool.py`。
4. 写 `test_qiyu_send_message_tool.py`。
5. 把文档回复和追问改成真实调用 `qiyu_send_message`。
6. 跑通文档场景完整闭环。

### 第五组：服务报错

1. 写 `paas_service_error_flow/SKILL.md`。
2. 写 `paas_response_composer/SKILL.md`。
3. 写 `paas_probe_service_tool.py`。
4. 写 `paas_query_logs_tool.py`。
5. 写 `paas_send_erp_message_tool.py`。
6. 写对应测试。
7. 跑通 probe 异常、probe 正常追问 requestId、requestId 到齐后查日志并 ERP。

### 第六组：ERP 跟进和治理

1. 写 `paas_erp_followup_policy/SKILL.md`。
2. 写 `paas_send_erp_message_tool.py`。
3. 限制 PaaS Agent 工具白名单。
4. 禁止 Bash/curl/file_write。
5. 加完整 CLI 集成测试。
6. 做手工烟测。

---

## 20. 每个 Skill 编写时的固定模板

后面具体填每个 Skill 时，建议统一用这个模板：

```markdown
---
name: <skill-name>
description: Use when <具体触发条件，不写流程总结>
---

# <Human Readable Skill Name>

## Overview

一句话说明这个 Skill 负责什么。

## When to Use

- 触发场景 1
- 触发场景 2
- 触发场景 3

## Required Tools

| Tool | Purpose |
|---|---|
| `<tool_name>` | 工具用途 |

## Flow

1. 第一步。
2. 第二步。
3. 第三步。

## Input Requirements

说明需要从 message/history/agentState/tool result 中拿什么信息。

## Output / State Requirements

说明 newState 应该如何更新。

## User Message Template

```text
用户可见话术模板。
```

## Safety Rules

1. 不得编造。
2. 不得执行 curl。

## Common Mistakes

| Mistake | Correct behavior |
|---|---|
| 错误做法 | 正确做法 |
```

---

## 21. 每个 Tool 编写时的固定模板

每个 Tool 建议按这个顺序写：

```text
1. 定义 InputModel。
2. 定义 OutputModel 或输出 dict 结构。
3. 加载服务注册表或外部配置。
4. 校验 serviceId / conversationId 等结构化字段。
5. 执行真实动作。
6. 对结果限长。
8. 分类错误。
9. 返回 ToolResult。
10. 写单元测试。
```

每个 Tool 的文档建议记录：

```markdown
# <tool_name>

## Purpose

这个 Tool 做什么真实动作。

## Input Schema

```json
{}
```

## Output Schema

```json
{}
```

## Validation Rules

1. ...
2. ...

## Security Rules

1. ...
2. ...

## Error Types

| errorType | Meaning |
|---|---|
| timeout | ... |
| auth_error | ... |
| upstream_5xx | ... |
```

---

## 22. 最关键的边界规则

实现过程中始终保持这几条边界：

1. **Skill 写知识，不执行真实动作。**
2. **Tool 执行真实动作，不让模型拼 curl。**
3. **服务事实源在注册表，不散落在 Skill。**
4. **Java 只负责桥接状态，不解析业务分支。**
5. **OpenHarness 每轮必须输出最小 JSON。**
6. **所有用户可见消息必须通过 `qiyu_send_message`。**
8. **ERP、七鱼、ERP 跟进必须幂等。**
9. **日志查询不能接受 raw DSL/SQL。**
10. **PaaS Agent 默认不能使用 Bash。**
