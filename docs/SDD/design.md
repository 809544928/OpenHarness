# OpenHarness PaaS 智能客服最小闭环改造设计

## 1. 背景与目标

PaaS 平台对外提供 OCR、TTS、ASR 等数十种接口服务。用户通过平台 A（第一版为七鱼客服平台）联系人工客服，常见问题集中在服务接入咨询、服务报错反馈和其他无关咨询。当前目标是在人工客服前增加一层智能客服预处理 Agent，由 Java 暴露平台 A 消息推送 HTTP 接口，并在鉴权、过滤和最小状态桥接后调用本地 OpenHarness 进程完成客服业务判断与工具调度。

本设计专门描述 OpenHarness 工程侧改造，不重复展开 Java webhook 细节。Java 与 OpenHarness 的职责边界以 `docs/SDD/agent-paas.md` 为准：Java 只负责接入、鉴权、去重、history/agentState 桥接、调用 `oh`、保存 `newState/terminal` 和返回 ACK；OpenHarness 负责意图理解、服务识别、追问、文档回复、demo probe、日志查询、ERP 升级、七鱼发消息以及最小结构化摘要输出。

本设计采用方案 B：**服务知识放 Skill，真实调用做通用 Tool**。

## 2. 核心结论：Skill 不直接执行真实 curl

不同服务的接入说明、参数含义、curl 示例模板、常见错误码和排障 runbook 可以写在 Skill 中；但真实 demo 调用、日志查询、ERP 发送、七鱼发消息和ERP 跟进必须通过 OpenHarness Tool 或 MCP 完成。

不建议让模型从 Skill 中复制 curl 并通过 Bash 执行，原因如下：

1. **安全边界不清晰**：Skill 是给模型看的文本，如果写入真实 token、header、内部域名或完整 curl，容易进入模型上下文、日志、调试输出或被 prompt injection 利用。
2. **权限不可审计**：通过 Bash 执行 curl 时，权限系统只看到一段 shell 字符串，无法按“调用 OCR probe”“查询日志”“发送 ERP 消息”“发送七鱼消息”做细粒度审计、限流、确认和告警。
3. **输入校验薄弱**：日志查询和 ERP 发送需要结构化参数、字段白名单、超时、重试和幂等控制，Skill 文本不能保证这些约束稳定执行。
4. **多服务扩展成本高**：数十个服务如果每个都写独立 curl skill，会重复鉴权、错误处理、超时和日志规范，难以统一治理。
5. **不利于 Java 侧稳定协议**：Java 只应解析 OpenHarness 输出的最小 JSON 摘要，而不是解析自然语言、curl stdout 和错误输出混合体。

因此分层原则如下：

| 层级 | 职责 | 示例 |
|---|---|---|
| Skill | 服务知识、流程规则、话术策略、接入说明、示例模板 | OCR 接入说明、TTS 常见错误码、服务报错处理流程 |
| 配置 | 服务事实源和执行参数 | 服务 ID、别名、手册 URL、probe 配置、日志 stream_name、ERP product/message |
| Tool/MCP | 真实副作用和外部系统调用 | `paas_probe_service`、`paas_query_logs`、`paas_send_erp_message`、`qiyu_send_message` |
| 最终摘要 | 返回 Java 的最小结构化结果 | `conversationId`、`action`、`toolResults`、`newState`、`terminal` |

## 3. OpenHarness 当前可复用扩展点

当前工程已有以下能力可复用：

