# PaaS Customer Service OpenHarness 插件 SDD

## 1. 文档定位

本文档描述 OpenHarness 插件 `.openharness/plugins/paas-customer-service` 的当前技术设计。该插件是 PaaS 智能客服预处理的业务核心，负责识别用户意图、解析服务、追问缺失信息、获取接入文档、探测在线 demo、查询 o2log、提交 ERP/POPo 跟进，以及通过七鱼发送用户可见消息。

Java 侧不是本文档主体。Java 侧只作为 webhook 入口和 OpenHarness 调用桥：接收七鱼事件、完成平台协议处理、构造当前轮输入、调用本地 `oh`、保存插件返回的 `newState`，并在下一轮作为 `agentState` 原样传回。客服业务判断、用户话术、probe、日志查询、ERP/POPo 升级均由 OpenHarness 插件完成。

## 2. 插件目录

```text
.openharness/plugins/paas-customer-service/
  plugin.json
  config/
    paas-services.example.yaml
  skills/
    paas_customer_service_router/SKILL.md
    paas_intent_classifier/SKILL.md
    paas_service_resolver/SKILL.md
    paas_access_docs_flow/SKILL.md
    paas_service_error_flow/SKILL.md
    paas_clarification_policy/SKILL.md
    paas_response_composer/SKILL.md
    services/ocr/SKILL.md
    services/tts/SKILL.md
    services/asr/SKILL.md
  tools/
    _config.py
    _errors.py
    _http.py
    _models.py
    _service_registry.py
    _turn_messages.py
    _youdao_auth.py
    _youdao_probe.py
    paas_resolve_service_tool.py
    paas_get_manual_url_tool.py
    paas_probe_service_tool.py
    paas_query_logs_tool.py
    paas_send_erp_message_tool.py
    qiyu_send_message_tool.py
    paas_finish_decision_tool.py
```

`plugin.json` 声明插件名为 `paas-customer-service`，版本为 `1.0.0`，默认启用，并分别从 `skills` 和 `tools` 目录加载技能和工具。

## 3. 总体职责边界

### 3.1 OpenHarness 插件负责

1. 将当前客服消息分类为 `access_docs`、`service_error` 或 `other`。
2. 通过服务注册表解析用户提到的 PaaS 服务，禁止模型自行发明 `serviceId`。
3. 在服务不明确或请求上下文缺失时，通过七鱼追问用户。
4. 在接入文档场景中获取注册表里的文档 URL，并通过七鱼发送给用户。
5. 在服务报错场景中先对标准 demo endpoint 做 probe。
6. 在 probe 异常时提交 ERP/POPo 跟进，并对用户静默结束该分支。
7. 在 probe 正常但缺少 `requestId` 或 `appKey` 时追问请求上下文。
8. 在拿到请求上下文后查询 o2log，提交带 `logResult` 的 ERP/POPo 消息。
9. 每轮都通过 `paas_finish_decision` 返回 Java 可解析的结构化结果。
10. 控制用户可见文本的安全边界，避免泄露日志、token、签名、headers、appSecret、内部 URL 或原始异常。

### 3.2 Java 侧只负责

1. 接收七鱼 webhook 和 URL 验证请求。
2. 过滤非文本、无效状态、重复消息等平台事件。
3. 将七鱼会话 ID 映射为 `conversationId`，例如 `qiyu:6383959733`。
4. 将当前文本、最近历史、平台标识和上一轮 `agentState` 传给 OpenHarness。
5. 调用本地 `oh` 执行插件流程。
6. 保存 OpenHarness 输出的 `newState` 和 `terminal`。
7. 下一轮把保存的 `newState` 作为 `agentState` 传回。
8. 返回七鱼 webhook ACK。

Java 不解析 `newState` 内部业务字段做客服分支，不生成用户可见话术，不调用 probe、日志、ERP/POPo，也不发送业务兜底消息。

## 4. Java 输入与插件输出契约

### 4.1 输入 JSON

每轮 Java 给 OpenHarness 的输入是一个当前轮上下文对象：

```json
{
  "conversationId": "qiyu:6383959733",
  "platformSessionId": "6383959733",
  "platformUserId": "user-1",
  "staffId": "staff-1",
  "message": "OCR 怎么接入？",
  "history": [
    {"role": "user", "content": "OCR 怎么接入？"}
  ],
  "agentState": {"terminal": false}
}
```

字段语义：