1. CLI 入口支持 `oh` / `openharness`。
2. 非交互执行路径位于 `src/openharness/ui/app.py` 的 `run_print_mode()`，可用于 Java 通过本地进程单次调用。
3. 运行时构造位于 `src/openharness/ui/runtime.py` 的 `build_runtime()`，会加载插件、MCP、工具注册表和 Skill。
4. 工具抽象位于 `src/openharness/tools/base.py`，`BaseTool` 使用 Pydantic `input_model` 描述结构化入参，并返回统一 `ToolResult`。
5. 默认工具注册位于 `src/openharness/tools/__init__.py`，插件工具会在 `build_runtime()` 中注册到 `ToolRegistry`。
6. Skill 数据结构位于 `src/openharness/skills/types.py`，适合承载业务说明、服务知识、runbook 和示例。
7. 插件加载位于 `src/openharness/plugins/loader.py`，项目插件默认需要 `allow_project_plugins=true` 才会加载。
8. 权限模式当前只有 `default`、`plan`、`full_auto`，第一版不新增权限模式，优先通过工具白名单、专用启动参数和插件部署约束工具面。

## 4. 总体架构

```text
平台 A / 七鱼
  ↓
Java HTTP 服务
  - 鉴权
  - 过滤事件
  - JVM 内存态 history / agentState / terminal
  - 调用本地 oh
  - 保存 OpenHarness 输出摘要
  - 返回 ACK
  ↓
oh --print --output-format json --prompt-file /tmp/paas-input.json
  ↓
OpenHarness Runtime
  - 加载 PaaS 客服 Skill
  - 加载服务注册表配置
  - 暴露 PaaS 通用 Tool
  - 识别意图、服务和场景
  - 调用 Tool 完成真实外部动作
  - 返回最小 JSON 摘要
  ↓
外部系统
  - 七鱼发送消息
  - 服务 demo probe
  - 日志系统
  - ERP / 内部工单
```

第一版保持“Java 每轮调用本地 `oh` 进程”的单次执行模型，不引入常驻 bridge/daemon。每次调用都必须依赖 Java 传入的 `history` 和 `agentState` 恢复上下文。

## 5. 最小闭环业务流程

### 5.1 接入文档场景

用户询问某服务的接入事项时，OpenHarness 判断为 `access_docs`。

服务明确：

```text
用户：OCR 怎么接入？
↓
OpenHarness:
  1. 识别 scenario=access_docs。
  2. 通过 paas_resolve_service 识别 serviceId=ocr。
  3. 调用 paas_get_manual_url(serviceId=ocr)。
  4. 生成用户可见文案。
  5. 调用 qiyu_send_message 发送文档说明。
  6. 输出 terminal=true，newState.terminalReason=manual_sent。
```

服务不明确：

```text
用户：怎么接入？
↓
OpenHarness:
  1. 识别 scenario=access_docs。
  2. 无法解析唯一 serviceId。
  3. 生成追问：请问你要接入 OCR、TTS、ASR 中的哪一个服务？
  4. 调用 qiyu_send_message 发送追问。
  5. 输出 terminal=false，newState.waitingFor=service。
```

对于接入咨询，如果用户持续未明确服务，OpenHarness 应持续追问到上限；达到上限后按策略结束。建议同一意图最多追问 2 次。

### 5.2 服务报错场景

用户反馈错误时，OpenHarness 判断为 `service_error`。

服务不明确：

```text
用户：接口一直报错。
↓
OpenHarness:
  1. 识别 scenario=service_error。
  2. serviceId=null。
  3. 调用 qiyu_send_message 追问具体服务。
  4. 输出 terminal=false，newState.waitingFor=service。
```

服务明确且线上 probe 异常：

```text
用户：OCR 报 500。
↓
OpenHarness:
  1. 识别 scenario=service_error。
  2. 解析 serviceId=ocr。
  3. 调用 paas_probe_service(serviceId=ocr)。
  4. probe 返回不可用或异常。
  5. 调用 paas_send_erp_message，携带用户摘要和 probe 摘要。
  6. 不调用 qiyu_send_message；probe 异常分支仅提交 ERP 并静默结束。
  7. 输出 terminal=true，newState.terminalReason=erp_sent_after_probe_failure。
```

服务明确且线上 probe 正常但缺少 requestId/appKey：

```text
用户：OCR 报 401。
↓
OpenHarness:
  1. 调用 paas_probe_service(serviceId=ocr)。
  2. probe 正常。
  3. 判断缺少 appKey/requestId。
  4. 调用 qiyu_send_message 追问 appKey 和 requestId（如果存在）。
  5. 输出 terminal=false，newState.waitingFor=request_context。
```

收到 requestId 后：

```text
用户：appKey 是 xxx，requestId 是 yyy。
↓
OpenHarness:
  1. 从 history + agentState 判断正在等待 request_context。
  2. 提取 appKey/requestId。
  3. 调用 paas_query_logs(serviceId, appKey, requestId, timeRange)。
  4. 调用 paas_send_erp_message，携带日志摘要和用户上下文。
  5. 调用 qiyu_send_message 告知用户已提交客服人员处理。
  6. 输出 terminal=true，newState.terminalReason=erp_sent_after_log_query。
```

### 5.3 其他场景

```text
用户：你是谁？
↓
OpenHarness:
  1. 识别 scenario=other。
  2. 不调用 probe/log/ERP。
  3. 可按策略调用 qiyu_send_message 简短说明，或直接结束。
  4. 输出 terminal=true，newState.terminalReason=other_closed。
```

第一版建议其他场景直接结束流程；是否发送用户消息由 PaaS 客服 Skill 策略决定。

## 6. OpenHarness 输入输出协议

### 6.1 Java 传入 OpenHarness 的最小 JSON

```json
{
  "conversationId": "qiyu:6383959733",
  "platformSessionId": "6383959733",
  "platformUserId": "81275614-ff4c-490e-9517-0934f4fc9325@顺风车乘客",
  "staffId": "4126122",
  "message": "OCR 服务一直报 401，帮我看下",
  "history": [
    {
      "role": "user",
      "content": "OCR 服务怎么接入？"
    }
  ],
  "agentState": {
    "terminal": false
  }
}
```

OpenHarness 侧只依赖这些字段完成决策。服务注册表、凭据、日志系统地址、ERP 发送配置和七鱼发送凭据均从 OpenHarness 侧配置或环境变量读取，不能由用户消息或 Java 传入。

### 6.2 OpenHarness 输出给 Java 的最小 JSON

```json
{
  "conversationId": "qiyu:6383959733",
  "action": "erp_sent",
  "toolResults": [
    {
      "tool": "paas_probe_service",
      "success": true,
      "summary": "online probe succeeded"
    },
    {
      "tool": "paas_query_logs",
      "success": true,
      "summary": "found related error log entries"
    },
    {
      "tool": "paas_send_erp_message",
      "success": true,
      "summary": "ERP message sent"
    }
  ],
  "newState": {
    "scenario": "service_error",
    "serviceId": "ocr",
    "waitingFor": null,
    "terminal": true,
    "terminalReason": "erp_sent_after_log_query"
  },
  "terminal": true
}
```

Java 行为：

1. 校验 `conversationId` 等于当前调用会话。
2. 保存 `newState` 到 `ConversationContext.agentState`。
3. 保存 `terminal` 到 `ConversationContext.terminal`。
4. 可记录 `action` 和 `toolResults.summary` 到内部日志。
5. 不解析 `scenario`、`serviceId`、`waitingFor` 做业务分支。
6. 不解析 `replyToUser`，即使 OpenHarness 输出该旧字段也忽略。

## 7. 服务注册表设计

### 7.1 配置文件

建议新增：

- `config/paas-services.example.yaml`
- 生产环境使用 `PAAS_SERVICE_REGISTRY_PATH` 指定真实配置路径。

示例：

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

### 7.2 配置原则