| 字段 | 必填 | 说明 |
|---|---:|---|
| `conversationId` | 是 | 稳定会话 ID，通常由平台前缀和平台会话 ID 组成。 |
| `platformSessionId` | 是 | 七鱼原始会话 ID，供 `qiyu_send_message` 定位会话。 |
| `platformUserId` | 否 | 平台用户标识，供七鱼发送消息和 ERP/POPo 上下文使用。 |
| `staffId` | 否 | 当前坐席或机器人坐席标识。 |
| `message` | 是 | 当前访客文本。 |
| `history` | 否 | 最近对话历史，元素建议包含 `role` 和 `content`。 |
| `agentState` | 否 | 上一轮插件返回的 `newState`，由 Java 原样传回。 |

### 4.2 输出 JSON

每轮插件必须调用 `paas_finish_decision` 产生结构化输出：

```json
{
  "conversationId": "qiyu:6383959733",
  "action": "manual_sent",
  "toolResults": [
    {"tool": "paas_resolve_service", "success": true, "summary": "service resolved"},
    {"tool": "paas_get_manual_url", "success": true, "summary": "manual URL resolved"},
    {"tool": "qiyu_send_message", "success": true, "summary": "manual message sent"}
  ],
  "assistantMessages": [
    {"role": "assistant", "content": "这是 OCR 文字识别 的接入文档：https://ai.youdao.com/DOCSIRMA/html/ocr/api/tyocr/"}
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

`assistantMessages` 由成功的 `qiyu_send_message` 调用记录并在 `paas_finish_decision` 中自动收集。probe 失败后的 ERP/POPo 分支故意不调用 `qiyu_send_message`，因此该分支可以没有用户可见消息。

## 5. 技能编排

### 5.1 `paas_customer_service_router`

顶层路由技能。它定义全局硬规则、Java 输入字段、状态字段、三类场景和完整的每轮执行顺序。所有路径都必须以 `paas_finish_decision` 结束。

关键规则：

1. 外部动作必须通过注册工具完成。
2. 禁止运行 curl、Bash 或技能中的复制示例。
3. 禁止发明服务 ID、文档 URL、probe 结果、日志结果、ERP/POPo 结果或七鱼发送结果。
4. 需要用户可见消息时必须通过 `qiyu_send_message` 发送；probe 失败 ERP/POPo 分支故意不发七鱼消息。
5. Java 只保存最终结构化结果，不发送业务兜底消息。
6. `paas_query_logs` 的输出在 request-context 分支中只用于 ERP/POPo，不发送给用户。
7. 只有 `logResult.hits` 表示匹配到的用户请求日志。

### 5.2 `paas_intent_classifier`

意图分类技能。没有待处理 `agentState.waitingFor` 时，先把用户消息分类为：

| 场景 | 含义 |
|---|---|
| `access_docs` | 用户询问接入、调用、配置、认证、测试、示例或文档。 |
| `service_error` | 用户反馈错误、失败、超时、状态码、认证问题、异常响应或服务行为异常。 |
| `other` | 非 PaaS 业务、闲聊、身份问题或当前插件不支持的问题。 |

如果文本含有错误症状，优先归为 `service_error`；如果询问“怎么接入”“怎么调用”“文档在哪”“如何配置”，优先归为 `access_docs`。

### 5.3 `paas_service_resolver`

服务解析技能。服务身份只能来自 `paas_resolve_service` 工具和服务注册表。模型可以提取候选词，但不能直接决定最终 `serviceId`。

解析规则：

1. 从当前消息和相关历史中提取服务候选词。
2. 忽略“接口”“服务”“平台”“API”“报错”“文档”等泛词，除非它们和具体别名一起出现。
3. 调用 `paas_resolve_service`。
4. 仅当工具返回唯一服务且 `ambiguous=false` 时继续。
5. 多候选、无候选、低置信或 `ambiguous=true` 时通过七鱼追问服务。

### 5.4 `paas_access_docs_flow`

接入文档流程。服务明确后调用 `paas_get_manual_url`，再通过 `qiyu_send_message` 发送短文档说明，并以 `terminal=true` 结束。

服务不明确时，发送服务澄清问题并保存：

```json
{
  "scenario": "access_docs",
  "serviceId": null,
  "waitingFor": "service",
  "terminal": false,
  "terminalReason": "waiting_for_service"
}
```

服务明确时，完成状态为：

```json
{
  "scenario": "access_docs",
  "serviceId": "ocr",
  "waitingFor": null,
  "terminal": true,
  "terminalReason": "manual_sent"
}
```

### 5.5 `paas_service_error_flow`

服务报错流程。服务明确后必须先 probe，再决定后续动作。

#### 服务不明确

通过七鱼询问具体服务，保存 `waitingFor=service`，不发送 ERP/POPo。

#### 服务明确且 probe 失败

调用 `paas_probe_service` 后，如果 `available=false`，或出现超时、网络错误、HTTP 5xx、认证错误、无效响应等异常，调用 `paas_send_erp_message`，不调用 `qiyu_send_message`，并以 `terminal=true` 静默结束。

典型状态：

```json
{
  "scenario": "service_error",
  "serviceId": "tts",
  "waitingFor": null,
  "probeResult": {"available": false, "errorType": "auth_error"},
  "erpSent": true,
  "terminal": true,
  "terminalReason": "erp_sent_after_probe_failure"
}
```

#### 服务明确且 probe 正常，但缺少请求上下文

如果 probe 正常，但当前轮缺少 `requestId` 或 `appKey`，通过七鱼询问请求上下文，保存 `waitingFor=request_context`。

用户提示中允许请求：`requestId`、`appKey`、可选 `time`。`time` 如果提供，要求使用 `2026年7月2日 10:30` 格式。

#### 等待请求上下文时用户补充信息

当上一轮 `agentState.waitingFor=request_context` 且已有 `serviceId` 时，从当前消息和历史中提取 `requestId`、`appKey`、可选 `time`。只要有 `requestId` 或 `appKey`，就调用 `paas_query_logs`，再用 `paas_send_erp_message` 提交带 `logResult` 的 ERP/POPo 消息。该分支不调用 `qiyu_send_message`，不向用户输出日志诊断。

典型状态：

```json
{
  "scenario": "service_error",
  "serviceId": "ocr",
  "waitingFor": null,
  "logResult": {
    "serviceId": "ocr",
    "streamName": "aicloud_ocr",
    "queryInfo": "req-abc-123",
    "queryInfoSource": "requestId",
    "hits": []
  },
  "erpSent": true,
  "terminal": true,
  "terminalReason": "erp_sent_after_log_query"
}
```

### 5.6 `paas_clarification_policy`

澄清策略技能。插件只在缺少必要信息时追问：

| `waitingFor` | 含义 | 下一轮期望 |
|---|---|---|
| `service` | 服务身份不明确。 | OCR、TTS、ASR 或注册表中的其他别名。 |
| `request_context` | 服务明确且 probe 正常，但缺少日志查询键。 | `requestId`、`appKey`、可选 `time`。 |

澄清文本必须通过 `qiyu_send_message` 发送。插件不得要求用户提供 appSecret、token、cookie、签名、私钥、完整 headers 或完整请求 payload。

### 5.7 `paas_response_composer`

响应撰写技能。所有用户可见消息都应简短、中文、行动导向，并且不能暴露工具名、内部 URL、日志流、环境变量、原始工具输出、token、headers、签名、cookie、appSecret、私钥或完整请求 payload。

probe 失败的 ERP/POPo 分支不撰写也不发送用户通知。

## 6. 工具设计

### 6.1 `paas_resolve_service`

输入：

```json
{
  "message": "OCR 服务一直报 401",
  "candidate": "OCR"
}
```

行为：加载服务注册表，用 `service.id`、`displayName` 和 `aliases` 在候选词与消息中做包含匹配。唯一匹配时返回 `serviceId`、`confidence=0.98`、`ambiguous=false` 和候选列表；多个匹配时返回 `ambiguous=true`；无匹配时返回全部服务候选供澄清使用。

该工具是只读工具。

### 6.2 `paas_get_manual_url`

输入：

```json
{"serviceId": "ocr"}
```

行为：从注册表读取服务的 `manualUrl`、`displayName` 和 `serviceId`。未知服务返回 `unknown_service` 错误。该工具是只读工具。

### 6.3 `paas_probe_service`

输入：

```json
{"serviceId": "tts"}
```

行为：读取注册表中的 probe 配置。若 probe URL 是 mock URL，直接返回可用的最小 probe 结果。真实请求会读取有道凭证，按服务模板构造 form-urlencoded 探活请求，并通过安全 HTTP 封装发送。

支持的模板：

| 模板 | 服务 | 探活特点 |
|---|---|---|
| `ocr-default` | OCR | 使用内置 demo PNG base64，期望 JSON 成功响应。 |
| `asr-default` | ASR | 使用内置静音 WAV base64，期望 JSON 成功响应。 |
| `tts-default` | TTS | 使用固定文本，成功响应通常是音频。 |

返回最小诊断字段：

```json
{
  "serviceId": "tts",
  "available": true,
  "statusCode": 200,
  "latencyMs": 98,
  "errorType": "ok",
  "responseKind": "audio",
  "apiErrorCode": null
}
```

probe 结果只用于内部判断和 ERP/POPo 摘要，不直接发送给用户。

### 6.4 `paas_query_logs`

输入：

```json
{
  "serviceId": "ocr",
  "requestId": "req-abc-123",
  "appKey": null,
  "time": "2026年7月2日 10:30"
}
```

`requestId` 和 `appKey` 至少需要一个。工具按优先级使用 `requestId`，否则使用 `appKey`。如果 `time` 能按 `yyyy年M月d日 HH:mm` 解析，则查询该时间前后 30 分钟；否则查询最近 120 分钟并标记 `timeFallback=true`。

输出包含：

| 字段 | 说明 |
|---|---|
| `serviceId` | 服务 ID。 |
| `streamName` | 注册表中的 o2log 流名。 |
| `queryInfo` | 实际查询键。 |
| `queryInfoSource` | `requestId` 或 `appKey`。 |
| `time` | 用户提供的时间文本。 |
| `timeFallback` | 是否使用默认最近 120 分钟。 |
| `startTime` / `endTime` | o2log 查询窗口时间戳。 |
| `mock` | 是否命中 mock endpoint。 |
| `hits` | 唯一表示匹配用户请求日志的列表。 |
| `queryError` | 可选，表示日志平台查询自身错误。 |

`hits=[]` 只表示未找到匹配日志，不代表用户 API 调用认证失败、签名错误、服务异常或 appKey 无效。`queryError` 只表示 o2log 查询错误，不表示用户的 PaaS API 错误。

### 6.5 `paas_send_erp_message`

输入：

```json
{
  "serviceId": "ocr",
  "userSummary": "用户反馈 OCR 服务 401",
  "probeSummary": "probe unavailable: serviceId=ocr, errorType=auth_error",
  "logResult": {"hits": []},
  "platformContext": {
    "conversationId": "qiyu:6383959733",
    "platformSessionId": "6383959733",
    "platformUserId": "user-1"
  }
}
```

行为：从注册表读取 ERP 产品和处理说明，构造 POPo/ERP 消息，并通过 JSON HTTP 请求发送。消息包含产品、处理说明、用户摘要、可选 probe 摘要、可选日志结果、会话和平台上下文。`logResult` 会被 JSON 压缩并限制在 4000 字符内，超出时截断。

默认 POPo endpoint 写在工具内，也可通过 `PAAS_POPO_ENDPOINT` 或 `PAAS_ERP_ENDPOINT` 覆盖。

### 6.6 `qiyu_send_message`

输入：

```json
{
  "conversationId": "qiyu:6383959733",
  "platformSessionId": "6383959733",
  "platformUserId": "user-1",
  "staffId": "staff-1",
  "messageType": "TEXT",
  "content": "请问你咨询的是哪个服务？例如 OCR、TTS 或 ASR。"
}
```

行为：向七鱼发送用户可见文本。默认 endpoint 为 `http://localhost:8686/http/ai-customer-service/qiyu-sendMsg`，可通过 `QIYU_SEND_MESSAGE_ENDPOINT` 覆盖；默认 admin token 可通过 `ADMIN_TOKEN` 覆盖。设置 `QIYU_SEND_MESSAGE_MOCK=true` 时不发真实 HTTP，只记录 assistant message。