1. 服务注册表是服务事实源，服务 ID、别名、文档 URL、probe 配置、日志 stream_name 和 ERP product/message 不应散落在多个 Skill 中。
2. 新增服务优先修改配置和服务知识 Skill，不新增真实执行 Tool。
3. 配置中不存真实 token、secret、cookie 或七鱼/ERP 凭据。
4. probe 请求模板可以引用模板 ID，但模板内鉴权头仍从环境变量或安全配置中心注入。
5. 日志配置只声明 `stream_name`，不允许配置任意可由模型拼接的 DSL。

## 8. OpenHarness 模块与文件设计

### 8.1 PaaS 核心模块

建议新增：

```text
src/openharness/paas/
  __init__.py
  models.py
  service_registry.py
  idempotency.py
  errors.py
```

职责：

- `models.py`：定义服务注册表、Agent 输入输出、工具结果摘要等 Pydantic 模型。
- `service_registry.py`：加载并校验 `paas-services.yaml`，提供按 ID/别名解析服务的 API。
- `idempotency.py`：生成 ERP、七鱼发送等发送类操作的幂等键。
- `errors.py`：定义 PaaS 工具错误分类，例如 `timeout`、`auth_error`、`upstream_5xx`、`invalid_service`。

### 8.2 插件封装

优先以插件形式封装企业客服能力，减少对 OpenHarness 核心的侵入：

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
    services/ocr/SKILL.md
    services/tts/SKILL.md
    services/asr/SKILL.md
  tools/
    paas_resolve_service_tool.py
    paas_get_manual_url_tool.py
    paas_probe_service_tool.py
    paas_query_logs_tool.py
    paas_send_erp_message_tool.py
    qiyu_send_message_tool.py
    paas_finish_decision_tool.py
```

`plugin.json` 示例：

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

注意：项目插件默认不启用，部署时必须显式配置 `allow_project_plugins=true`，或将插件部署到用户插件目录。

### 8.3 是否放入内置 tools

最小闭环可以优先放在插件中。如果企业部署要求不依赖项目插件，也可以把稳定通用的 PaaS Tool 放入 `src/openharness/tools/` 并在 `create_default_tool_registry()` 注册；但这会把业务系统耦合进 OpenHarness 核心，第一版不推荐。

## 9. Tool 设计

所有 Tool 都继承 `BaseTool`，使用 Pydantic `input_model` 定义结构化入参，返回 `ToolResult`。外部响应应限长并分类，不能把 token/header/raw payload 原样写入 `ToolResult.output`。

### 9.1 `paas_resolve_service`

职责：将用户文本、候选服务名或别名解析为服务 ID。

入参：

```json
{
  "message": "OCR 服务一直报 401",
  "candidate": "OCR"
}
```

出参摘要：

```json
{
  "serviceId": "ocr",
  "confidence": 0.98,
  "ambiguous": false,
  "candidates": [
    {"serviceId": "ocr", "displayName": "OCR 文字识别"}
  ]
}
```

规则：

1. 只返回注册表中存在的 `serviceId`。
2. 多义或低置信度时返回 `ambiguous=true`，由 Agent 追问用户。
3. 不让模型自由创造服务 ID。

### 9.2 `paas_get_manual_url`

职责：按 `serviceId` 返回接入文档 URL。

入参：

```json
{"serviceId": "ocr"}
```

出参摘要：

```json
{
  "serviceId": "ocr",
  "displayName": "OCR 文字识别",
  "manualUrl": "https://docs.example.com/ocr/quickstart"
}
```

规则：

1. URL 来自服务注册表。
2. 找不到服务时返回工具错误，不允许模型编造 URL。

### 9.3 `paas_probe_service`

职责：执行指定服务的在线 demo probe，判断线上服务是否可用。

入参：

```json
{
  "serviceId": "ocr",
}
```

出参摘要：

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

规则：

1. demo endpoint、method、timeout 和模板引用来自服务注册表。
2. 凭据从环境变量、配置文件或安全配置中心读取，不能来自用户输入。
3. 每次 probe 必须设置超时，建议默认 3 秒。
4. 响应体采样必须限长。
5. 对 2xx、4xx、5xx、timeout、network error 做明确分类。
6. 对客服消息触发的 probe 做限流和熔断，避免大量用户消息冲击线上服务。

### 9.4 `paas_query_logs`

职责：按结构化字段查询日志系统并返回摘要。

入参：

```json
{
  "serviceId": "ocr",
  "appKey": "app_****1234",
  "requestId": "req-abc-123",
  "timeRange": {
    "start": "2026-06-23T10:00:00Z",
    "end": "2026-06-23T11:00:00Z"
  }
}
```

出参摘要：

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

规则：

1. 不接受 `rawQuery`、`dsl`、`sql` 等自由查询参数。
2. 只允许按 `serviceId + requestId + appKey + timeRange` 查询。
3. 日志流名称来自服务注册表的 `log.stream_name`。
5. 返回条数和响应体长度必须有限制。
6. 日志系统超时或失败时返回错误摘要，并允许 Agent 发 ERP 告知客服“日志查询失败”。

### 9.5 `paas_send_erp_message`

职责：将用户反馈、probe 结果和日志摘要发送给 ERP 或内部工单系统。

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
  }
}
```

出参摘要：

```json
{
  "erpMessageId": "erp-10086",
  "ticketUrl": "https://erp.example.com/tickets/erp-10086",
  "sentAt": "2026-06-23T10:20:00Z"
}
```

规则：

1. Java webhook 层负责按平台事件去重；Tool 不暴露去重字段。
2. ERP `product` 和 `message` 模板来自服务注册表，Tool 可结合 probe/log 摘要生成最终发送内容。
3. 发送内容不携带原始用户 payload、真实 token 或完整 appKey。
4. ERP 失败时返回明确错误类型，Agent 可选择通知用户“已记录，将由客服跟进”或ERP 跟进。

### 9.6 `qiyu_send_message`

职责：向七鱼会话发送用户可见文本。

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

规则：

1. 七鱼 API 鉴权由 Tool 自己处理。
2. Tool 自己负责发送幂等、重试和错误分类。
3. 不在 ToolResult 中返回七鱼 token、请求签名或完整响应体。
4. `content` 来自 OpenHarness 的话术生成策略，不由 Java 生成。


### 9.7 `paas_finish_decision`

职责：作为 OpenHarness 单次执行的最终结构化出口，保证 Java 能解析最小 JSON。

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

规则：

1. 必须校验 `conversationId` 存在。
2. 必须校验 `terminal` 与 `newState.terminal` 一致。
3. 服务报错场景中，如果服务已明确但没有 probe 结果，不允许直接发 ERP 或结束。
4. 非终态必须设置 `waitingFor`；服务不明确时继续追问服务。
5. 这是 Java 解析的最终结果来源。

## 10. Skill 设计

### 10.1 总入口 Skill：`paas_customer_service_router`

职责：定义 Agent 身份、总流程和强约束。

必须说明：

1. 你是 PaaS 智能客服预处理 Agent。
2. 你负责判断用户问题是否明确、是否需要追问、属于哪种场景。
3. 你必须优先使用服务注册表和 Tool，不得编造服务、URL、日志或 ERP 结果。
4. 真实外部调用必须通过 Tool，不能复制 Skill 中 curl 通过 Bash 执行。
5. 每轮最终必须通过 `paas_finish_decision` 输出结构化摘要。
6. Java 不会发送用户消息；如需给用户发消息，必须调用 `qiyu_send_message`。
7. 如果服务不明确，必须追问服务名。
8. 服务报错且服务明确后，必须先调用 `paas_probe_service`。
9. probe 异常时发送 ERP 并结束。
10. probe 正常且缺少 requestId/appKey 时追问用户。
11. 收到 requestId 后查询日志，再发 ERP 并结束。
12. 其他场景直接结束。

### 10.2 意图与服务识别 Skill