成功发送后，工具会把消息记录到 turn message 缓存，供 `paas_finish_decision` 自动写入 `assistantMessages`。

### 6.7 `paas_finish_decision`

输入包括 `conversationId`、`action`、`toolResults`、可选 `assistantMessages`、`newState` 和 `terminal`。

校验规则：

1. `conversationId` 不能为空。
2. 顶层 `terminal` 必须等于 `newState.terminal`。
3. `terminal=false` 时必须设置 `newState.waitingFor`。
4. `service_error` 场景中，如果有 `serviceId` 且 `erpSent=true`，必须带 `probeResult`。

该工具是每轮的唯一结构化出口。

## 7. 服务注册表

默认注册表路径为：

```text
.openharness/plugins/paas-customer-service/config/paas-services.example.yaml
```

可通过环境变量覆盖：

```text
PAAS_SERVICE_REGISTRY_PATH=/absolute/path/to/paas-services.yaml
```

注册表结构：

```yaml
services:
  - id: ocr
    displayName: OCR 文字识别
    aliases:
      - ocr
      - OCR
      - 文字识别
    manualUrl: "https://ai.youdao.com/DOCSIRMA/html/ocr/api/tyocr/"
    probe:
      type: http
      method: POST
      url: "https://openapi.youdao.com/ocrapi"
      timeoutMs: 10000
      requestTemplateRef: "ocr-default"
    log:
      stream_name: "aicloud_ocr"
    erp:
      product: "ocr"
      message: "用户反馈 OCR 服务异常，请客服结合 probe 和日志摘要跟进。"
```