- `paas_intent_classifier`：判断 `access_docs`、`service_error`、`other`。
- `paas_service_resolver`：说明如何从用户文本中提取候选服务词，并调用 `paas_resolve_service`。

规则：

1. 服务识别结论必须来自 `paas_resolve_service`。
2. 如果候选服务多义，追问用户确认。
3. 不允许模型把“接口”“平台”“服务”等泛称当作具体服务。

### 10.3 接入文档 Skill

`paas_access_docs_flow` 定义：

1. 服务明确时调用 `paas_get_manual_url`。
2. 生成简短文案，包含服务展示名和手册 URL。
3. 调用 `qiyu_send_message`。
4. 输出 `terminal=true`。
5. 服务不明确时追问，不返回通用文档集合。

### 10.4 服务报错 Skill

`paas_service_error_flow` 定义：

1. 服务不明确先追问。
2. 服务明确后先 probe。
3. probe 异常直接 ERP，不再向用户索要 appKey/requestId。
4. probe 正常才询问 appKey/requestId。
5. 收到 requestId 后查日志。
6. 无 requestId 但用户无法提供时，可以发 ERP，说明“用户未提供 requestId”。
7. ERP 后给用户发送已提交客服人员的话术。
8. 流程结束时 `terminal=true`。

### 10.5 服务知识 Skill

每个服务可以有一个知识 Skill，例如：

```text
skills/services/ocr/SKILL.md
skills/services/tts/SKILL.md
skills/services/asr/SKILL.md
```

内容包括：

1. 服务简介。
2. 服务别名。
3. 接入文档说明。
4. 常见错误码和排障建议。
5. demo probe 的业务含义和样例输入说明。
6. curl 示例模板，但必须标注“仅示例，不由 Agent 直接执行”。

服务 Skill 不应包含：

1. 真实 token、secret、cookie。
2. 生产内部域名路径。
3. 需要由模型直接复制执行的 curl。
4. 日志系统原始 DSL 或 SQL。

## 11. CLI 与运行方式设计

Java 建议调用：

```bash
oh --print --output-format json --prompt-file /tmp/paas-input.json
```

OpenHarness 侧需要满足：

1. 支持 `--prompt-file` 或等价文件输入方式，避免命令行长度和 shell 转义问题。
2. 支持加载 PaaS 插件和服务注册表。
3. 支持输出最小 JSON 摘要。
4. `--output-format json` 如果仍返回 `{"type":"result","text":"..."}`，则 `text` 必须是可解析的最小 JSON。
5. 更优方案是增加 PaaS 专用输出包装，使 `paas_finish_decision` 的结果直接作为顶层 JSON 输出。

推荐启动上下文：

```bash
PAAS_SERVICE_REGISTRY_PATH=/etc/openharness/paas-services.yaml \
QIYU_APP_KEY=*** \
QIYU_APP_SECRET=*** \
ERP_API_TOKEN=*** \
LOG_API_TOKEN=*** \
oh --print --output-format json --prompt-file /tmp/paas-input.json
```

## 12. 权限与工具面控制

客服预处理 Agent 不需要通用 shell、文件写入、子代理、定时任务等能力。第一版应尽量通过专用运行配置只暴露以下工具：

允许：

- `paas_resolve_service`
- `paas_get_manual_url`
- `paas_probe_service`
- `paas_query_logs`
- `paas_send_erp_message`
- `qiyu_send_message`
- `paas_send_erp_message`
- `paas_finish_decision`
- 必要的 Skill 加载能力

禁止或默认不暴露：

- `bash`
- `file_write`
- `file_edit`
- `notebook_edit`
- `cron`
- `agent`
- `team`
- 任意 MCP 工具自动暴露

如果当前 OpenHarness 工具注册表尚不支持按场景白名单过滤，最小闭环可先通过以下方式实现：

1. PaaS 专用插件只注册 PaaS 工具。
2. PaaS 专用启动入口或配置在构造 API tool schema 时过滤工具名。
3. 权限策略禁止 Bash 和文件修改类工具。
4. 后续再新增正式的 `tool_allowlist` 配置。

## 13. 状态模型设计

OpenHarness 返回的 `newState` 建议包含：

```json
{
  "scenario": "service_error",
  "serviceId": "ocr",
  "waitingFor": "request_context",
  "clarificationCount": 1,
  "probeResult": {
    "available": true,
    "errorType": null
  },
  "logResult": null,
  "erpSent": false,
  "erpMessageId": null,
  "terminal": false,
  "terminalReason": null
}
```

字段说明：

| 字段 | 说明 |
|---|---|
| `scenario` | OpenHarness 内部业务场景，Java 原样保存但不解析。 |
| `serviceId` | 注册表服务 ID，Java 原样保存但不解析。 |
| `waitingFor` | 当前等待用户补充的信息，例如 `service`、`request_context`。 |
| `clarificationCount` | 当前意图追问次数，用于限制无限追问。 |
| `probeResult` | probe 摘要。 |
| `logResult` | 日志查询摘要。 |
| `erpSent` | 是否已发送 ERP。 |
| `erpMessageId` | ERP 返回 ID。 |
| `terminal` | 流程是否结束。 |
| `terminalReason` | 结束原因，例如 `manual_sent`、`erp_sent_after_probe_failure`、`other_closed`。 |

## 14. 错误处理设计

### 14.1 Tool 失败

| Tool | 失败处理 |
|---|---|
| `paas_resolve_service` | 追问用户或结束，不编造服务。 |
| `paas_get_manual_url` | 告知用户暂未找到文档，可结束。 |
| `paas_probe_service` | 如果 probe 工具本身超时或异常，发送 ERP，说明 probe 失败。 |
| `paas_query_logs` | 发送 ERP，说明日志查询失败或未查到。 |
| `paas_send_erp_message` | 尝试ERP 跟进或告警；输出错误摘要，避免重复发送。 |
| `qiyu_send_message` | 输出错误摘要给 Java，Java 仍只 ACK，不补发兜底消息。 |

### 14.2 OpenHarness 进程失败

OpenHarness 超时、非法 JSON 或进程异常由 Java 处理。Java 只记录内部日志并 ACK，不发送兜底消息。OpenHarness 设计侧应尽量通过 `paas_finish_decision` 降低非法 JSON 概率。

## 15. 安全要求

1. Skill 中不得写真实密钥、token、cookie、生产签名密钥。
2. Skill 中的 curl 只能作为说明模板，不能作为执行路径。
3. 所有真实外部调用必须通过 Tool/MCP。
4. Tool 凭据必须从环境变量、配置文件或安全配置中心读取。
5. ToolResult 不得输出真实 token/header/cookie。
6. 日志查询不得接受任意 raw DSL、SQL 或 Lucene 查询。
7. ERP 发送、七鱼发送和ERP 跟进必须具备幂等保护。
8. probe 必须有超时、限流、熔断和响应体长度限制。
10. Java 不传 `appSecret`、`checksum`、`rawPayload`、七鱼内部 `user_id` 给 OpenHarness。
11. OpenHarness 不依赖用户提供的服务注册表或执行端点。
12. 禁止默认暴露 Bash 给客服 Agent。

## 16. 测试与验收计划

### 16.1 单元测试

建议新增测试：

```bash
pytest tests/test_paas/test_service_registry.py -v
pytest tests/test_paas/test_paas_resolve_service_tool.py -v
pytest tests/test_paas/test_paas_get_manual_url_tool.py -v
pytest tests/test_paas/test_paas_probe_service_tool.py -v
pytest tests/test_paas/test_paas_query_logs_tool.py -v
pytest tests/test_paas/test_paas_send_erp_message_tool.py -v
pytest tests/test_paas/test_qiyu_send_message_tool.py -v
pytest tests/test_paas/test_paas_finish_decision_tool.py -v
```