当前示例注册了 OCR、TTS 和 ASR。每个服务必须包含非空 `aliases`，并提供文档 URL、probe 配置、o2log stream 和 ERP/POPo 元数据。

## 8. 运行时状态模型

`newState` 是跨轮状态的唯一来源。Java 必须原样保存，并在下一轮作为 `agentState` 传回。

| 字段 | 说明 |
|---|---|
| `scenario` | `access_docs`、`service_error` 或 `other`。 |
| `serviceId` | 注册表服务 ID；未解析时为 `null`。 |
| `waitingFor` | `service`、`request_context` 或 `null`。 |
| `clarificationCount` | 当前场景已追问次数。 |
| `probeResult` | 运行过 probe 时的脱敏诊断摘要。 |
| `logResult` | 日志查询结果；只有 `hits` 是匹配用户请求日志。 |
| `erpSent` | 是否成功提交 ERP/POPo。 |
| `erpMessageId` | ERP/POPo 消息 ID；没有时为 `null`。 |
| `terminal` | 当前预处理场景是否结束。 |
| `terminalReason` | 稳定结束原因，例如 `manual_sent`、`waiting_for_service`、`waiting_for_request_context`、`erp_sent_after_probe_failure`、`erp_sent_after_log_query`。 |

## 9. 端到端流程

### 9.1 接入文档

```text
用户询问接入/调用/文档
  -> classify: access_docs
  -> paas_resolve_service
     -> 未唯一命中: qiyu_send_message 追问服务 -> paas_finish_decision(terminal=false)
     -> 唯一命中: paas_get_manual_url
  -> qiyu_send_message 发送文档 URL
  -> paas_finish_decision(terminal=true, terminalReason=manual_sent)
```

### 9.2 服务报错：probe 异常

```text
用户反馈服务报错
  -> classify: service_error
  -> paas_resolve_service
     -> 未唯一命中: qiyu_send_message 追问服务 -> paas_finish_decision(terminal=false)
     -> 唯一命中: paas_probe_service
  -> probeResult.available=false
  -> paas_send_erp_message
  -> 不调用 qiyu_send_message
  -> paas_finish_decision(terminal=true, terminalReason=erp_sent_after_probe_failure)
```

### 9.3 服务报错：probe 正常但缺上下文

```text
用户反馈服务报错
  -> classify: service_error
  -> paas_resolve_service
  -> paas_probe_service
  -> probeResult.available=true
  -> 缺少 requestId/appKey
  -> qiyu_send_message 询问 requestId、appKey、可选 time
  -> paas_finish_decision(terminal=false, waitingFor=request_context)
```

### 9.4 服务报错：补充上下文后查日志并提交 ERP/POPo

```text
agentState.waitingFor=request_context
  -> 从当前消息和历史提取 requestId/appKey/time
  -> paas_query_logs
  -> paas_send_erp_message(logResult=日志查询结果)
  -> 不调用 qiyu_send_message
  -> paas_finish_decision(terminal=true, terminalReason=erp_sent_after_log_query)
```

### 9.5 其他场景

```text
用户消息不属于 PaaS 接入或服务报错
  -> classify: other
  -> 不调用 probe/log/ERP/POPo
  -> paas_finish_decision(terminal=true)
```

## 10. 环境变量