覆盖：

1. 服务别名解析。
2. 服务不明确和多义匹配。
3. 手册 URL 查询。
4. probe 200/4xx/5xx/timeout。
5. 日志查询字段白名单。
7. ERP 幂等键重复调用。
8. 七鱼发送幂等和错误处理。
9. 最终 JSON schema 校验。

### 16.2 CLI 集成测试

建议新增：

```bash
pytest tests/test_paas/test_paas_cli_integration.py -v
```

场景：

1. 输入“怎么接入？”：OpenHarness 追问具体服务，`terminal=false`。
2. 输入“OCR 怎么接入？”：调用 `paas_get_manual_url` 和 `qiyu_send_message`，`terminal=true`。
3. 输入“接口报错”：追问服务，`waitingFor=service`。
4. 输入“OCR 报 500”，probe mock 异常：调用 ERP，`terminal=true`。
5. 输入“OCR 报 401”，probe mock 正常且缺 requestId：追问 requestId/appKey，`terminal=false`。
6. 上轮 `waitingFor=request_context`，本轮提供 requestId：查日志、发 ERP、结束。
7. 输入“你是谁？”：直接结束，不调用 probe/log/ERP。

### 16.3 手工烟测

输入文件：

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

执行：

```bash
oh --print --output-format json --prompt-file /tmp/paas-input.json
```

期望：

```json
{
  "conversationId": "qiyu:demo-1",
  "action": "manual_sent",
  "newState": {
    "scenario": "access_docs",
    "serviceId": "ocr",
    "terminal": true
  },
  "terminal": true
}
```

## 17. 最小实施阶段

### Phase 1：协议和最终出口

1. 定义 OpenHarness 输入 JSON 模型。
2. 定义 OpenHarness 输出 JSON 模型。
3. 实现 `paas_finish_decision`。
4. 确认 `oh --print --output-format json --prompt-file` 能稳定返回 Java 可解析 JSON。

### Phase 2：服务注册表和文档场景

1. 实现服务注册表加载。
2. 实现 `paas_resolve_service`。
3. 实现 `paas_get_manual_url`。
4. 编写接入文档 Skill。
5. 打通“服务明确返回文档”和“服务不明确追问”。

### Phase 3：七鱼消息 Tool

1. 实现 `qiyu_send_message`。
2. 实现发送幂等和错误处理。
3. 将追问和文档回复改为通过 Tool 发送。

### Phase 4：服务报错场景

1. 实现 `paas_probe_service`。
2. 实现 `paas_query_logs`。
3. 实现 `paas_send_erp_message`。
4. 编写服务报错 Skill。
5. 打通 probe 异常 ERP、probe 正常追问 requestId、查日志后 ERP。

### Phase 5：治理和白名单

1. 限制 PaaS Agent 可用工具集合。
2. 禁止 Bash 和文件修改类工具。
3. 增加限流、熔断、超时配置。
4. 增加完整集成测试。

## 18. 后续演进

第一版不做：

1. 常驻 bridge/daemon。
2. Redis/数据库状态持久化。
3. 多平台统一适配层。
4. 每个服务独立真实执行 Tool。
5. 模型自由执行 Bash/curl。
6. 复杂人工客服排班路由。
7. 任意日志 DSL 查询。

后续可演进：

1. 如果 `oh` 冷启动不可接受，再引入 bridge/daemon。
2. 如果企业已有 MCP 基础设施，可把日志、ERP、七鱼能力迁移到 MCP server。
3. 如果服务数量继续增长，引入服务注册表管理后台。
4. 如果需要生产级审计，引入 OpenHarness 调用摘要对象和持久化审计表。
5. 如果需要跨节点一致性，由 Java 侧引入 Redis/DB 保存 conversation 和 dedup。