| 环境变量 | 作用 |
|---|---|
| `PAAS_SERVICE_REGISTRY_PATH` | 覆盖服务注册表路径。 |
| `YOUDAO_<SERVICE>_APP_KEY` | 指定服务的有道 appKey，例如 `YOUDAO_OCR_APP_KEY`。 |
| `YOUDAO_<SERVICE>_APP_SECRET` | 指定服务的有道 appSecret，例如 `YOUDAO_OCR_APP_SECRET`。 |
| `YOUDAO_APP_KEY` | 所有服务共用的默认有道 appKey。 |
| `YOUDAO_APP_SECRET` | 所有服务共用的默认有道 appSecret。 |
| `PAAS_O2LOG_ENDPOINT` | 覆盖 o2log 查询 endpoint。 |
| `PAAS_O2LOG_AUTHORIZATION` | o2log 查询 Authorization header。 |
| `PAAS_POPO_ENDPOINT` | 覆盖 POPo/ERP endpoint。 |
| `PAAS_ERP_ENDPOINT` | POPo/ERP endpoint 的兼容覆盖项。 |
| `QIYU_SEND_MESSAGE_ENDPOINT` | 覆盖七鱼发送消息 endpoint。 |
| `QIYU_SEND_MESSAGE_MOCK` | 为 `true` 时七鱼发送消息走 mock，只记录 assistant message。 |
| `ADMIN_TOKEN` | 调用七鱼发送消息 endpoint 的 Admin-Token。 |

## 11. 安全与错误语义

1. 工具错误必须安全摘要，不能暴露原始异常、token、headers、cookies、签名、完整 appKey、appSecret、私钥或原始日志。
2. 用户可见消息必须通过 `qiyu_send_message`，不能让 Java 代发业务兜底消息。
3. probe 失败 ERP/POPo 分支不发送七鱼消息，避免向用户暴露内部探活诊断。
4. 日志查询结果只用于 ERP/POPo；不要通过七鱼发送 raw logs 或日志诊断。
5. `logResult.hits` 是唯一表示匹配用户请求日志的字段。
6. `hits=[]` 只表示未找到匹配日志，不能推断用户请求认证失败、签名错误、服务异常或 appKey 无效。
7. `queryError` 表示 o2log 查询自身失败，不表示用户的 PaaS API 调用失败。
8. 服务 ID、文档 URL、日志流、ERP 产品名必须来自注册表或工具结果，不能由模型记忆生成。
9. 插件不得执行技能文档中的 curl、Bash 或示例请求。
10. `paas_finish_decision` 是每轮唯一结构化出口；不能只返回自然语言。

## 12. 测试覆盖

当前插件测试集中在 `tests/test_plugins/test_paas_customer_service/`，覆盖以下方向：

| 测试文件 | 覆盖重点 |
|---|---|
| `test_paas_agent_input_model.py` | Java 输入模型字段和别名。 |
| `test_paas_resolve_service_tool.py` | 服务注册表解析、唯一匹配、歧义和候选返回。 |
| `test_paas_get_manual_url_tool.py` | 文档 URL 从注册表读取，未知服务错误。 |
| `test_paas_probe_service_tool.py` | probe 结果分类、mock、凭证缺失和服务模板行为。 |
| `test_paas_query_logs_tool.py` | requestId/appKey 查询、时间窗口、`hits` 与 query error 语义。 |
| `test_paas_send_erp_message_tool.py` | POPo/ERP 消息格式、endpoint 覆盖、截断和错误处理。 |
| `test_paas_finish_decision_tool.py` | 终态校验、等待状态校验、assistant message 汇总。 |

建议修改插件行为时优先补充对应工具级测试。技能文档变更需要人工按端到端路径走查：接入文档、服务不明确、probe 失败、probe 正常缺上下文、补充上下文查日志、other 场景。

## 13. 维护规则

1. 新增服务时，只扩展服务注册表和必要的服务技能文档；不要在路由技能中硬编码服务 ID。
2. 新增 probe 模板时，在 `_youdao_probe.py` 中增加模板构造和结果分类，并补充工具测试。
3. 新增日志查询字段时，保持 `paas_query_logs` 的结构化输入；不要允许模型传 raw SQL、DSL 或 Lucene 查询。
4. 新增用户话术时，先确认是否需要用户可见消息；probe 失败 ERP/POPo 分支继续保持静默。
5. 新增 Java 字段时，必须保持 Java 侧薄桥接边界：Java 只传上下文，不解释插件业务状态。
